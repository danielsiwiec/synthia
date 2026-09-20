import asyncio
import os
import time
from pathlib import Path

import pytest
from google.adk.sessions import InMemorySessionService

from synthia.agents.agent import JEV_MODEL_SPEC, TASK_MODEL, Agent, required_api_key
from synthia.agents.browser.decider import LlmDecider
from synthia.agents.browser.jev import JevClient, jev_available
from synthia.agents.browser.loop import run_goal
from synthia.agents.browser.page import HostBrowser, Tab
from synthia.agents.browser.tools import BrowserService, create_browser_tools

_CDP = os.getenv("BROWSER_CDP_HTTP", "http://localhost:9222")
_DOWNLOADS = Path(os.getenv("DOWNLOADS_DIR", Path.home() / "Downloads"))
_OBJECTIVES = {
    "guided": (
        "https://freemagazines.top/?s=The+Economist+USA",
        "Starting from the search results for The Economist USA, open the newest issue listed, then start "
        "downloading its PDF file: get past any ad-block notice, cookie or 'continue' gates, follow the "
        "download / view PDF link to the file-hosting page (it may open in a new tab), and press its Download "
        "button until the file transfer actually begins.",
        {},
    ),
    "minimal": (
        "https://freemagazines.top/",
        "You have a browser. Download the PDF of the newest issue of The Economist USA from this site, "
        "navigating it as needed.",
        {"magazine": "The Economist USA"},
    ),
}
_START_URL, _OBJECTIVE, _VALUES = _OBJECTIVES[os.getenv("EVAL_OBJECTIVE", "guided")]
_RUNS = int(os.getenv("EVAL_RUNS", "1"))
_GEMINI_MODEL = os.getenv("EVAL_GEMINI_MODEL", TASK_MODEL.name)
_HARNESS_MODELS = [m for m in os.getenv("EVAL_HARNESS_MODELS", TASK_MODEL.name).split(",") if m]


def _rates(model: str) -> tuple[float, float, float]:
    import litellm

    cost = litellm.model_cost.get(model) or litellm.model_cost.get(model.split("/", 1)[-1]) or {}

    def per_m(key):
        return float(cost.get(key) or 0) * 1_000_000

    return per_m("input_cost_per_token"), per_m("output_cost_per_token"), per_m("cache_read_input_token_cost")


def _gemini_rates() -> tuple[float, float, float]:
    return _rates(_GEMINI_MODEL)


_FILE_WAIT_S = 120
_GEMINI_KEY = required_api_key(TASK_MODEL.name)

needs_env = pytest.mark.skipif(
    not (jev_available() and _GEMINI_KEY and os.getenv(_GEMINI_KEY)),
    reason="requires TYPESAFE_API_KEY and GEMINI_API_KEY",
)


def _snapshot() -> set[Path]:
    return set(_DOWNLOADS.glob("*.pdf"))


async def _wait_for_file(before: set[Path]) -> Path | None:
    deadline = time.perf_counter() + _FILE_WAIT_S
    last = -1
    while time.perf_counter() < deadline:
        new = [p for p in _snapshot() - before if "economist" in p.name.lower()]
        if new and not list(_DOWNLOADS.glob("*.crdownload")):
            size = new[0].stat().st_size
            if size == last:
                return new[0]
            last = size
        await asyncio.sleep(3)
    return None


async def _jev_run() -> dict:
    host, jev = HostBrowser(_CDP), JevClient()
    tab = Tab(host)
    started = time.perf_counter()
    try:
        await tab.open(_START_URL)
        result = await run_goal(tab, jev, _OBJECTIVE, _VALUES, max_steps=30, timeout_s=240)
    finally:
        await tab.close()
        await jev.close()
        await host.close()
    assert result.jev_tokens > 0
    assert result.cost_usd == pytest.approx(result.jev_tokens / 1_000_000 * JEV_MODEL_SPEC.input_cost_per_m, abs=1e-6)
    return {
        "driver": f"jev ({jev.model}, ${JEV_MODEL_SPEC.input_cost_per_m}/M in, output free)",
        "status": result.status,
        "seconds": round(time.perf_counter() - started, 1),
        "model_calls": result.jev_calls,
        "input_tokens": result.jev_tokens,
        "output_tokens": 0,
        "cost_usd": result.cost_usd,
        "model_ms": result.jev_mean_ms,
        "steps": result.steps,
    }


def _harness_run(model: str):
    async def run() -> dict:
        in_rate, out_rate, cache_rate = _rates(model)
        host = HostBrowser(_CDP)
        tab = Tab(host)
        started = time.perf_counter()
        try:
            await tab.open(_START_URL)
            decider = LlmDecider(model, in_rate, out_rate, cache_rate)
            result = await run_goal(tab, decider, _OBJECTIVE, _VALUES, max_steps=30, timeout_s=240)
        finally:
            await tab.close()
            await host.close()
        return {
            "driver": f"harness:{model} (${in_rate}/M in, ${out_rate}/M out, ${cache_rate}/M cached)",
            "status": result.status,
            "seconds": round(time.perf_counter() - started, 1),
            "model_calls": result.jev_calls,
            "input_tokens": result.jev_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
            "model_ms": result.jev_mean_ms,
            "steps": result.steps,
        }

    return run


async def _gemini_run() -> dict:
    service = BrowserService(_CDP)
    tools = [
        t
        for t in create_browser_tools(service, thread_id=9001, show_images=False)
        if getattr(t, "__name__", "") not in ("browser_do", "browser_check")
    ]
    instruction = (
        "You have a real web browser, driven through the browser_* tools. "
        "Stop as soon as a tool result says 'download started' and reply with the single word DONE. "
        "If you cannot make progress after several attempts, reply with BLOCKED and why."
    )
    agent = await Agent.create(
        tools=tools,
        system_prompt=instruction,
        session_service=InMemorySessionService(),
        model=_GEMINI_MODEL,
        include_builtins=False,
        name="browser_eval",
        prompt_thread_hint=False,
    )
    started = time.perf_counter()
    try:
        result = await agent.run_for_result(objective=f"Open {_START_URL}. {_OBJECTIVE}", session_id="eval-gemini")
    finally:
        await service.close()
    assert result is not None
    usage = await _usage_from_session(agent)
    in_rate, out_rate, cache_rate = _gemini_rates()
    uncached = usage["input_tokens"] - usage["cached_tokens"]
    cost = (uncached * in_rate + usage["cached_tokens"] * cache_rate + usage["output_tokens"] * out_rate) / 1_000_000
    return {
        "driver": f"gemini ({_GEMINI_MODEL}, ${in_rate}/M in, ${out_rate}/M out, ${cache_rate}/M cached)",
        "status": "done" if "download started" in usage["tool_outputs"] else result.result[:60],
        "seconds": round(time.perf_counter() - started, 1),
        "model_calls": usage["calls"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cost_usd": round(cost, 6),
        "model_ms": usage["model_ms"],
        "steps": usage["steps"],
    }


async def _usage_from_session(agent: Agent) -> dict:
    session = await agent._session_service.get_session(app_name="synthia", user_id="default", session_id="eval-gemini")
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
        f"objective={os.getenv('EVAL_OBJECTIVE', 'guided')} runs={_RUNS}",
        "| run | driver | status | seconds to download start | file on disk | model calls "
        "| mean model ms | input tok | output tok | cost USD |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['run']} | {r['driver']} | {r['status']} | {r['seconds']} | {r['file_seconds']} | "
            f"{r['model_calls']} | {r['model_ms']} | {r['input_tokens']} | {r['output_tokens']} | {r['cost_usd']:.6f} |"
        )
    lines.append("\n| driver | success | mean s | mean cost | mean calls | mean model ms |\n|---|---|---|---|---|---|")
    for driver in dict.fromkeys(r["driver"] for r in rows):
        group = [r for r in rows if r["driver"] == driver]
        ok = [r for r in group if r["file"]]

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
async def test_economist_download_jev_vs_gemini() -> None:
    rows = []
    drivers = {"jev": _jev_run, "gemini": _gemini_run}
    drivers.update({f"harness:{m}": _harness_run(m) for m in _HARNESS_MODELS})
    requested = os.getenv("EVAL_DRIVERS", "jev,gemini").split(",")
    selected = [d for d in requested if d in drivers] + (
        [f"harness:{m}" for m in _HARNESS_MODELS] if "harness" in requested else []
    )
    for index in range(1, _RUNS + 1):
        for run in (drivers[d] for d in selected):
            before = _snapshot()
            started = time.perf_counter()
            row = await run()
            file = await _wait_for_file(before) if row["status"] == "done" else None
            row["run"] = index
            row["file_seconds"] = round(time.perf_counter() - started, 1) if file else "none"
            row["file"] = str(file) if file else None
            if file:
                file.unlink()
            rows.append(row)
            print(_report([row]).splitlines()[4], flush=True)
            await asyncio.sleep(2)
    print(_report(rows))
    assert any(row["file"] for row in rows), "no run produced a file"
