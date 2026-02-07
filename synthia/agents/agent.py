from datetime import datetime
from pathlib import Path
from typing import Any, Self

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    McpServerConfig,
    ResultMessage,
    SystemMessage,
    UserMessage,
    query,
)
from loguru import logger
from pydantic import BaseModel

from synthia.helpers.pubsub import pubsub
from synthia.metrics import record_session_cost
from synthia.telemetry import current_span, start_span, traced

SYSTEM_PROMPT = f"""
Your name is Synthia. You are a helpful assistant that can help with tasks and questions.

# Today is {datetime.now().strftime("%Y-%m-%d")}.

## Browser downloads
All browser downloads, by default, are saved in the `/mounts/downloads` folder.

## Web Search
If you encounter access issues using the web search tool, try using the browser instead.
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


class ClaudeAgent:
    def __init__(self, client: ClaudeSDKClient | None, options: ClaudeAgentOptions):
        self._client = client
        self._options = options
        self._session_id: str | None = None

    @classmethod
    async def create(
        cls,
        mcp_servers: dict[str, McpServerConfig] | None = None,
        cwd: str | Path | None = None,
        system_prompt: str | None = None,
        resume: str | None = None,
    ) -> "ClaudeAgent":
        if resume:
            options = ClaudeAgentOptions(
                cwd=cwd,
                setting_sources=["user", "project"],
                permission_mode="bypassPermissions",
                resume=resume,
            )
            return cls(None, options)
        options = ClaudeAgentOptions(
            cwd=cwd,
            setting_sources=["user", "project"],
            allowed_tools=["Skill"],
            permission_mode="bypassPermissions",
            system_prompt=system_prompt if system_prompt is not None else SYSTEM_PROMPT,
            mcp_servers=mcp_servers or {},
        )
        client = ClaudeSDKClient(options)
        logger.debug("🔌 Claude SDK connecting...")
        await client.connect()
        logger.debug("🔌 Claude SDK connected")
        return cls(client, options)

    async def disconnect(self) -> None:
        if not self._client:
            return
        try:
            await self._client.disconnect()
        except Exception:
            pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, _exc_type: type[BaseException] | None, _exc_val: BaseException | None, _exc_tb: Any
    ) -> None:
        await self.disconnect()

    def _parse_message(
        self, message: Any, tool_calls: dict[str, ToolCall], session_id: str, thread_id: int | None
    ) -> Any | None:
        if isinstance(message, ResultMessage):
            return Result(
                session_id=message.session_id,
                thread_id=thread_id,
                success=message.subtype == "success",
                result=message.result.strip(),
                cost_usd=getattr(message, "total_cost_usd", None),
            )

        if not isinstance(message, (UserMessage, AssistantMessage)):
            return None

        content_blocks = getattr(message, "content", [])
        if not isinstance(content_blocks, list):
            return None

        for block in content_blocks:
            match type(block).__name__:
                case "ThinkingBlock":
                    thinking = getattr(block, "thinking", "")
                    if thinking:
                        return Thought(
                            session_id=session_id,
                            thread_id=thread_id,
                            thinking=thinking,
                        )

                case "ToolUseBlock":
                    tool_use_id = getattr(block, "id", None)
                    if tool_use_id:
                        tool_calls[tool_use_id] = ToolCall(
                            session_id=session_id,
                            thread_id=thread_id,
                            name=getattr(block, "name", ""),
                            input=getattr(block, "input", {}),
                        )

                case "ToolResultBlock":
                    tool_use_id = getattr(block, "tool_use_id", None)
                    output = getattr(block, "content", "")
                    if isinstance(output, list):
                        output = str(output)
                    elif output is None:
                        output = ""

                    if tool_use_id and tool_use_id in tool_calls:
                        tool_call = tool_calls.pop(tool_use_id)
                        return ToolCall(
                            session_id=tool_call.session_id,
                            thread_id=tool_call.thread_id,
                            name=tool_call.name,
                            input=tool_call.input,
                            output=output.strip(),
                            error="Error occurred" if getattr(block, "is_error", False) else None,
                        )

        return None

    @traced("claude_run")
    async def run_for_result(self, objective: str, thread_id: int | None = None) -> Result | None:
        prompt = f"{objective}\n\nthread_id: {thread_id}" if thread_id else objective
        tool_calls: dict[str, ToolCall] = {}

        logger.debug(f"📤 Claude SDK query: {prompt[:50]}...")
        if self._client:
            await self._client.query(prompt=prompt)
            message_stream = self._client.receive_response()
        else:
            message_stream = query(prompt=prompt, options=self._options)
        logger.debug("📤 Claude SDK query sent, receiving messages...")

        message_count = 0
        result: Result | None = None
        async for message in message_stream:
            if thread_id:
                await pubsub.publish(message)
            if isinstance(message, SystemMessage):
                self._session_id = message.data["session_id"]
                message_count += 1
                if thread_id:
                    init_msg = InitMessage(session_id=self._session_id, thread_id=thread_id, prompt=objective)
                    with start_span("InitMessage"):
                        await pubsub.publish(init_msg)
                continue
            if isinstance(message, ResultMessage):
                logger.debug(f"📥 Claude SDK ResultMessage received: {(message.result or '')[:50]}...")
                cost = getattr(message, "total_cost_usd", None)
                usage = getattr(message, "usage", None)
                logger.info(f"💰 Session cost: ${cost}, usage: {usage}")
                if cost:
                    record_session_cost(cost)
            if self._session_id is None:
                raise ValueError("Session ID is not set")
            if transformed := self._parse_message(message, tool_calls, self._session_id, thread_id):
                message_count += 1
                if thread_id:
                    message_type = type(transformed).__name__
                    with start_span(message_type):
                        await pubsub.publish(transformed)
                if isinstance(transformed, Result) and result is None:
                    result = transformed
                    if thread_id:
                        current_span().set_attribute("message_count", message_count)
                        if transformed.cost_usd is not None:
                            current_span().set_attribute("session_cost_usd", transformed.cost_usd)
        return result
