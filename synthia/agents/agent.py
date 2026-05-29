import json
import os
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types
from loguru import logger
from pydantic import BaseModel

from synthia.agents.builtins import create_builtin_tools
from synthia.helpers.pubsub import pubsub
from synthia.metrics import record_call_cost, record_session_cost
from synthia.telemetry import current_span, start_span, traced

APP_NAME = "synthia"
USER_ID = "default"
DEFAULT_MODEL = os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4-6")

_INPUT_COST_PER_M = float(os.getenv("LLM_INPUT_COST_PER_M", "3.0"))
_OUTPUT_COST_PER_M = float(os.getenv("LLM_OUTPUT_COST_PER_M", "15.0"))
_THINKING_BUDGET = int(os.getenv("LLM_THINKING_BUDGET", "2048"))


def _model_kwargs(model_name: str) -> dict[str, Any]:
    if _THINKING_BUDGET <= 0 or ("claude" not in model_name and "anthropic" not in model_name):
        return {}
    return {
        "thinking": {"type": "enabled", "budget_tokens": _THINKING_BUDGET},
        "extra_headers": {"anthropic-beta": "interleaved-thinking-2025-05-14"},
    }


def _token_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        (prompt_tokens / 1_000_000) * _INPUT_COST_PER_M + (completion_tokens / 1_000_000) * _OUTPUT_COST_PER_M,
        8,
    )


def _cost_tracking_callback(model_name: str) -> Callable[[Any, Any], Any]:
    def _after_model(callback_context: Any, llm_response: Any) -> None:
        usage = getattr(llm_response, "usage_metadata", None)
        if usage is None:
            return None
        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
        if not (prompt_tokens or completion_tokens):
            return None
        cost = _token_cost(prompt_tokens, completion_tokens)
        record_call_cost(model_name, cost)
        current_span().set_attribute("gen_ai.usage.cost_usd", cost)
        return None

    return _after_model


SYSTEM_PROMPT = f"""
Your name is Synthia. You are a helpful assistant that can help with tasks and questions.

# Today is {datetime.now().strftime("%Y-%m-%d")}.

## Shell and files
Use the run_bash tool to execute shell commands and run scripts. Use read_file and write_file for file access.

## Browser downloads
All browser downloads, by default, are saved in the `/mounts/downloads` folder.

## Web access
Use the fetch_url tool to retrieve web pages. If a page is not accessible (JavaScript-rendered,
login-gated, or blocked), use the playwright browser tools, which drive a real Chrome.
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

    def render(self, short: bool = False) -> str:
        return f"{'✅' if self.success else '🔴'} {self.result if self.success else self.error}"


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

    @traced("adk_run")
    async def run_for_result(self, objective: str, thread_id: int | None = None) -> Result | None:
        session_id = str(thread_id) if thread_id is not None else uuid.uuid4().hex
        prompt = f"{objective}\n\nthread_id: {thread_id}" if thread_id else objective

        await self._ensure_session(session_id)

        if thread_id:
            with start_span("InitMessage"):
                await pubsub.publish(InitMessage(session_id=session_id, thread_id=thread_id, prompt=objective))

        new_message = types.Content(role="user", parts=[types.Part(text=prompt)])
        tool_calls: dict[str, ToolCall] = {}
        final_text = ""
        error: str | None = None
        prompt_tokens = 0
        completion_tokens = 0
        message_count = 0

        logger.debug(f"📤 ADK query: {prompt[:50]}...")
        async for event in self._runner.run_async(user_id=USER_ID, session_id=session_id, new_message=new_message):
            usage = getattr(event, "usage_metadata", None)
            if usage:
                prompt_tokens += getattr(usage, "prompt_token_count", 0) or 0
                completion_tokens += getattr(usage, "candidates_token_count", 0) or 0

            if getattr(event, "error_message", None):
                error = event.error_message

            if getattr(event, "partial", False):
                continue

            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) if content else None
            for part in parts or []:
                is_thought = bool(getattr(part, "thought", False))
                text = getattr(part, "text", None)

                if is_thought and text and thread_id:
                    message_count += 1
                    with start_span("Thought"):
                        await pubsub.publish(Thought(session_id=session_id, thread_id=thread_id, thinking=text))

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
                    message_count += 1
                    if thread_id:
                        with start_span("ToolCall"):
                            await pubsub.publish(tool_call)

                if text and not is_thought:
                    final_text = text

        cost: float | None = None
        if prompt_tokens or completion_tokens:
            cost = _token_cost(prompt_tokens, completion_tokens)
            record_session_cost(self._model_name, cost)
            current_span().set_attribute("session_cost_usd", cost)
            logger.info(f"💰 Session cost: ${cost} (in={prompt_tokens}, out={completion_tokens})")

        result = Result(
            session_id=session_id,
            thread_id=thread_id,
            success=bool(final_text) and error is None,
            result=final_text.strip(),
            error=error,
            cost_usd=cost,
        )
        message_count += 1
        if thread_id:
            with start_span("Result"):
                current_span().set_attribute("message_count", message_count)
                await pubsub.publish(result)
        return result
