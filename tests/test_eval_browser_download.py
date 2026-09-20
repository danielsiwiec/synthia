import asyncio
import os
import time
from pathlib import Path

import pytest
from google.adk.sessions import InMemorySessionService

from synthia.agents.agent import JEV_MODEL_SPEC, TASK_MODEL, Agent, required_api_key
from synthia.agents.browser.jev import JevClient, jev_available
from synthia.agents.browser.loop import run_goal
from synthia.agents.browser.page import HostBrowser, Tab
from synthia.agents.browser.tools import BrowserService, create_browser_tools

_CDP = os.getenv("BROWSER_CDP_HTTP", "http://localhost:9222")
_DOWNLOADS = Path(os.getenv("DOWNLOADS_DIR", Path.home() / "Downloads"))
_SEARCH_URL = "https://freemagazines.top/?s=The+Economist+USA"
_OBJECTIVE = (
    "Starting from the search results for The Economist USA, open the newest issue listed, then start "
    "downloading its PDF file: get past any ad-block notice, cookie or 'continue' gates, follow the "
    "download / view PDF link to the file-hosting page (it may open in a new tab), and press its Download "
    "button until the file transfer actually begins."
)
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
        await tab.open(_SEARCH_URL)
        result = await run_goal(tab, jev, _OBJECTIVE, max_steps=30, timeout_s=240)
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
        "steps": result.steps,
    }


async def _gemini_run() -> dict:
    service = BrowserService(_CDP)
    tools = [
        t
        for t in create_browser_tools(service, thread_id=9001, show_images=False)
        if getattr(t, "__name__", "") not in ("browser_do", "browser_check")
    ]
    instruction = (
        "You control a real web browser through the browser_* tools only. Work step by step: open pages, "
        "observe, act on element refs from the latest observation, and re-observe after every action. "
        "Stop as soon as a tool result says 'download started' and reply with the single word DONE. "
        "If you cannot make progress after several attempts, reply with BLOCKED and why."
    )
    agent = await Agent.create(
        tools=tools,
        system_prompt=instruction,
        session_service=InMemorySessionService(),
        model=TASK_MODEL.name,
        include_builtins=False,
        name="browser_eval",
        prompt_thread_hint=False,
    )
    started = time.perf_counter()
    try:
        result = await agent.run_for_result(objective=f"Open {_SEARCH_URL}. {_OBJECTIVE}", session_id="eval-gemini")
    finally:
        await service.close()
    assert result is not None
    usage = await _usage_from_session(agent)
    return {
        "driver": (
            f"gemini ({TASK_MODEL.name}, ${TASK_MODEL.input_cost_per_m}/M in, ${TASK_MODEL.output_cost_per_m}/M out)"
        ),
        "status": "done" if "download started" in usage["tool_outputs"] else result.result[:60],
        "seconds": round(time.perf_counter() - started, 1),
        "model_calls": usage["calls"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cost_usd": result.cost_usd or 0.0,
        "steps": usage["steps"],
    }


async def _usage_from_session(agent: Agent) -> dict:
    session = await agent._session_service.get_session(app_name="synthia", user_id="default", session_id="eval-gemini")
    calls = input_tokens = output_tokens = 0
    steps: list[str] = []
    tool_outputs = ""
    for event in session.events if session else []:
        usage = getattr(event, "usage_metadata", None)
        if usage and (usage.prompt_token_count or usage.candidates_token_count):
            calls += 1
            input_tokens += usage.prompt_token_count or 0
            output_tokens += usage.candidates_token_count or 0
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
        "steps": steps,
        "tool_outputs": tool_outputs,
    }


def _report(rows: list[dict]) -> str:
    lines = [
        "",
        "| driver | status | seconds to download start | file on disk | model calls "
        "| input tok | output tok | cost USD |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['driver']} | {r['status']} | {r['seconds']} | {r['file_seconds']} | {r['model_calls']} | "
            f"{r['input_tokens']} | {r['output_tokens']} | {r['cost_usd']:.6f} |"
        )
    for r in rows:
        lines.append(f"\n{r['driver']} steps:")
        lines.extend(f"  {s}" for s in r["steps"])
    return "\n".join(lines)


@pytest.mark.eval
@needs_env
async def test_economist_download_jev_vs_gemini() -> None:
    rows = []
    for run in (_jev_run, _gemini_run):
        before = _snapshot()
        started = time.perf_counter()
        row = await run()
        file = await _wait_for_file(before)
        row["file_seconds"] = round(time.perf_counter() - started, 1) if file else "none"
        row["file"] = str(file) if file else None
        if file:
            file.unlink()
        rows.append(row)
        await asyncio.sleep(2)
    print(_report(rows))
    for row in rows:
        assert row["file"], f"{row['driver']} did not produce a file: {row}"
