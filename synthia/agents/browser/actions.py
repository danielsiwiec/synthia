import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from typesafe_sdk import Choice, Noul

ACTIONS: dict[str, str] = {
    "click": "click the target element (a link, button, checkbox, menu item, or an option)",
    "type": "type one of the available values into the target text field or search box",
    "select": "choose one of the available values in the target dropdown",
    "scroll_down": "scroll down because what is needed is probably further down the page",
    "scroll_up": "scroll up because what is needed is probably above",
    "back": "go back to the previous page because this page is a dead end",
    "wait": "wait because the page is still loading or a challenge is clearing",
    "done": "the goal is already fully achieved on this page; nothing else to do",
    "blocked": "the goal cannot be achieved from here: login wall, captcha, error, or the content does not exist",
}
VALUE_ACTIONS = frozenset({"type", "select"})
TARGET_ACTIONS = frozenset({"click", "type", "select"})
TYPEABLE_KINDS = frozenset({"textbox", "search", "email", "number", "password", "url", "tel", "date", "combobox"})
_TARGET_QUESTION = {"click": "click_target", "type": "type_target", "select": "select_target"}
_WORD = re.compile(r"[a-z0-9]{3,}")
_SECRET = re.compile(r"pass|secret|token|key|pin|cvv|ssn", re.I)
_VALUE_LEN = 120
_TEXT_EXCERPT = 1800
_NAME_LEN = 80


@dataclass(frozen=True)
class Element:
    ref: int
    kind: str
    name: str
    extra: str = ""
    in_viewport: bool = True
    modal: bool = False

    @property
    def typeable(self) -> bool:
        return self.kind in TYPEABLE_KINDS

    @property
    def selectable(self) -> bool:
        return self.kind == "select"

    @property
    def clickable(self) -> bool:
        return not self.typeable

    def describe(self) -> str:
        parts = [self.kind, f"'{self.name}'" if self.name else "''"]
        if self.extra:
            parts.append(self.extra)
        if self.modal:
            parts.append("[in dialog]")
        if not self.in_viewport:
            parts.append("[offscreen]")
        return " ".join(parts)

    def line(self) -> str:
        return f"#{self.ref} {self.describe()}"


@dataclass
class Observation:
    url: str
    title: str
    text: str
    alerts: list[str]
    scroll: dict[str, int]
    elements: list[Element]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "Observation":
        elements = [
            Element(
                ref=int(e["ref"]),
                kind=str(e.get("kind", "")),
                name=_clean(str(e.get("name", "")))[:_NAME_LEN],
                extra=_clean(str(e.get("extra", "")))[:_NAME_LEN],
                in_viewport=bool(e.get("inViewport", True)),
                modal=bool(e.get("modal", False)),
            )
            for e in raw.get("elements", [])
        ]
        return cls(
            url=str(raw.get("url", "")),
            title=_clean(str(raw.get("title", ""))),
            text=_clean_text(str(raw.get("text", "")))[:_TEXT_EXCERPT],
            alerts=[_clean(a)[:200] for a in raw.get("alerts", []) if _clean(a)],
            scroll=dict(raw.get("scroll", {})),
            elements=elements,
            raw=raw,
        )

    def fingerprint(self) -> str:
        body = self.url + self.title + self.text[:600] + "|".join(e.line() for e in self.elements[:60])
        return hashlib.sha1(body.encode()).hexdigest()

    def find(self, ref: int) -> Element | None:
        return next((e for e in self.elements if e.ref == ref), None)

    def render(self, max_elements: int = 120) -> str:
        lines = [f"url: {self.url}", f"title: {self.title}"]
        if self.alerts:
            lines.append("alerts: " + " | ".join(self.alerts))
        if self.scroll:
            position = f"{self.scroll.get('y', 0)}/{self.scroll.get('height', 0)}"
            lines.append(f"scroll: {position} (viewport {self.scroll.get('viewport', 0)})")
        lines.append(f"text:\n{self.text}")
        shown = min(len(self.elements), max_elements)
        lines.append(f"elements ({len(self.elements)} interactive, showing {shown}):")
        lines.extend(e.line() for e in self.elements[:max_elements])
        return "\n".join(lines)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clean_text(text: str) -> str:
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _masked(name: str, value: str) -> str:
    return "(hidden)" if _SECRET.search(name) else value[:_VALUE_LEN]


def _goal_words(goal: str) -> set[str]:
    return set(_WORD.findall(goal.lower()))


def prune(elements: list[Element], goal: str, limit: int) -> list[Element]:
    words = _goal_words(goal)

    def score(e: Element) -> tuple[int, int, int]:
        overlap = len(words & _goal_words(f"{e.name} {e.extra}"))
        return (1 if e.modal else 0, overlap, 1 if e.in_viewport else 0)

    ranked = sorted(elements, key=score, reverse=True)
    kept = ranked[:limit]
    return sorted(kept, key=lambda e: e.ref)


def build_state(
    goal: str, values: dict[str, str], observation: Observation, elements: list[Element], history: list[str]
) -> dict[str, Any]:
    page_text = observation.text.lower()
    return {
        "goal": goal,
        "available_values": {name: _masked(name, value) for name, value in sorted(values.items())},
        "values_now_visible_in_page_text": sorted(name for name, value in values.items() if value.lower() in page_text),
        "page": {
            "url": observation.url,
            "title": observation.title,
            "alerts": observation.alerts,
            "scroll": observation.scroll,
            "text": observation.text,
        },
        "elements": [e.line() for e in elements],
        "recent_actions": history[-5:],
    }


def build_questions(values: dict[str, str], elements: list[Element]) -> dict[str, Any]:
    questions: dict[str, Any] = {
        "action": Choice(
            instructions=(
                "Which single next browser action best advances `goal` on this `page`, "
                "given `elements` and `recent_actions`?"
            ),
            criteria=dict(ACTIONS),
        ),
        "goal_met": Noul(
            instructions=(
                "Considering `recent_actions` already performed and the current `page.text`, is `goal` "
                "now fully achieved (the requested content is visible, or the requested state is reached, "
                "for example an entry listed in `values_now_visible_in_page_text` was entered as the goal wanted)?"
            )
        ),
        "stuck": Noul(
            instructions=(
                "Do `recent_actions` show the same action repeating without the `page` changing, "
                "so that no available action makes progress?"
            )
        ),
        "irreversible": Noul(
            instructions=(
                "Would the next action submit a payment, send a message, delete something, "
                "or otherwise cause an effect that cannot be undone?"
            )
        ),
    }
    groups = {
        "click_target": ("clicked", [e for e in elements if e.clickable]),
        "type_target": ("typed into", [e for e in elements if e.typeable]),
        "select_target": ("used to choose an option", [e for e in elements if e.selectable]),
    }
    for name, (verb, group) in groups.items():
        if group:
            questions[name] = Choice(
                instructions=(
                    f"Which element in `elements` should be {verb} next to advance `goal`? "
                    "Prefer elements in a dialog if one blocks the page."
                ),
                criteria={str(e.ref): e.describe() for e in group},
            )
    if values:
        questions["value"] = Choice(
            instructions=(
                "If text must be typed or an option chosen, which of `available_values` belongs in the target field?"
            ),
            criteria=dict.fromkeys(values),
        )
    return questions


@dataclass(frozen=True)
class Decision:
    action: str
    target: int | None
    value: str | None
    action_confidence: float
    target_confidence: float
    goal_met: float
    stuck: float
    irreversible: float
    action_probabilities: dict[str, float] = field(default_factory=dict)
    targets: dict[str, tuple[int, float]] = field(default_factory=dict)

    def without(self, *actions: str) -> "Decision":
        remaining = {k: v for k, v in self.action_probabilities.items() if k not in actions}
        if not remaining:
            return self
        best = max(remaining, key=lambda name: remaining[name])
        target, confidence = self.targets.get(best, (None, 0.0))
        return Decision(
            best,
            target,
            self.value,
            remaining[best],
            confidence,
            self.goal_met,
            self.stuck,
            self.irreversible,
            remaining,
            self.targets,
        )

    def render(self) -> str:
        bits = [self.action]
        if self.target is not None:
            bits.append(f"#{self.target}")
        if self.value:
            bits.append(f"value={self.value}")
        return " ".join(bits) + f" (goal_met={self.goal_met:.2f} stuck={self.stuck:.2f})"


def parse_decision(answers: dict[str, Any]) -> Decision:
    action = answers["action"]
    value = answers.get("value")
    targets: dict[str, tuple[int, float]] = {}
    for name, question in _TARGET_QUESTION.items():
        answer = answers.get(question)
        if answer is not None:
            targets[name] = (int(answer.choice), float(getattr(answer, "confidence", 0.0) or 0.0))
    chosen = str(action.choice)
    target, confidence = targets.get(chosen, (None, 0.0))
    return Decision(
        action=chosen,
        target=target,
        value=str(value.choice) if value is not None else None,
        action_confidence=float(getattr(action, "confidence", 0.0) or 0.0),
        target_confidence=confidence,
        goal_met=float(answers["goal_met"].noul),
        stuck=float(answers["stuck"].noul),
        irreversible=float(answers["irreversible"].noul),
        action_probabilities={str(k): float(v) for k, v in (getattr(action, "probabilities", None) or {}).items()},
        targets=targets,
    )


def to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)
