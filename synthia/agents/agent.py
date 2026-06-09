import asyncio
import json
import mimetypes
import os
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Self

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
DEFAULT_MODEL = os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4-6")

_INPUT_COST_PER_M = float(os.getenv("LLM_INPUT_COST_PER_M", "3.0"))
_OUTPUT_COST_PER_M = float(os.getenv("LLM_OUTPUT_COST_PER_M", "15.0"))
_THINKING_BUDGET = int(os.getenv("LLM_THINKING_BUDGET", "2048"))
_PROMPT_CACHING = os.getenv("LLM_PROMPT_CACHING", "1") != "0"
_CACHE_READ_MULTIPLIER = 0.1


def _is_anthropic(model_name: str) -> bool:
    return "claude" in model_name or "anthropic" in model_name


def _model_kwargs(model_name: str) -> dict[str, Any]:
    if not _is_anthropic(model_name):
        return {}
    kwargs: dict[str, Any] = {}
    if _PROMPT_CACHING:
        kwargs["cache_control_injection_points"] = [
            {"location": "message", "role": "system"},
            {"location": "message", "index": -1},
        ]
    if _THINKING_BUDGET > 0:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": _THINKING_BUDGET}
        kwargs["extra_headers"] = {"anthropic-beta": "interleaved-thinking-2025-05-14"}
    return kwargs


def _token_cost(prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> float:
    uncached_tokens = max(prompt_tokens - cached_tokens, 0)
    return round(
        (uncached_tokens / 1_000_000) * _INPUT_COST_PER_M
        + (cached_tokens / 1_000_000) * _INPUT_COST_PER_M * _CACHE_READ_MULTIPLIER
        + (completion_tokens / 1_000_000) * _OUTPUT_COST_PER_M,
        8,
    )


def _cost_tracking_callback(model_name: str) -> Callable[[Any, Any], Any]:
    def _after_model(callback_context: Any, llm_response: Any) -> None:
        usage = getattr(llm_response, "usage_metadata", None)
        if usage is None:
            return None
        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
        cached_tokens = getattr(usage, "cached_content_token_count", 0) or 0
        if not (prompt_tokens or completion_tokens):
            return None
        cost = _token_cost(prompt_tokens, completion_tokens, cached_tokens)
        record_call_cost(model_name, cost)
        current_span().set_attribute("gen_ai.usage.cost_usd", cost)
        return None

    return _after_model


SYSTEM_PROMPT = f"""
Your name is Synthia. You are a helpful assistant that can help with tasks and questions.

# Today is {datetime.now().strftime("%Y-%m-%d")}.

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
    def __init__(self, runner: Runner, session_service: BaseSessionService, model_name: str):
        self._runner = runner
        self._session_service = session_service
        self._model_name = model_name
        self._live = True

    @classmethod
    async def create(
        cls,
        tools: list[Callable | Any] | None = None,
        cwd: str | Path | None = None,
        system_prompt: str | None = None,
        session_service: BaseSessionService | None = None,
        model: str | None = None,
    ) -> "Agent":
        model_name = model or DEFAULT_MODEL
        all_tools: list[Any] = list(tools or [])
        all_tools.extend(create_builtin_tools(cwd))

        llm_agent = LlmAgent(
            name="synthia",
            model=LiteLlm(model=model_name, **_model_kwargs(model_name)),
            instruction=system_prompt if system_prompt is not None else SYSTEM_PROMPT,
            tools=all_tools,
            after_model_callback=_cost_tracking_callback(model_name),
        )

        session_service = session_service or InMemorySessionService()
        runner = Runner(app_name=APP_NAME, agent=llm_agent, session_service=session_service)
        logger.debug(f"🔌 ADK agent created (model={model_name}, tools={len(all_tools)})")
        return cls(runner, session_service, model_name)

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
        self, objective: str, thread_id: int | None = None, images: list[TaskImage] | None = None
    ) -> Result | None:
        session_id = str(thread_id) if thread_id is not None else uuid.uuid4().hex
        prompt = f"{objective}\n\nthread_id: {thread_id}" if thread_id else objective

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

            if getattr(event, "error_message", None):
                error = event.error_message

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

                if text and not is_thought:
                    final_text = text

        await _flush_thoughts()

        cost: float | None = None
        if prompt_tokens or completion_tokens:
            cost = _token_cost(prompt_tokens, completion_tokens, cached_tokens)
            record_session_cost(self._model_name, cost)
            current_span().set_attribute("session_cost_usd", cost)
            current_span().set_attribute("cached_prompt_tokens", cached_tokens)
            logger.info(
                f"💰 Session cost: ${cost} (in={prompt_tokens}, cached={cached_tokens}, out={completion_tokens})"
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
        )
        message_count += 1
        if thread_id:
            with start_span("Result"):
                current_span().set_attribute("message_count", message_count)
                await pubsub.publish(result)
        return result
