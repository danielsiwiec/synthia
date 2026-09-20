import json
import time
from typing import Any, Protocol

import litellm
from loguru import logger

from synthia.agents.browser.actions import (
    ACTIONS,
    TARGET_ACTIONS,
    VALUE_ACTIONS,
    Decision,
    Element,
    build_questions,
    parse_decision,
)
from synthia.agents.browser.jev import JevClient, JevUsage
from synthia.telemetry import start_span

_LLM_TIMEOUT_S = 30
_MAX_OUTPUT_TOKENS = 300


class Decider(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def calibrated(self) -> bool: ...

    async def decide(
        self, state: dict[str, Any], values: dict[str, str], elements: list[Element], usage: JevUsage
    ) -> Decision: ...


class JevDecider:
    def __init__(self, client: JevClient):
        self._client = client

    @property
    def model(self) -> str:
        return self._client.model

    @property
    def calibrated(self) -> bool:
        return True

    async def decide(
        self, state: dict[str, Any], values: dict[str, str], elements: list[Element], usage: JevUsage
    ) -> Decision:
        answers = await self._client.ask(state, build_questions(values, elements), usage)
        return parse_decision(answers)


_SYSTEM_PROMPT = (
    "You choose the single next browser action that best advances `goal`, given the current page state.\n"
    "Actions: {actions}\n"
    "Rules:\n"
    "- For click/type/select, `target` must be the numeric ref of an element listed in `elements` (an integer "
    "from a line like \"#12 button 'Download'\"); otherwise null. Only type into text fields and only select in "
    "dropdowns.\n"
    "- For type/select, set `value` to the name of an entry in `available_values` when one fits; if none fits "
    "but you know the exact text to enter, put it in `text` and leave `value` null.\n"
    "- Prefer elements inside a dialog when one blocks the page. Do not repeat an action that `recent_actions` "
    "shows left the page unchanged.\n"
    "- `goal_met`: probability (0-1) that `goal` is already fully achieved on the current page, considering "
    "`recent_actions` and `page.text`.\n"
    "- `stuck`: probability (0-1) that no available action makes progress (same action repeating without change).\n"
    "- `irreversible`: probability (0-1) that the next action submits a payment, sends a message, deletes "
    "something, or otherwise cannot be undone.\n"
    "Respond with JSON only, matching the schema."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(ACTIONS)},
        "target": {"type": ["integer", "null"]},
        "value": {"type": ["string", "null"]},
        "text": {"type": ["string", "null"]},
        "goal_met": {"type": "number"},
        "stuck": {"type": "number"},
        "irreversible": {"type": "number"},
    },
    "required": ["action", "target", "value", "text", "goal_met", "stuck", "irreversible"],
    "additionalProperties": False,
}


class LlmDecider:
    def __init__(self, model: str, input_cost_per_m: float, output_cost_per_m: float, cached_cost_per_m: float = 0.0):
        self._model = model
        self._in = input_cost_per_m
        self._out = output_cost_per_m
        self._cached = cached_cost_per_m

    @property
    def model(self) -> str:
        return self._model

    @property
    def calibrated(self) -> bool:
        return False

    async def decide(
        self, state: dict[str, Any], values: dict[str, str], elements: list[Element], usage: JevUsage
    ) -> Decision:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT.format(actions=json.dumps(ACTIONS))},
            {"role": "user", "content": json.dumps(state, ensure_ascii=False)},
        ]
        started = time.perf_counter()
        with start_span("llm_decide") as span:
            response = await litellm.acompletion(
                model=self._model,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "browser_decision", "schema": _SCHEMA, "strict": True},
                },
                max_tokens=_MAX_OUTPUT_TOKENS,
                timeout=_LLM_TIMEOUT_S,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            prompt_tokens = int(getattr(response.usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(response.usage, "completion_tokens", 0) or 0)
            details = getattr(response.usage, "prompt_tokens_details", None)
            cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
            cost = round(
                ((prompt_tokens - cached) * self._in + cached * self._cached + completion_tokens * self._out)
                / 1_000_000,
                8,
            )
            usage.record(prompt_tokens, completion_tokens, cost, latency_ms)
            span.set_attribute("gen_ai.request.model", self._model)
            span.set_attribute("gen_ai.usage.input_tokens", prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", completion_tokens)
            span.set_attribute("gen_ai.usage.cost_usd", cost)
        content = response.choices[0].message.content or "{}"
        logger.debug(f"🧭 {self._model} {prompt_tokens}+{completion_tokens} tokens, {latency_ms}ms: {content[:120]}")
        return parse_llm_decision(content, elements, values)


def parse_llm_decision(content: str, elements: list[Element], values: dict[str, str]) -> Decision:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {}
    action = str(data.get("action") or "wait")
    if action not in ACTIONS:
        action = "wait"
    refs = {e.ref for e in elements}
    target = data.get("target")
    target = int(target) if isinstance(target, (int, float)) and int(target) in refs else None
    if action in TARGET_ACTIONS and target is None:
        action = "wait"
    value = data.get("value")
    value = str(value) if value in values else None
    text = data.get("text")
    text = str(text).strip() if isinstance(text, str) and text.strip() else None
    if action in VALUE_ACTIONS and value is None and text is None:
        action = "wait"
    return Decision(
        action=action,
        target=target,
        value=value,
        action_confidence=1.0,
        target_confidence=1.0 if target is not None else 0.0,
        goal_met=_prob(data.get("goal_met")),
        stuck=_prob(data.get("stuck")),
        irreversible=_prob(data.get("irreversible")),
        text=text,
    )


def _prob(raw: Any) -> float:
    try:
        return min(max(float(raw), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0
