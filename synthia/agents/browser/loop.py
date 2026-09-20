import os
import time
from collections.abc import Awaitable, Callable

from loguru import logger
from pydantic import BaseModel
from typesafe_sdk import Noul

from synthia.agents.browser.actions import (
    TARGET_ACTIONS,
    VALUE_ACTIONS,
    Decision,
    Observation,
    build_questions,
    build_state,
    parse_decision,
    prune,
)
from synthia.agents.browser.jev import JevClient, JevUsage
from synthia.agents.browser.page import Tab
from synthia.telemetry import start_span

MAX_STEPS = int(os.getenv("BROWSER_MAX_STEPS", "20"))
TIMEOUT_S = float(os.getenv("BROWSER_TIMEOUT_S", "120"))
MAX_CANDIDATES = int(os.getenv("BROWSER_MAX_CANDIDATES", "80"))
_GOAL_MET = 0.8
_DONE_AGREEMENT = 0.5
_STUCK = 0.8
_IRREVERSIBLE = 0.5
_REPEAT_LIMIT = 3
_WAIT_S = 2.0
_WAIT_MAX_S = 10.0
_SUMMARY_CHARS = 2500

OnStep = Callable[[int, str], Awaitable[None]]


class BrowseResult(BaseModel):
    status: str
    url: str = ""
    title: str = ""
    summary: str = ""
    reason: str = ""
    steps: list[str] = []
    jev_calls: int = 0
    jev_tokens: int = 0
    jev_mean_ms: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0

    def render(self) -> str:
        lines = [f"status: {self.status}"]
        if self.reason:
            lines.append(f"reason: {self.reason}")
        lines += [f"url: {self.url}", f"title: {self.title}"]
        if self.steps:
            lines.append("steps:\n  " + "\n  ".join(self.steps))
        lines.append(f"page text: {self.summary}")
        lines.append(
            f"({len(self.steps)} steps, {self.jev_calls} jev calls averaging {self.jev_mean_ms}ms, "
            f"${self.cost_usd:.5f}, {self.duration_s:.1f}s)"
        )
        return "\n".join(lines)


async def run_goal(
    tab: Tab,
    jev: JevClient,
    goal: str,
    values: dict[str, str] | None = None,
    max_steps: int = MAX_STEPS,
    timeout_s: float = TIMEOUT_S,
    allow_irreversible: bool = False,
    on_step: OnStep | None = None,
) -> BrowseResult:
    values = {k: str(v) for k, v in (values or {}).items() if str(v)}
    usage = JevUsage()
    started = time.perf_counter()
    history: list[str] = []
    fingerprints: list[str] = []
    actions: list[str] = []
    waits = 0
    observation: Observation | None = None
    status, reason = "max_steps", f"stopped after {max_steps} steps"

    with start_span("browser_run") as span:
        span.set_attribute("browser.goal", goal[:200])
        for step in range(1, max_steps + 1):
            if time.perf_counter() - started > timeout_s:
                status, reason = "timeout", f"exceeded {timeout_s:.0f}s"
                break
            observation = await tab.observe()
            fingerprints.append(observation.fingerprint())
            candidates = prune(observation.elements, goal, MAX_CANDIDATES)
            state = build_state(goal, values, observation, candidates, history)
            answers = await jev.ask(state, build_questions(values, candidates), usage)
            decision = parse_decision(answers)
            if decision.action == "done" and decision.goal_met < _DONE_AGREEMENT:
                decision = decision.without("done")
            logger.info(f"🧭 step {step}: {decision.render()}")

            if decision.goal_met >= _GOAL_MET or decision.action == "done":
                status, reason = "done", f"goal met (p={decision.goal_met:.2f})"
                break
            if decision.action == "blocked":
                status, reason = "blocked", _blocked_reason(observation, history)
                break
            if decision.stuck >= _STUCK or _repeating(fingerprints, actions):
                status, reason = "stuck", "page stopped changing"
                break
            if decision.irreversible >= _IRREVERSIBLE and not allow_irreversible:
                status, reason = "needs_confirmation", _pending(decision, observation)
                break
            if decision.action in VALUE_ACTIONS and (not values or decision.value not in values):
                status, reason = "needs_input", f"a value is needed for {_pending(decision, observation)}"
                break

            waits = waits + 1 if decision.action == "wait" else 0
            outcome = await _perform(tab, decision, observation, values, waits)
            actions.append(decision.action)
            if outcome != "download started" and (await tab.observe()).fingerprint() == fingerprints[-1]:
                outcome += " (page unchanged)"
            entry = f"{step}. {_pending(decision, observation, values)} -> {outcome}"
            history.append(entry)
            if on_step is not None:
                await on_step(step, entry)
            if outcome == "download started":
                status, reason = "done", "a file download was started"
                break
        else:
            observation = await tab.observe()

        if observation is None or observation.url != (tab.page.url if tab.page else observation.url):
            observation = await tab.observe()
        span.set_attribute("browser.status", status)
        span.set_attribute("browser.steps", len(history))
        span.set_attribute("gen_ai.usage.cost_usd", usage.cost_usd)

    return BrowseResult(
        status=status,
        url=observation.url,
        title=observation.title,
        summary=observation.text[:_SUMMARY_CHARS],
        reason=reason,
        steps=history,
        jev_calls=usage.calls,
        jev_tokens=usage.input_tokens,
        jev_mean_ms=round(sum(usage.latencies_ms) / len(usage.latencies_ms)) if usage.latencies_ms else 0,
        cost_usd=usage.cost_usd,
        duration_s=round(time.perf_counter() - started, 2),
    )


async def check(tab: Tab, jev: JevClient, question: str) -> tuple[float, JevUsage]:
    usage = JevUsage()
    observation = await tab.observe()
    state = {
        "page": {
            "url": observation.url,
            "title": observation.title,
            "alerts": observation.alerts,
            "text": observation.text,
        }
    }
    answers = await jev.ask(state, {"answer": Noul(instructions=question)}, usage)
    return float(answers["answer"].noul), usage


def _blocked_reason(observation: Observation, history: list[str]) -> str:
    dialog = next(
        (h.split("dialog dismissed: ", 1)[1].rstrip(")") for h in reversed(history) if "dialog dismissed: " in h), ""
    )
    if dialog:
        return f"the page said: {dialog}"
    if observation.alerts:
        return "the page shows: " + " | ".join(observation.alerts)[:200]
    return "no way forward from this page (login wall, error, or missing content)"


def _repeating(fingerprints: list[str], actions: list[str]) -> bool:
    if len(fingerprints) <= _REPEAT_LIMIT or len(set(fingerprints[-_REPEAT_LIMIT - 1 :])) != 1:
        return False
    return any(action != "wait" for action in actions[-_REPEAT_LIMIT:])


def _pending(decision: Decision, observation: Observation, values: dict[str, str] | None = None) -> str:
    target = observation.find(decision.target) if decision.target is not None else None
    text = decision.action
    if decision.action in TARGET_ACTIONS and target is not None:
        text += f" {target.line()}"
    if decision.action in VALUE_ACTIONS and decision.value:
        shown = (values or {}).get(decision.value)
        text += f" with {decision.value}='{shown}'" if shown else f" with value '{decision.value}'"
    return text


async def _perform(
    tab: Tab, decision: Decision, observation: Observation, values: dict[str, str], waits: int = 0
) -> str:
    action = decision.action
    if action in TARGET_ACTIONS:
        if decision.target is None or observation.find(decision.target) is None:
            return "no target element"
        if action == "click":
            return await tab.click(decision.target)
        value = values.get(decision.value or "", "")
        if action == "type":
            return await tab.type(decision.target, value, submit=True)
        return await tab.select(decision.target, value)
    if action == "scroll_down":
        return await tab.scroll(1)
    if action == "scroll_up":
        return await tab.scroll(-1)
    if action == "back":
        return await tab.back()
    if action == "wait":
        return await tab.sleep(min(_WAIT_S * (2 ** max(waits - 1, 0)), _WAIT_MAX_S))
    return f"unsupported action {action}"
