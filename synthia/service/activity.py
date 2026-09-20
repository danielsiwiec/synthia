import json
import time
from dataclasses import dataclass
from typing import Any

from google.adk.sessions import BaseSessionService

_ARGS_CHARS = 90
_RESULT_CHARS = 160
_TEXT_CHARS = 160
_TRAIL_LIMIT = 60


@dataclass(frozen=True)
class Step:
    at: float
    kind: str
    name: str
    detail: str
    done_at: float | None = None
    result: str = ""

    @property
    def in_flight(self) -> bool:
        return self.kind == "tool" and self.done_at is None


@dataclass(frozen=True)
class Activity:
    started_at: float | None
    steps: list[Step]

    def current(self, now: float | None = None) -> str:
        now = now or time.time()
        if not self.steps:
            return "no activity recorded yet"
        last = self.steps[-1]
        if last.in_flight:
            return f"current step: {last.name}({last.detail}) running for {_fmt(now - last.at)}"
        if last.kind == "tool":
            return f"last step: {last.name}({last.detail}) finished {_fmt(now - (last.done_at or last.at))} ago"
        return f"last output {_fmt(now - last.at)} ago: {last.detail}"

    def summary(self, now: float | None = None) -> str:
        now = now or time.time()
        elapsed = f"running for {_fmt(now - self.started_at)}, " if self.started_at else ""
        return f"{elapsed}{len([s for s in self.steps if s.kind == 'tool'])} tool calls, {self.current(now)}"

    def trail(self, now: float | None = None, limit: int = _TRAIL_LIMIT) -> str:
        now = now or time.time()
        if not self.steps:
            return "no activity recorded yet"
        start = self.started_at or self.steps[0].at
        shown = self.steps[-limit:]
        lines = [f"execution trail ({len(self.steps)} entries, showing last {len(shown)}; t=0 at task start):"]
        for step in shown:
            stamp = f"t+{_fmt(step.at - start)}"
            if step.kind == "tool":
                if step.in_flight:
                    lines.append(f"{stamp} 🔧 {step.name}({step.detail}) … still running ({_fmt(now - step.at)})")
                else:
                    took = _fmt((step.done_at or step.at) - step.at)
                    lines.append(f"{stamp} 🔧 {step.name}({step.detail}) [{took}] → {step.result}")
            else:
                lines.append(f"{stamp} 💬 {step.detail}")
        return "\n".join(lines)


async def task_activity(session_service: BaseSessionService, app_name: str, user_id: str, session_id: str) -> Activity:
    session = await session_service.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
    return parse_events(list(getattr(session, "events", None) or []))


def parse_events(events: list[Any]) -> Activity:
    steps: list[Step] = []
    pending: dict[str, int] = {}
    started_at: float | None = None
    for event in events:
        at = float(getattr(event, "timestamp", 0.0) or 0.0)
        content = getattr(event, "content", None)
        parts = list(getattr(content, "parts", None) or []) if content else []
        author = getattr(event, "author", "")
        if started_at is None:
            started_at = at
        for part in parts:
            call = getattr(part, "function_call", None)
            if call is not None:
                key = call.id or call.name
                pending[key] = len(steps)
                steps.append(Step(at=at, kind="tool", name=call.name, detail=_args(dict(call.args or {}))))
                continue
            response = getattr(part, "function_response", None)
            if response is not None:
                index = pending.pop(response.id or response.name, None)
                result = _result(response.response)
                if index is None:
                    steps.append(Step(at=at, kind="tool", name=response.name, detail="", done_at=at, result=result))
                else:
                    open_step = steps[index]
                    steps[index] = Step(open_step.at, "tool", open_step.name, open_step.detail, at, result)
                continue
            text = getattr(part, "text", None)
            if text and not getattr(part, "thought", False) and author != "user":
                steps.append(Step(at=at, kind="text", name="", detail=_clip(text, _TEXT_CHARS)))
    return Activity(started_at=started_at, steps=steps)


def _args(args: dict[str, Any]) -> str:
    if not args:
        return ""
    if len(args) == 1:
        return _clip(str(next(iter(args.values()))), _ARGS_CHARS)
    return _clip(", ".join(f"{k}={v}" for k, v in args.items()), _ARGS_CHARS)


def _result(response: Any) -> str:
    if isinstance(response, dict):
        if len(response) == 1:
            response = next(iter(response.values()))
        else:
            try:
                response = json.dumps(response, default=str)
            except Exception:
                response = str(response)
    return _clip(str(response), _RESULT_CHARS)


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fmt(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{rest:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"
