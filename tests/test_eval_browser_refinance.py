import asyncio
import os
import re
import time

import pytest
from google.adk.sessions import InMemorySessionService

from synthia.agents.agent import JEV_MODEL_SPEC, TASK_MODEL, Agent, required_api_key
from synthia.agents.browser.decider import LlmDecider
from synthia.agents.browser.jev import JevClient, jev_available
from synthia.agents.browser.loop import run_goal
from synthia.agents.browser.page import HostBrowser, Tab
from synthia.agents.browser.tools import BrowserService, create_browser_tools

_CDP = os.getenv("BROWSER_CDP_HTTP", "http://localhost:9222")
_START_URL = "https://www.bankrate.com/mortgages/refinance-rates/"
_VALUES = {
    "loan amount": "600000",
    "property value": "950000",
    "credit score": "800",
    "zip code": "96150",
}
_OBJECTIVE = (
    "Find the best zero-point mortgage refinance rate on this page for a $600,000 loan on a $950,000 property, "
    "with an 800 credit score, in zip code 96150. Dismiss any cookie or subscription gate, enter those details in "
    "the rate search form and apply them, then filter the results to zero-point offers only (the points filter, "
    "sometimes shown as 'Points' or 'All points options'). The goal is met when the results table lists refinance "
    "offers whose points are 0 and you can read the lowest rate and APR among them."
)
_RUNS = int(os.getenv("EVAL_RUNS", "1"))
_MAX_STEPS = int(os.getenv("EVAL_MAX_STEPS", "40"))
_TIMEOUT_S = float(os.getenv("EVAL_TIMEOUT_S", "300"))
_GEMINI_MODEL = os.getenv("EVAL_GEMINI_MODEL", "gemini/gemini-3.1-flash-lite")
_HARNESS_MODELS = [m for m in os.getenv("EVAL_HARNESS_MODELS", "gpt-5.6-luna").split(",") if m]

_RATE_MIN, _RATE_MAX = 2.0, 15.0
_RATE = re.compile(r"(\d{1,2}\.\d{2,3})\s*%")
_ZERO_POINTS = re.compile(r"points?\D{0,20}\b0(?:\.0{1,3})?\b|\bzero[- ]points?\b", re.I)
_GEMINI_KEY = required_api_key(TASK_MODEL.name)

needs_env = pytest.mark.skipif(
    not (jev_available() and _GEMINI_KEY and os.getenv(_GEMINI_KEY)),
    reason="requires TYPESAFE_API_KEY and GEMINI_API_KEY",
)


def _rates(model: str) -> tuple[float, float, float]:
    import litellm

    cost = litellm.model_cost.get(model) or litellm.model_cost.get(model.split("/", 1)[-1]) or {}

    def per_m(key):
        return float(cost.get(key) or 0) * 1_000_000

    return per_m("input_cost_per_token"), per_m("output_cost_per_token"), per_m("cache_read_input_token_cost")


def plausible_rates(text: str) -> list[float]:
    found = [float(m) for m in _RATE.findall(text or "")]
    return sorted({r for r in found if _RATE_MIN <= r <= _RATE_MAX})


def shows_zero_points(text: str) -> bool:
    return bool(_ZERO_POINTS.search(text or ""))


def score(text: str, url: str) -> dict:
    rates = plausible_rates(text)
    on_bankrate = "bankrate.com" in (url or "")
    zero = shows_zero_points(text)
    return {
        "best_rate": rates[0] if rates else None,
        "rates_seen": len(rates),
        "zero_points": zero,
        "found": bool(rates) and zero and on_bankrate,
    }


async def _loop_run(label: str, decider, close=None) -> dict:
    host = HostBrowser(_CDP)
    tab = Tab(host)
    started = time.perf_counter()
    try:
        await tab.open(_START_URL)
        result = await run_goal(tab, decider, _OBJECTIVE, dict(_VALUES), max_steps=_MAX_STEPS, timeout_s=_TIMEOUT_S)
    finally:
        await tab.close()
        await host.close()
        if close is not None:
            await close()
    return {
        "driver": label,
        "status": result.status,
        "seconds": round(time.perf_counter() - started, 1),
        "model_calls": result.jev_calls,
        "input_tokens": result.jev_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": result.cost_usd,
        "model_ms": result.jev_mean_ms,
        "steps": result.steps,
        **score(result.summary, result.url),
    }


async def _jev_run() -> dict:
    jev = JevClient()
    return await _loop_run(
        f"jev ({jev.model}, ${JEV_MODEL_SPEC.input_cost_per_m}/M in, output free)", jev, close=jev.close
    )


def _harness_run(model: str):
    async def run() -> dict:
        in_rate, out_rate, cache_rate = _rates(model)
        decider = LlmDecider(model, in_rate, out_rate, cache_rate)
        return await _loop_run(f"harness:{model} (${in_rate}/M in, ${out_rate}/M out)", decider)

    return run


async def _gemini_run() -> dict:
    service = BrowserService(_CDP)
    tools = [
        t
        for t in create_browser_tools(service, thread_id=9002, show_images=False)
        if getattr(t, "__name__", "") not in ("browser_do", "browser_check")
    ]
    instruction = (
        "You have a real web browser, driven through the browser_* tools. "
        "When you have the answer, reply with the lowest zero-point rate and its APR. "
        "If you cannot make progress after several attempts, reply with BLOCKED and why."
    )
    agent = await Agent.create(
        tools=tools,
        system_prompt=instruction,
        session_service=InMemorySessionService(),
        model=_GEMINI_MODEL,
        include_builtins=False,
        name="refi_eval",
        prompt_thread_hint=False,
    )
    started = time.perf_counter()
    try:
        result = await agent.run_for_result(objective=f"Open {_START_URL}. {_OBJECTIVE}", session_id="eval-refi")
    finally:
        await service.close()
    assert result is not None
    usage = await _usage_from_session(agent)
    in_rate, out_rate, cache_rate = _rates(_GEMINI_MODEL)
    uncached = usage["input_tokens"] - usage["cached_tokens"]
    cost = (uncached * in_rate + usage["cached_tokens"] * cache_rate + usage["output_tokens"] * out_rate) / 1_000_000
    seen = f"{result.result}\n{usage['tool_outputs']}"
    return {
        "driver": f"gemini ({_GEMINI_MODEL}, ${in_rate}/M in, ${out_rate}/M out)",
        "status": result.result[:60].replace("\n", " "),
        "seconds": round(time.perf_counter() - started, 1),
        "model_calls": usage["calls"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cost_usd": round(cost, 6),
        "model_ms": usage["model_ms"],
        "steps": usage["steps"],
        **score(seen, _START_URL),
    }


async def _usage_from_session(agent: Agent) -> dict:
    session = await agent._session_service.get_session(app_name="synthia", user_id="default", session_id="eval-refi")
    calls = input_tokens = output_tokens = cached_tokens = 0
    steps: list[str] = []
    tool_outputs = ""
    latencies: list[float] = []
    previous_at: float | None = None
    for event in session.events if session else []:
        usage = getattr(event, "usage_metadata", None)
        if usage and (usage.prompt_token_count or usage.candidates_token_count):
            calls += 1
            input_tokens += usage.prompt_token_count or 0
            output_tokens += usage.candidates_token_count or 0
            cached_tokens += getattr(usage, "cached_content_token_count", 0) or 0
            if previous_at is not None:
                latencies.append((event.timestamp - previous_at) * 1000)
        previous_at = event.timestamp
        for part in (event.content.parts if event.content else []) or []:
            if part.function_call:
                args = dict(part.function_call.args or {})
                steps.append(f"{part.function_call.name}({str(next(iter(args.values()), ''))[:60]})")
            if part.function_response:
                tool_outputs += str(part.function_response.response)
    return {
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "steps": steps,
        "tool_outputs": tool_outputs,
        "model_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
    }


def _report(rows: list[dict]) -> str:
    lines = [
        "",
        f"runs={_RUNS} loan={_VALUES['loan amount']} value={_VALUES['property value']} "
        f"fico={_VALUES['credit score']} zip={_VALUES['zip code']}",
        "| run | driver | status | found | best rate | rates seen | zero pts | seconds | model calls "
        "| mean model ms | input tok | output tok | cost USD |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['run']} | {r['driver']} | {r['status']} | {'yes' if r['found'] else 'no'} | "
            f"{r['best_rate'] if r['best_rate'] is not None else '-'} | {r['rates_seen']} | "
            f"{'yes' if r['zero_points'] else 'no'} | {r['seconds']} | {r['model_calls']} | {r['model_ms']} | "
            f"{r['input_tokens']} | {r['output_tokens']} | {r['cost_usd']:.6f} |"
        )
    lines.append("\n| driver | found | mean s | mean cost | mean calls | mean model ms |\n|---|---|---|---|---|---|")
    for driver in dict.fromkeys(r["driver"] for r in rows):
        group = [r for r in rows if r["driver"] == driver]
        ok = [r for r in group if r["found"]]

        def mean(key, rs):
            return (sum(r[key] for r in rs) / len(rs)) if rs else 0

        lines.append(
            f"| {driver} | {len(ok)}/{len(group)} | {mean('seconds', ok):.1f} | {mean('cost_usd', group):.5f} "
            f"| {mean('model_calls', group):.1f} | {mean('model_ms', group):.0f} |"
        )
    for r in rows:
        lines.append(f"\nrun {r['run']} {r['driver']} steps:")
        lines.extend(f"  {s}" for s in r["steps"])
    return "\n".join(lines)


@pytest.mark.eval
@needs_env
async def test_zero_point_refinance_rate() -> None:
    rows = []
    drivers = {"jev": _jev_run, "gemini": _gemini_run}
    drivers.update({f"harness:{m}": _harness_run(m) for m in _HARNESS_MODELS})
    requested = os.getenv("EVAL_DRIVERS", "jev,gemini,harness").split(",")
    selected = [d for d in requested if d in drivers] + (
        [f"harness:{m}" for m in _HARNESS_MODELS] if "harness" in requested else []
    )
    for index in range(1, _RUNS + 1):
        for run in (drivers[d] for d in selected):
            row = await run()
            row["run"] = index
            rows.append(row)
            print(_report([row]).splitlines()[4], flush=True)
            await asyncio.sleep(2)
    print(_report(rows))
    assert any(row["found"] for row in rows), "no run reached zero-point refinance rates"
