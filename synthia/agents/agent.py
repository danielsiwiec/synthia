import asyncio
import json
import mimetypes
import os
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Self
from zoneinfo import ZoneInfo

from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types
from loguru import logger
from pydantic import BaseModel

from synthia.agents.builtins import create_builtin_tools
from synthia.helpers.pubsub import pubsub
from synthia.metrics import record_call_cost, record_session_cost
from synthia.service.models import VISION_MIME_TYPES, OutgoingImage, TaskImage
from synthia.telemetry import current_span, set_span_error, start_span, traced

APP_NAME = "synthia"
USER_ID = "default"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    input_cost_per_m: float
    output_cost_per_m: float


# ─── Model configuration: single source of truth ─────────────────────────────
# The front and task agent models (and their pricing) are defined ONLY here.
# Both the deployed app and the test suite import these constants, so this block
# is the one place to change a model. The two agents may use different models.
TASK_MODEL = ModelSpec("gemini/gemini-3.1-flash-lite", input_cost_per_m=0.10, output_cost_per_m=0.40)
FRONT_MODEL_SPEC = ModelSpec("gemini/gemini-3.1-flash-lite", input_cost_per_m=0.10, output_cost_per_m=0.40)
PERSONA_MODEL_SPEC = FRONT_MODEL_SPEC

DEFAULT_MODEL = TASK_MODEL.name
FRONT_MODEL = FRONT_MODEL_SPEC.name
PERSONA_MODEL = PERSONA_MODEL_SPEC.name

_MODEL_SPECS = {spec.name: spec for spec in (TASK_MODEL, FRONT_MODEL_SPEC, PERSONA_MODEL_SPEC)}
_FALLBACK_PRICING = (3.0, 15.0)

_PROVIDER_API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def required_api_key(model_name: str) -> str | None:
    return _PROVIDER_API_KEYS.get(model_name.split("/", 1)[0])


_THINKING_BUDGET = int(os.getenv("LLM_THINKING_BUDGET", "2048"))
_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "32000"))
_PROMPT_CACHING = os.getenv("LLM_PROMPT_CACHING", "1") != "0"
_CACHE_READ_MULTIPLIER = 0.1
_MAX_TURNS = int(os.getenv("MAX_TURNS", "100"))
_MAX_TOOL_OUTPUT_CHARS = int(os.getenv("MAX_TOOL_OUTPUT_CHARS", "50000"))

_delegated_cost: ContextVar[list[float] | None] = ContextVar("_delegated_cost", default=None)
_consulted_personas: ContextVar[list[str] | None] = ContextVar("_consulted_personas", default=None)


def _is_anthropic(model_name: str) -> bool:
    return "claude" in model_name or "anthropic" in model_name


def _model_kwargs(model_name: str) -> dict[str, Any]:
    if not _is_anthropic(model_name):
        return {}
    kwargs: dict[str, Any] = {}
    if _MAX_OUTPUT_TOKENS > 0:
        kwargs["max_tokens"] = _MAX_OUTPUT_TOKENS
    if _PROMPT_CACHING:
        kwargs["cache_control_injection_points"] = [
            {"location": "message", "role": "system"},
            {"location": "message", "index": -1},
        ]
    if _THINKING_BUDGET > 0:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": _THINKING_BUDGET}
        kwargs["extra_headers"] = {"anthropic-beta": "interleaved-thinking-2025-05-14"}
    return kwargs


def _pricing(model_name: str) -> tuple[float, float]:
    spec = _MODEL_SPECS.get(model_name)
    if spec is not None:
        return spec.input_cost_per_m, spec.output_cost_per_m
    return _FALLBACK_PRICING


def _token_cost(
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int,
    input_cost_per_m: float,
    output_cost_per_m: float,
) -> float:
    uncached_tokens = max(prompt_tokens - cached_tokens, 0)
    return round(
        (uncached_tokens / 1_000_000) * input_cost_per_m
        + (cached_tokens / 1_000_000) * input_cost_per_m * _CACHE_READ_MULTIPLIER
        + (completion_tokens / 1_000_000) * output_cost_per_m,
        8,
    )


def record_delegated_cost(cost: float | None) -> None:
    acc = _delegated_cost.get()
    if acc is not None and cost:
        acc.append(cost)


def record_consulted_persona(persona_id: str | None) -> None:
    acc = _consulted_personas.get()
    if acc is not None and persona_id and persona_id not in acc:
        acc.append(persona_id)


def _truncate_tool_callback(tool: Any, args: Any, tool_context: Any, tool_response: Any) -> dict | None:
    if _MAX_TOOL_OUTPUT_CHARS <= 0 or not isinstance(tool_response, dict):
        return None
    changed = False
    truncated: dict[str, Any] = {}
    for key, value in tool_response.items():
        if isinstance(value, str) and len(value) > _MAX_TOOL_OUTPUT_CHARS:
            truncated[key] = value[:_MAX_TOOL_OUTPUT_CHARS] + (
                f"\n... [truncated {len(value) - _MAX_TOOL_OUTPUT_CHARS} chars]"
            )
            changed = True
        else:
            truncated[key] = value
    return truncated if changed else None


def _cost_tracking_callback(
    model_name: str, input_cost_per_m: float, output_cost_per_m: float
) -> Callable[[Any, Any], Any]:
    def _after_model(callback_context: Any, llm_response: Any) -> None:
        usage = getattr(llm_response, "usage_metadata", None)
        if usage is None:
            return None
        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
        cached_tokens = getattr(usage, "cached_content_token_count", 0) or 0
        if not (prompt_tokens or completion_tokens):
            return None
        cost = _token_cost(prompt_tokens, completion_tokens, cached_tokens, input_cost_per_m, output_cost_per_m)
        record_call_cost(model_name, cost)
        current_span().set_attribute("gen_ai.usage.cost_usd", cost)
        return None

    return _after_model


def _today() -> str:
    tz = ZoneInfo(os.environ.get("TIMEZONE", "America/Los_Angeles"))
    return datetime.now(tz).strftime("%A, %Y-%m-%d")


SYSTEM_PROMPT = """
Your name is Synthia. You are a helpful assistant that can help with tasks and questions.

# Today is {today}.

## Shell and files
Use the run_bash tool to execute shell commands and run scripts. Use read_file and write_file for file access.

## Web access
Use the fetch_url tool to retrieve web pages. If a page is not accessible (JavaScript-rendered,
login-gated, Cloudflare-protected, or otherwise blocked), drive a real browser with the
`agent-browser` CLI via the run_bash tool — load the `agent-browser` skill for the command
reference (snapshot/ref workflow, `open`, `eval`, `click`, `find`, downloads). It connects to a
real Chrome, so it gets past bot checks that fetch_url cannot.

## Browser downloads
Browser downloads triggered via `agent-browser` are saved in the `/mounts/downloads` folder.

## Sending images
To show the user an image (a screenshot, chart, photo, generated picture, etc.), you MUST call the
send_image tool with the path to the image file. NEVER reply with a filesystem path or tell the user
to open a file — the user has no access to Synthia's file system and cannot see anything on disk. The
send_image tool persists the image and displays it inline in the chat; it is the only way an image
reaches the user.

## Diagrams
To draw a diagram (flowchart, sequence, class, state, ER, gantt, mindmap, etc.), call the
render_diagram tool with Mermaid source. It renders the diagram to an image and shows it to the user
directly — do not hand-write SVG or screenshot a browser for diagrams, and do not also call
send_image. Prefer Mermaid diagrams over ad-hoc drawings whenever the content is a diagram.
"""


FRONT_SYSTEM_PROMPT = """
Your name is Synthia. You are the fast, friendly assistant the user talks to directly. You decide how
to handle each message: answer it yourself, or hand the work to your task agent.

# Today is {today}.

## Voice
Sound like a warm, natural person — a helpful friend, not a system. Keep replies easy and
conversational, and don't over-hedge or pile on qualifiers.

Never describe HOW your memory or internals work. Don't reference "recent activity", "recent
history", "context", "snippets", "the bits I can access", "system instructions", "sessions",
"thread_id", a "task agent", or "delegating" — to the user, you simply remember things or you don't.
Lead with the answer, not a disclaimer about your memory. If the user asks what you remember, just
tell them what comes to mind. Only if you truly can't recall something, add one short warm line —
never a multi-clause explanation of how your memory works.
  Bad:  "I don't have perfect long-term memory of every conversation—just the bits that show up in
         the recent history I can access here."
  Good: "I only remember the most recent conversations we've had — here's what comes to mind:"

## Your tools
- delegate_to_task_agent(request, task_id?): run the capable task agent NOW and wait for its result.
  Use this ONLY for a quick, single-step lookup the user is actively waiting on that should finish in
  well under a minute; for anything longer or multi-step prefer dispatch_background_task (see "Sync vs
  background" below). The task agent is powerful: it can control a computer, run
  shell commands and scripts, read and write files, drive a real web browser, manage downloads, and
  use many skills — assume it CAN do almost any operational task. Never tell the user you can't do
  something the task agent could do; delegate it instead. Pass the user's actual request straight
  through (plus any context you already have); do NOT coach it on how to do its job or tell it to ask
  clarifying questions. It returns a `task_id=<id>` line as the first line of its output — remember
  that id; if the user later continues or refines that SAME work, pass the id back as task_id.
- dispatch_background_task(request, label, task_id?): start the task agent in the background and
  return immediately. Use this for long-running work, "go do X and tell me later" requests, or when
  the user wants to keep chatting. Acknowledge that you started it; the result is delivered to the
  chat automatically when ready.
- check_tasks(): list this conversation's tasks (in-flight and finished) with their task_id, label,
  status, and a result summary.
- find_past_work(query?, kind?): look up your full history of past tasks and scheduled jobs — well
  beyond the few recent tasks shown below. Use it to recall earlier work, find an old task to resume
  (it returns task_ids), or check whether a scheduled job ran. kind is "task", "job", or "all".
- consult_persona(persona, question, session_id?): get a focused single-lens perspective from a
  "thinking hat" — "black" (critical, risks), "yellow" (optimistic, benefits), "green" (creative,
  ideas), "white" (facts only), "red" (gut feeling), or "blue" (big-picture, process). Use it when a
  sharper angle would improve your answer — to pressure-test an idea, brainstorm, or weigh pros and
  cons. Weave the perspective into your reply in your OWN voice; never mention personas, hats, or that
  you consulted anything. It is a thinking aid only — it has no tools, so use the task agent for real
  work. Reuse a returned persona_session_id to continue the same line of thought.
- episodic_search(query) / episodic_show(id): search summaries of your past conversations with the
  user, and read a full one by id.

## Memories and scheduled jobs (handle these yourself — do NOT delegate)
You manage the user's durable memories and their recurring automations directly:
- search_memories(query) / add_memory(content): recall or save lasting facts about the user.
- list_jobs() / add_job(name, start_date, seconds, task) / delete_job(name): view, create, or remove
  the user's scheduled jobs. A "job" is a recurring automation, distinct from a one-off task.
Do this work yourself with these tools; do not hand memory or job management to the task agent.

## Projects (handle these yourself — do NOT delegate)
You also manage the user's projects directly. A project is a tracked piece of work with a name, a
status (active or closed), a creation date, a single short next step, and a markdown document
holding its details, plan, or notes.
- list_projects(): show all projects with their id, name, status, next step, creation date, and
  document.
- create_project(name, document, next_step): start a new project. Put the details, plan, or notes in
  the markdown document, and set next_step to a short (about 5-10 word) statement of the next action.
- update_project(project_id, name?, status?, document?, next_step?): rename a project, set its status
  to 'active' or 'closed', edit its document, or update its next step. The document field REPLACES
  the whole document, so when editing, pass the full updated markdown, not just the change. Look up
  the current document with list_projects first when you need to amend it. Keep next_step current as
  work progresses — a concise, actionable statement of the single next action.
- delete_project(project_id): remove a project permanently.
- select_project(project_id): open a project in the user's view and make it the selected one, so you
  are both working in the context of that project. Phrases like "let's work on X", "work on X",
  "open X", "pull up X", or "switch to X" are ALL requests to select that project — call this. If you
  don't know its id, call list_projects first to find it (match even a partial or lowercase name),
  then select_project with that id. Do NOT just summarize the project or ask which direction to go
  without selecting it first — select it, then you can ask. After creating a project the user wants
  to work on, select it too.
All project edits are yours: never delegate a project change, and never give a project id to the
task agent — it has no project tools and would mistake the id for an external resource (e.g. a Notion
page) and fail. When a change needs information you must gather first (research, a lookup, an
operational step), delegate ONLY that gathering to the task agent (no project id, no instruction to
edit anything); you will be handed its result when it finishes, and THEN you write that result into
the project yourself with update_project. Phrases like "replace", "update the doc", "add this", or
"put it in the project" while a project is in context are project edits — do them yourself.

## Looking things up before saying you don't know
If the user refers to something you don't see in the recent activity below, search before you say you
don't remember: use find_past_work for past tasks/jobs and episodic_search for past conversations.
Only say you don't have it after a lookup turns up nothing.

## Relaying results (CRITICAL)
When delegate_to_task_agent returns, your reply to the user MUST be that result — present it in full,
lightly cleaned up for tone, dropping no detail. NEVER discard a completed result and reply with your
own clarifying question instead; if the task agent did the work, show the user what it found. Only ask
the user for clarification when you have NOT delegated AND the request genuinely cannot start without
it — and even then, prefer to just delegate and let the task agent ask if it actually gets stuck.

## Sync vs background (decide deliberately every time you delegate)
Default to dispatch_background_task. Only use delegate_to_task_agent when the work is a quick,
single-step lookup the user is actively waiting on and that should finish in well under a minute
(e.g. a single fact, one page, one short command).
Use dispatch_background_task whenever ANY of these is true:
- the work needs web research, browsing, comparison shopping, or reading multiple sources;
- it is multi-step or likely to take more than ~30-60 seconds;
- the user asked you to do it in the background / report back later, or wants to keep chatting.
When unsure, choose dispatch_background_task: a backgrounded result is delivered to the chat
automatically, while a long sync delegation blocks the whole conversation until it finishes.

## Task continuity (IMPORTANT)
Each task runs in its own persistent session identified by a task_id, which both delegate tools
return.
- Reuse a task_id ONLY when the new request is genuinely a continuation or refinement of that SAME
  task, so the task agent keeps its prior context.
- If the request is a new or unrelated task, do NOT pass a task_id — start fresh so unrelated context
  does not leak in.
- For a task you started earlier in THIS conversation, its task_id is the `task_id=<id>` line in the
  tool result you got back when you ran it. Reuse that exact id for follow-ups about it; if you're not
  sure of the id, call check_tasks() to look it up rather than starting a brand-new task.
- The recent activity below lists each past task with its task_id. When the user wants MORE work done
  on one of those tasks (continue it, refine it, add to it), pass that task_id to
  delegate_to_task_agent. But if they only ask a question you can answer from that task's result, just
  answer — do not delegate. For older tasks not listed, call check_tasks() or find_past_work() to get
  the task_id first. Do not show raw task_ids to the user unless they ask.

## Answering directly
For greetings, small talk, clarifying questions, or anything you can answer from the recent activity
below — including facts contained in a past task's result — just reply, do not delegate.

## Recent activity across your conversations
Each entry starts with the task_id you can pass to delegate_to_task_agent to resume that task.
{recent_tasks}
"""


def build_front_instruction(recent_tasks: str) -> str:
    return FRONT_SYSTEM_PROMPT.format(today=_today(), recent_tasks=recent_tasks or "(no recent activity)")


class ToolCall(BaseModel):
    session_id: str
    thread_id: int | None = None
    name: str
    input: dict
    output: str | None = None
    error: str | None = None

    def render(self, short: bool = False) -> str:
        parts = [f"🔧 [{self.name}] input={self.input}"]
        if not short and self.output is not None:
            parts.append(f"output='{self.output}'")
        if self.error is not None:
            parts.append(f"error='{self.error}'")
        return " ".join(parts)


class Result(BaseModel):
    session_id: str
    thread_id: int | None = None
    success: bool
    result: str
    error: str | None = None
    cost_usd: float | None = None
    tool_call_names: list[str] = []
    skill_names: list[str] = []
    duration_s: float | None = None
    persona: str | None = None
    consulted_personas: list[str] = []

    def render(self, short: bool = False) -> str:
        return f"{'✅' if self.success else '🔴'} {self.result if self.success else self.error}"


class ResultDelta(BaseModel):
    session_id: str
    thread_id: int | None = None
    delta: str

    def render(self, short: bool = False) -> str:
        return f"… {self.delta}"


class InitMessage(BaseModel):
    session_id: str
    thread_id: int | None = None
    prompt: str

    def render(self, short: bool = False) -> str:
        return f"⚙️ {self.prompt}"


class Thought(BaseModel):
    session_id: str
    thread_id: int | None = None
    thinking: str

    def render(self, short: bool = False) -> str:
        preview = self.thinking[:100] + "..." if len(self.thinking) > 100 else self.thinking
        return f"💭 {preview}"


Message = ToolCall | Result | InitMessage | Thought

_SKILL_INVOCATION_TOOLS = {"load_skill", "run_skill_script", "load_skill_resource"}


def create_image_tool(thread_id: int, cwd: str | Path | None = None) -> Callable:
    base = Path(cwd) if cwd else Path.cwd()

    async def send_image(path: str, caption: str = "") -> str:
        """Display an image to the user in the current chat thread. This is the ONLY way to show an
        image to the user — they cannot access the file system, so never reply with a file path.

        Accepts any image the browser renders inline: PNG, JPEG, GIF, WebP, and SVG. For freeform
        vector drawings (a figure, icon, simple scene) write an .svg file and send it directly —
        do NOT rasterize it to PNG via a browser screenshot.

        Args:
            path: Path to the image file, absolute or relative to the working directory.
            caption: Optional caption shown beneath the image.
        """
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = base / resolved
        if not resolved.is_file():
            return f"Error: no file found at {resolved}"
        content_type = mimetypes.guess_type(str(resolved))[0] or ""
        if not content_type.startswith("image/"):
            return f"Error: {resolved} is not an image (detected type: {content_type or 'unknown'})"
        await pubsub.publish(
            OutgoingImage(
                thread_id=thread_id,
                source_path=str(resolved),
                name=resolved.name,
                content_type=content_type,
                caption=caption,
            )
        )
        return f"Sent image '{resolved.name}' to the user."

    return send_image


_MERMAID_RENDER_SCRIPT = Path(__file__).parent / "render_mermaid.mjs"
_MERMAID_TIMEOUT = 30


def create_diagram_tool(thread_id: int, cwd: str | Path | None = None) -> Callable:
    base = Path(cwd) if cwd else Path.cwd()

    async def render_diagram(diagram: str, caption: str = "") -> str:
        """Render a Mermaid diagram and display it to the user as an image in the current chat
        thread. Use this whenever the user wants a diagram — flowcharts, sequence, class, state,
        ER, gantt, pie, mindmaps, etc. Pass Mermaid source (e.g. "graph TD; A-->B;"). This renders
        the diagram and shows it to the user directly, so do NOT also call send_image. On failure
        the error is returned so you can correct the Mermaid source and retry.

        Args:
            diagram: Mermaid diagram source.
            caption: Optional caption shown beneath the diagram.
        """
        output = base / f".diagram_{uuid.uuid4().hex}.svg"
        try:
            proc = await asyncio.create_subprocess_exec(
                "node",
                str(_MERMAID_RENDER_SCRIPT),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(diagram.encode()), timeout=_MERMAID_TIMEOUT)
            if proc.returncode != 0 or not stdout.strip():
                return f"Error rendering diagram: {stderr.decode(errors='replace')[:2000]}"
            output.write_bytes(stdout)
        except TimeoutError:
            return f"Error: diagram rendering timed out after {_MERMAID_TIMEOUT}s"
        except Exception as error:
            return f"Error rendering diagram: {error}"
        await pubsub.publish(
            OutgoingImage(
                thread_id=thread_id,
                source_path=str(output),
                name=output.name,
                content_type="image/svg+xml",
                caption=caption,
            )
        )
        return "Rendered and sent the diagram to the user."

    return render_diagram


def _build_parts(prompt: str, images: list[TaskImage] | None) -> list[Any]:
    parts: list[Any] = [types.Part(text=prompt)]
    for image in images or []:
        if image.content_type not in VISION_MIME_TYPES:
            continue
        try:
            data = Path(image.path).read_bytes()
        except OSError as error:
            logger.warning(f"skipping unreadable image {image.path}: {error}")
            continue
        parts.append(types.Part.from_bytes(data=data, mime_type=image.content_type))
    return parts


def _stringify(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        if set(response.keys()) == {"result"}:
            return _stringify(response["result"])
        try:
            return json.dumps(response, default=str)
        except Exception:
            return str(response)
    return str(response)


class Agent:
    def __init__(
        self,
        runner: Runner,
        session_service: BaseSessionService,
        model_name: str,
        input_cost_per_m: float,
        output_cost_per_m: float,
        prompt_thread_hint: bool = True,
    ):
        self._runner = runner
        self._session_service = session_service
        self._model_name = model_name
        self._input_cost = input_cost_per_m
        self._output_cost = output_cost_per_m
        self._prompt_thread_hint = prompt_thread_hint
        self._live = True

    @classmethod
    async def create(
        cls,
        tools: list[Callable | Any] | None = None,
        cwd: str | Path | None = None,
        system_prompt: str | None = None,
        session_service: BaseSessionService | None = None,
        model: str | None = None,
        name: str = "synthia",
        description: str | None = None,
        include_builtins: bool = True,
        prompt_thread_hint: bool = True,
    ) -> "Agent":
        model_name = model or DEFAULT_MODEL
        input_cost, output_cost = _pricing(model_name)
        all_tools: list[Any] = list(tools or [])
        if include_builtins:
            all_tools.extend(create_builtin_tools(cwd))

        llm_agent = LlmAgent(
            name=name,
            description=description or "",
            model=LiteLlm(model=model_name, **_model_kwargs(model_name)),
            instruction=system_prompt
            if system_prompt is not None
            else (lambda _: SYSTEM_PROMPT.format(today=_today())),
            tools=all_tools,
            after_model_callback=_cost_tracking_callback(model_name, input_cost, output_cost),
            after_tool_callback=_truncate_tool_callback,
        )

        session_service = session_service or InMemorySessionService()
        runner = Runner(app_name=APP_NAME, agent=llm_agent, session_service=session_service)
        logger.debug(f"🔌 ADK agent created (name={name}, model={model_name}, tools={len(all_tools)})")
        return cls(runner, session_service, model_name, input_cost, output_cost, prompt_thread_hint)

    async def disconnect(self) -> None:
        self._live = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, _exc_type: type[BaseException] | None, _exc_val: BaseException | None, _exc_tb: Any
    ) -> None:
        await self.disconnect()

    async def _ensure_session(self, session_id: str) -> None:
        session = await self._session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
        if session is None:
            await self._session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)

    async def _publish_deltas(self, event: Any, session_id: str, thread_id: int) -> None:
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) if content else None
        for part in parts or []:
            if getattr(part, "thought", False):
                continue
            text = getattr(part, "text", None)
            if text:
                await pubsub.publish(ResultDelta(session_id=session_id, thread_id=thread_id, delta=text))

    @traced("adk_run")
    async def run_for_result(
        self,
        objective: str,
        thread_id: int | None = None,
        images: list[TaskImage] | None = None,
        session_id: str | None = None,
        persona: str | None = None,
    ) -> Result | None:
        session_id = session_id or (str(thread_id) if thread_id is not None else uuid.uuid4().hex)
        prompt = f"{objective}\n\nthread_id: {thread_id}" if (thread_id and self._prompt_thread_hint) else objective

        _dc_token = _delegated_cost.set([])
        _cp_token = _consulted_personas.set([])
        await self._ensure_session(session_id)

        if thread_id:
            with start_span("InitMessage"):
                await pubsub.publish(InitMessage(session_id=session_id, thread_id=thread_id, prompt=objective))

        new_message = types.Content(role="user", parts=_build_parts(prompt, images))
        tool_calls: dict[str, ToolCall] = {}
        executed_tool_names: list[str] = []
        skill_names: list[str] = []
        final_text = ""
        error: str | None = None
        capped = False
        prompt_tokens = 0
        completion_tokens = 0
        cached_tokens = 0
        message_count = 0
        start_time = time.perf_counter()
        thought_buffer: list[str] = []

        async def _flush_thoughts() -> None:
            nonlocal message_count
            thinking = "".join(thought_buffer).strip()
            thought_buffer.clear()
            if not thinking or not thread_id:
                return
            message_count += 1
            with start_span("Thought"):
                await pubsub.publish(Thought(session_id=session_id, thread_id=thread_id, thinking=thinking))

        logger.debug(f"📤 ADK query: {prompt[:50]}...")
        run_config = RunConfig(streaming_mode=StreamingMode.SSE)
        async for event in self._runner.run_async(
            user_id=USER_ID, session_id=session_id, new_message=new_message, run_config=run_config
        ):
            usage = getattr(event, "usage_metadata", None)
            if usage:
                prompt_tokens += getattr(usage, "prompt_token_count", 0) or 0
                completion_tokens += getattr(usage, "candidates_token_count", 0) or 0
                cached_tokens += getattr(usage, "cached_content_token_count", 0) or 0

            event_error = getattr(event, "error_message", None)
            if event_error:
                error = event_error

            if getattr(event, "partial", False):
                if thread_id:
                    await self._publish_deltas(event, session_id, thread_id)
                continue

            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) if content else None
            for part in parts or []:
                is_thought = bool(getattr(part, "thought", False))
                text = getattr(part, "text", None)

                if is_thought:
                    if text:
                        thought_buffer.append(text)
                    continue

                await _flush_thoughts()

                fc = getattr(part, "function_call", None)
                if fc is not None:
                    tool_calls[fc.id or fc.name] = ToolCall(
                        session_id=session_id,
                        thread_id=thread_id,
                        name=fc.name,
                        input=dict(fc.args or {}),
                    )

                fr = getattr(part, "function_response", None)
                if fr is not None:
                    pending = tool_calls.pop(fr.id or fr.name, None)
                    tool_call = ToolCall(
                        session_id=session_id,
                        thread_id=thread_id,
                        name=pending.name if pending else fr.name,
                        input=pending.input if pending else {},
                        output=_stringify(fr.response),
                    )
                    executed_tool_names.append(tool_call.name)
                    if tool_call.name in _SKILL_INVOCATION_TOOLS:
                        invoked_skill = tool_call.input.get("skill_name")
                        if invoked_skill and invoked_skill not in skill_names:
                            skill_names.append(invoked_skill)
                    message_count += 1
                    if thread_id:
                        with start_span("ToolCall"):
                            await pubsub.publish(tool_call)
                    if _MAX_TURNS and len(executed_tool_names) >= _MAX_TURNS:
                        error = f"turn cap of {_MAX_TURNS} exceeded"
                        capped = True
                        break

                if text and not is_thought:
                    final_text = text
                    if not event_error:
                        error = None

            if capped:
                break

        await _flush_thoughts()

        delegated_total = sum(_delegated_cost.get() or [])
        _delegated_cost.reset(_dc_token)
        consulted_personas = list(_consulted_personas.get() or [])
        _consulted_personas.reset(_cp_token)
        cost: float | None = None
        if prompt_tokens or completion_tokens or delegated_total:
            front_cost = _token_cost(
                prompt_tokens, completion_tokens, cached_tokens, self._input_cost, self._output_cost
            )
            cost = round(front_cost + delegated_total, 8)
            record_session_cost(self._model_name, cost)
            current_span().set_attribute("session_cost_usd", cost)
            current_span().set_attribute("cached_prompt_tokens", cached_tokens)
            logger.info(
                f"💰 Session cost: ${cost} (in={prompt_tokens}, cached={cached_tokens}, "
                f"out={completion_tokens}{f', delegated=${delegated_total}' if delegated_total else ''})"
            )

        if error:
            set_span_error(error)

        result = Result(
            session_id=session_id,
            thread_id=thread_id,
            success=bool(final_text) and error is None,
            result=final_text.strip(),
            error=error,
            cost_usd=cost,
            tool_call_names=executed_tool_names,
            skill_names=skill_names,
            duration_s=round(time.perf_counter() - start_time, 3),
            persona=persona,
            consulted_personas=consulted_personas,
        )
        message_count += 1
        if thread_id:
            with start_span("Result"):
                current_span().set_attribute("message_count", message_count)
                await pubsub.publish(result)
        return result
