import asyncio
import functools
import http.server
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from synthia.agents.browser.actions import (
    Decision,
    Element,
    Observation,
    build_questions,
    build_state,
    parse_decision,
    prune,
)
from synthia.agents.browser.decider import parse_llm_decision
from synthia.agents.browser.jev import JevClient, jev_available
from synthia.agents.browser.loop import BrowseResult, _repeating, check, run_goal
from synthia.agents.browser.page import HostBrowser, Tab, cdp_endpoint
from synthia.agents.browser.tools import BrowserService, create_browser_tools

_FIXTURES = Path(__file__).parent / "fixtures"
_CDP = os.getenv("BROWSER_CDP_HTTP", "http://localhost:9222")


def _chrome_reachable() -> bool:
    try:
        return httpx.get(f"{_CDP}/json/version", timeout=2).status_code == 200
    except Exception:
        return False


_HAS_CHROME = _chrome_reachable()
needs_chrome = pytest.mark.skipif(not _HAS_CHROME, reason=f"no Chrome CDP endpoint at {_CDP}")
needs_jev = pytest.mark.skipif(not jev_available(), reason="requires TYPESAFE_API_KEY")


def _by_name(tools: list) -> dict:
    return {tool.__name__: tool for tool in tools}


def _raw(elements: list[dict], **overrides) -> dict:
    raw = {
        "url": "https://example.test/page",
        "title": "Example",
        "text": "Hello   world",
        "alerts": [],
        "scroll": {"y": 0, "height": 1000, "viewport": 800},
        "elements": elements,
    }
    raw.update(overrides)
    return raw


@pytest.mark.smoke
def test_observation_cleans_and_renders_elements() -> None:
    obs = Observation.from_raw(
        _raw(
            [
                {"ref": 1, "kind": "button", "name": "  Download\n now ", "modal": True},
                {"ref": 2, "kind": "link", "name": "Wired", "extra": "-> /wired", "inViewport": False},
            ],
            alerts=["Ad   blocker\ndetected"],
        )
    )
    assert obs.text == "Hello world"
    assert obs.alerts == ["Ad blocker detected"]
    lines = obs.render().splitlines()
    assert "#1 button 'Download now' [in dialog]" in lines
    assert "#2 link 'Wired' -> /wired [offscreen]" in lines
    assert obs.find(2) is not None and obs.find(3) is None


@pytest.mark.smoke
def test_fingerprint_changes_with_content() -> None:
    a = Observation.from_raw(_raw([{"ref": 1, "kind": "button", "name": "Add"}]))
    b = Observation.from_raw(_raw([{"ref": 1, "kind": "button", "name": "Add"}]))
    c = Observation.from_raw(_raw([{"ref": 1, "kind": "button", "name": "Remove"}]))
    assert a.fingerprint() == b.fingerprint() != c.fingerprint()


@pytest.mark.smoke
def test_prune_prefers_dialog_then_goal_overlap_then_viewport_and_caps() -> None:
    elements = [Element(ref=i, kind="link", name=f"Category {i}", in_viewport=False) for i in range(1, 50)]
    elements += [
        Element(ref=50, kind="link", name="Wired USA – September 2026", in_viewport=True),
        Element(ref=51, kind="button", name="Continue", modal=True, in_viewport=True),
        Element(ref=52, kind="link", name="Wired USA – July 2026", in_viewport=False),
    ]
    kept = prune(elements, "open the newest Wired USA issue", limit=3)
    assert [e.ref for e in kept] == [50, 51, 52]


@pytest.mark.smoke
def test_questions_include_target_and_value_only_when_available() -> None:
    element = Element(ref=7, kind="textbox", name="Search")
    questions = build_questions({}, [])
    assert set(questions) == {"action", "goal_met", "stuck", "irreversible"}
    questions = build_questions({"query": "wired"}, [element])
    assert questions["type_target"].criteria == {"7": "textbox 'Search'"}
    assert "click_target" not in questions and "select_target" not in questions
    assert list(questions["value"].criteria) == ["query"]
    button = Element(ref=8, kind="button", name="Go")
    assert list(build_questions({}, [element, button])["click_target"].criteria) == ["8"]
    page = Observation.from_raw(_raw([], text="Results for wired"))
    state = build_state("find it", {"query": "wired"}, page, [element], ["1. click #3 -> clicked"])
    assert state["available_values"] == {"query": "wired"} and state["elements"] == ["#7 textbox 'Search'"]
    assert state["values_now_visible_in_page_text"] == ["query"]
    assert build_state("x", {"password": "hunter2"}, Observation.from_raw(_raw([])), [], [])["available_values"] == {
        "password": "(hidden)"
    }


@pytest.mark.smoke
def test_parse_decision_and_fallback_when_done_disagrees() -> None:
    answers = {
        "action": SimpleNamespace(
            choice="done", confidence=0.6, probabilities={"done": 0.5, "click": 0.4, "wait": 0.1}
        ),
        "click_target": SimpleNamespace(choice="7", confidence=0.9),
        "type_target": SimpleNamespace(choice="9", confidence=0.4),
        "value": SimpleNamespace(choice="query"),
        "goal_met": SimpleNamespace(noul=0.2),
        "stuck": SimpleNamespace(noul=0.05),
        "irreversible": SimpleNamespace(noul=0.01),
    }
    decision = parse_decision(answers)
    assert decision.action == "done" and decision.target is None and decision.value == "query"
    fallback = decision.without("done")
    assert fallback.action == "click" and fallback.target == 7 and fallback.target_confidence == 0.9
    assert fallback.action_probabilities == {"click": 0.4, "wait": 0.1}
    assert fallback.without("click").action == "wait" and fallback.without("click").target is None
    assert Decision("wait", None, None, 1, 0, 0, 0, 0).without("wait").action == "wait"


@pytest.mark.smoke
def test_repeating_needs_unchanged_page_after_non_wait_actions() -> None:
    same = ["a", "a", "a", "a"]
    assert _repeating(same, ["click", "click", "click"])
    assert _repeating(same, ["wait", "click", "wait"])
    assert not _repeating(same, ["wait", "wait", "wait"])
    assert not _repeating(["a", "a", "a"], ["click", "click"])
    assert not _repeating(["b", "a", "a", "a"], ["click", "click", "click"])


@pytest.mark.smoke
def test_llm_decision_parsing_validates_refs_values_and_text() -> None:
    elements = [Element(ref=3, kind="textbox", name="Search"), Element(ref=9, kind="button", name="Go")]
    values = {"query": "wired"}
    good = parse_llm_decision(
        '{"action": "type", "target": 3, "value": "query", "text": null, '
        '"goal_met": 0.1, "stuck": 0, "irreversible": 0}',
        elements,
        values,
    )
    assert good.action == "type" and good.target == 3 and good.value == "query" and good.text is None
    free_text = parse_llm_decision(
        '{"action": "type", "target": 3, "value": null, "text": "The Economist", '
        '"goal_met": 0, "stuck": 0, "irreversible": 0}',
        elements,
        {},
    )
    assert free_text.action == "type" and free_text.value is None and free_text.text == "The Economist"
    bad_ref = parse_llm_decision(
        '{"action": "click", "target": 42, "goal_met": 0.2, "stuck": 0, "irreversible": 0}', elements, values
    )
    assert bad_ref.action == "wait" and bad_ref.target is None
    no_value = parse_llm_decision('{"action": "select", "target": 9, "value": "nope", "text": ""}', elements, values)
    assert no_value.action == "wait"
    done = parse_llm_decision('{"action": "done", "goal_met": 1.7, "stuck": "x", "irreversible": -1}', elements, values)
    assert done.action == "done" and (done.goal_met, done.stuck, done.irreversible) == (1.0, 0.0, 0.0)
    assert parse_llm_decision("not json", elements, values).action == "wait"


@pytest.mark.smoke
def test_browse_result_render_lists_steps_and_cost() -> None:
    text = BrowseResult(
        status="done", url="u", title="t", summary="s", steps=["1. click #1 -> clicked"], cost_usd=0.00012
    ).render()
    assert text.startswith("status: done") and "1. click #1 -> clicked" in text and "$0.00012" in text


@pytest.mark.smoke
def test_cdp_endpoint_falls_back_to_abr_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BROWSER_CDP_HTTP", raising=False)
    monkeypatch.setenv("ABR_CDP_HTTP", "http://10.0.0.1:9222")
    assert cdp_endpoint() == "http://10.0.0.1:9222"
    monkeypatch.setenv("BROWSER_CDP_HTTP", "http://localhost:9222")
    assert cdp_endpoint() == "http://localhost:9222"


@pytest.fixture(scope="module")
def fixture_url():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(_FIXTURES))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/browser_todo.html"
    finally:
        server.shutdown()


@pytest.fixture
async def tab():
    host = HostBrowser(_CDP)
    tab = Tab(host)
    try:
        yield tab
    finally:
        await tab.close()
        await host.close()


@needs_chrome
async def test_tab_observes_acts_and_evaluates(fixture_url: str, tab: Tab, tmp_path: Path) -> None:
    assert await tab.open(fixture_url) == "opened"
    obs = await tab.observe()
    assert obs.title == "Todo Fixture"
    gate = next(e for e in obs.elements if e.name == "Continue")
    assert gate.modal and "Welcome" in " ".join(obs.alerts)
    assert not any(e.name == "hidden link" for e in obs.elements)
    assert await tab.click(gate.ref) == "clicked"
    obs = await tab.observe()
    assert not obs.alerts
    field = next(e for e in obs.elements if e.kind == "textbox")
    assert field.name == "New item"
    assert await tab.type(field.ref, "buy milk", submit=True) == "typed"
    assert await tab.evaluate("Array.from(document.querySelectorAll('#list li')).map(li => li.textContent)") == [
        "buy milk"
    ]
    assert await tab.wait_for(text="buy milk", timeout_s=3) == "text 'buy milk' is visible"
    assert "timed out" in await tab.wait_for(text="no such text", timeout_s=0.5)
    shot = await tab.screenshot(tmp_path / "shot.png")
    assert shot.stat().st_size > 1000


@needs_chrome
async def test_click_follows_new_tab(fixture_url: str, tab: Tab) -> None:
    await tab.open(fixture_url)
    obs = await tab.observe()
    await tab.click(next(e.ref for e in obs.elements if e.name == "Continue"))
    obs = await tab.observe()
    pages_before = len(await tab._host.pages())
    outcome = await tab.click(next(e.ref for e in obs.elements if e.name == "Open help"))
    assert outcome.startswith("opened new tab ") and outcome.endswith("/browser_help.html")
    assert (await tab.observe()).title == "Help Popup"
    assert await tab.sleep(0.2) == "waited"
    assert len(await tab._host.pages()) == pages_before + 1
    await tab.close()
    assert len(await tab._host.pages()) == pages_before - 1


@needs_chrome
async def test_click_follows_link_target_when_click_is_swallowed(fixture_url: str, tab: Tab) -> None:
    await tab.open(fixture_url.replace("browser_todo.html", "browser_swallow.html"))
    obs = await tab.observe()
    outcome = await tab.click(next(e.ref for e in obs.elements if e.name == "Go to help"))
    assert outcome == "clicked (link did not navigate; opened its target directly)"
    assert (await tab.observe()).title == "Help Popup"
    await tab.open(fixture_url.replace("browser_todo.html", "browser_swallow.html"))
    obs = await tab.observe()
    assert await tab.click(next(e.ref for e in obs.elements if e.name == "Jump on page")) == "clicked"
    obs = await tab.observe()
    assert (await tab.observe()).url.endswith("#section")
    outcome = await tab.click(next(e.ref for e in obs.elements if e.name == "Go to help"))
    assert outcome == "clicked (link did not navigate; opened its target directly)"


@needs_chrome
async def test_click_clears_an_intercepting_overlay_and_keeps_the_popup(fixture_url: str, tab: Tab) -> None:
    await tab.open(fixture_url.replace("browser_todo.html", "browser_covered.html"))
    obs = await tab.observe()
    started = time.perf_counter()
    outcome = await tab.click(next(e.ref for e in obs.elements if e.name == "Open help"))
    assert time.perf_counter() - started < 5, "obstruction should be cleared before the first click times out"
    assert outcome.startswith("opened new tab ") and outcome.endswith("/browser_help.html")
    assert (await tab.observe()).title == "Help Popup"


@needs_chrome
async def test_observe_times_out_on_a_busy_page_instead_of_hanging(fixture_url: str, tab: Tab) -> None:
    await tab.open(fixture_url.replace("browser_todo.html", "browser_busy.html"))
    obs = await tab.observe()
    ref = next(e.ref for e in obs.elements if e.name == "Block for 4s")
    page = tab.page
    assert page is not None
    asyncio.get_event_loop().create_task(
        page.locator(f'[data-synthia-ref="{ref}"]').click(timeout=1000, no_wait_after=True)
    )
    await asyncio.sleep(0.3)
    started = time.perf_counter()
    busy = await tab.observe(timeout_s=1.5)
    assert time.perf_counter() - started < 3
    assert busy.alerts == ["page busy"] and busy.elements == []
    with pytest.raises(Exception, match="timed out"):
        await tab.evaluate("1 + 1", timeout_s=1)
    await asyncio.sleep(3)
    assert (await tab.observe()).title == "Busy Fixture"


@needs_chrome
async def test_click_dismisses_dialogs_without_killing_the_driver(fixture_url: str, tab: Tab) -> None:
    await tab.open(fixture_url)
    obs = await tab.observe()
    await tab.click(next(e.ref for e in obs.elements if e.name == "Continue"))
    obs = await tab.observe()
    outcome = await tab.click(next(e.ref for e in obs.elements if e.name == "Alert me"))
    assert outcome == "clicked (dialog dismissed: alert: Nope)"
    assert (await tab.observe()).title == "Todo Fixture"


@needs_chrome
async def test_tools_round_trip(fixture_url: str) -> None:
    service = BrowserService(_CDP)
    tools = _by_name(create_browser_tools(service, thread_id=1, show_images=False))
    try:
        opened = await tools["browser_open"](fixture_url)
        assert "title: Todo Fixture" in opened and "#" in opened
        ref = next(int(line.split()[0][1:]) for line in opened.splitlines() if "'Continue'" in line)
        acted = await tools["browser_act"]("click", ref)
        assert acted.startswith("clicked")
        assert await tools["browser_eval"]("document.title") == '"Todo Fixture"'
        assert "Error: unknown action" in await tools["browser_act"]("fly")
        tabs = await tools["browser_tabs"]()
        assert "(current)" in tabs
        assert await tools["browser_close"]() == "tab closed"
    finally:
        await service.close()


async def test_tools_report_unreachable_chrome_as_error() -> None:
    service = BrowserService("http://127.0.0.1:9")
    tools = _by_name(create_browser_tools(service, thread_id=1, show_images=False))
    try:
        assert (await tools["browser_open"]("https://example.com")).startswith("Error: host Chrome unreachable")
    finally:
        await service.close()


@pytest.mark.eval
@needs_chrome
@needs_jev
async def test_jev_loop_completes_todo_goal(fixture_url: str, tab: Tab) -> None:
    jev = JevClient()
    try:
        await tab.open(fixture_url)
        result = await run_goal(tab, jev, "Add a todo item to the list", values={"item": "buy milk"}, max_steps=6)
        assert result.status == "done", result.render()
        assert await tab.evaluate("document.querySelectorAll('#list li').length") == 1
        assert result.jev_calls >= 1 and result.cost_usd > 0
        probability, _ = await check(tab, jev, "Does the todo list contain 'buy milk'?")
        assert probability > 0.5
    finally:
        await jev.close()


@pytest.mark.eval
@needs_chrome
@needs_jev
async def test_jev_loop_stops_for_missing_value(fixture_url: str, tab: Tab) -> None:
    jev = JevClient()
    try:
        await tab.open(fixture_url)
        await tab.click(next(e.ref for e in (await tab.observe()).elements if e.name == "Continue"))
        result = await run_goal(tab, jev, "Type a new todo into the text field and add it", max_steps=4)
        assert result.status in ("needs_input", "stuck", "max_steps"), result.render()
    finally:
        await jev.close()
