import pytest
from google.adk.events import Event
from google.adk.sessions import InMemorySessionService
from google.genai import types

from synthia.service.activity import parse_events, task_activity


def _call(name: str, args: dict, at: float, call_id: str = "") -> Event:
    part = types.Part(function_call=types.FunctionCall(name=name, args=args, id=call_id or None))
    return Event(author="synthia", content=types.Content(role="model", parts=[part]), timestamp=at)


def _response(name: str, result: dict, at: float, call_id: str = "") -> Event:
    part = types.Part(function_response=types.FunctionResponse(name=name, response=result, id=call_id or None))
    return Event(author="synthia", content=types.Content(role="user", parts=[part]), timestamp=at)


def _text(text: str, at: float, author: str = "synthia") -> Event:
    return Event(author=author, content=types.Content(role="model", parts=[types.Part(text=text)]), timestamp=at)


@pytest.mark.smoke
def test_running_task_shows_in_flight_step_and_duration() -> None:
    events = [
        _text("Check for new issues", 1000.0, author="user"),
        _call("load_skill", {"skill_name": "magazines"}, 1001.0, "a"),
        _response("load_skill", {"skill_name": "magazines", "instructions": "..."}, 1002.0, "a"),
        _call("run_bash", {"command": "abr open https://freemagazines.top/"}, 1003.0, "b"),
    ]
    activity = parse_events(events)
    assert activity.started_at == 1000.0
    assert activity.steps[-1].in_flight
    assert (
        activity.current(now=1123.0) == "current step: run_bash(abr open https://freemagazines.top/) running for 2m00s"
    )
    assert activity.summary(now=1123.0).startswith("running for 2m03s, 2 tool calls, current step: run_bash(")


@pytest.mark.smoke
def test_finished_steps_render_timings_results_and_text() -> None:
    events = [
        _text("Download it", 10.0, author="user"),
        _call("browser_open", {"url": "https://example.test/issue"}, 11.0, "x"),
        _response("browser_open", {"result": "url: https://example.test/issue\ntitle: Issue"}, 13.5, "x"),
        _call("browser_do", {"goal": "start the download", "max_steps": 20}, 14.0, "y"),
        _response("browser_do", {"result": "status: done\nreason: a file download was started"}, 16.0, "y"),
        _text("Done, the file is downloading.", 17.0),
    ]
    activity = parse_events(events)
    assert activity.current(now=20.0) == "last output 3s ago: Done, the file is downloading."
    trail = activity.trail(now=20.0)
    lines = trail.splitlines()
    assert lines[0] == "execution trail (3 entries, showing last 3; t=0 at task start):"
    assert (
        lines[1]
        == "t+1s 🔧 browser_open(https://example.test/issue) [2s] → url: https://example.test/issue title: Issue"
    )
    assert lines[2].startswith("t+4s 🔧 browser_do(goal=start the download, max_steps=20) [2s] → status: done")
    assert lines[3] == "t+7s 💬 Done, the file is downloading."


@pytest.mark.smoke
def test_trail_is_capped_and_long_values_clipped() -> None:
    events = []
    for i in range(70):
        events.append(_call("run_bash", {"command": "x" * 500}, float(i), str(i)))
        events.append(_response("run_bash", {"result": "y" * 1000}, float(i) + 0.5, str(i)))
    activity = parse_events(events)
    trail = activity.trail(now=100.0, limit=5)
    lines = trail.splitlines()
    assert lines[0] == "execution trail (70 entries, showing last 5; t=0 at task start):"
    assert len(lines) == 6 and all(len(line) < 320 for line in lines[1:]) and lines[1].startswith("t+1m05s")


@pytest.mark.smoke
def test_empty_session_has_no_activity() -> None:
    activity = parse_events([])
    assert activity.current() == "no activity recorded yet" and activity.trail() == "no activity recorded yet"


async def test_task_activity_reads_session_events() -> None:
    service = InMemorySessionService()
    session = await service.create_session(app_name="synthia", user_id="default", session_id="task-1")
    await service.append_event(session, _call("run_bash", {"command": "sleep 5"}, 50.0, "k"))
    activity = await task_activity(service, "synthia", "default", "task-1")
    assert activity.steps[0].in_flight and activity.steps[0].name == "run_bash"
