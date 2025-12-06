import os
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    McpServerConfig,
    ResultMessage,
    SystemMessage,
    UserMessage,
)
from claude_agent_sdk.types import McpHttpServerConfig
from loguru import logger
from pydantic import BaseModel

from synthia.helpers.pubsub import pubsub

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
        parts = ["🔧"]
        parts.append(f"[{self.name}]")
        parts.append(f"input={self.input}")
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

    def render(self, short: bool = False) -> str:
        parts = ["✅" if self.success else "🔴"]
        parts.append(self.result if self.success else self.error)
        return " ".join(parts)


class InitMessage(BaseModel):
    session_id: str
    thread_id: int | None = None
    prompt: str

    def render(self, short: bool = False) -> str:
        parts = ["⚙️"]
        parts.append(self.prompt)
        return " ".join(parts)


Message = ToolCall | Result | InitMessage


class ClaudeAgent:
    def __init__(
        self,
        mcp_servers: dict[str, McpServerConfig] | None = None,
        cwd: str | Path | None = None,
    ):
        self._mcp_servers = mcp_servers or {}
        self._cwd = cwd

    def _parse_message(
        self, message: Any, tool_calls: dict[str, ToolCall], session_id: str, thread_id: int | None
    ) -> Any | None:
        if isinstance(message, ResultMessage):
            return Result(
                session_id=message.session_id,
                thread_id=thread_id,
                success=message.subtype == "success",
                result=message.result.strip(),
            )

        if not isinstance(message, (UserMessage, AssistantMessage)):
            return None

        content_blocks = getattr(message, "content", [])
        if not isinstance(content_blocks, list):
            return None

        for block in content_blocks:
            match type(block).__name__:
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

    async def _run(
        self,
        objective: str,
        thread_id: int,
        resume_from_session: str | None = None,
    ) -> AsyncIterator[Any]:
        from synthia.agents.image.client import create_image_mcp_server

        mcp_servers = {
            "browser": McpHttpServerConfig(type="http", url="http://host.docker.internal:8931/mcp"),
            "google": McpHttpServerConfig(type="http", url="http://google-mcp:8000/mcp"),
            **self._mcp_servers,
        }

        if os.getenv("GEMINI_API_KEY"):
            logger.info("Enabling image MCP server...")
            mcp_servers["image"] = create_image_mcp_server(thread_id)

        options = ClaudeAgentOptions(
            cwd=self._cwd,
            setting_sources=["project"],
            allowed_tools=["Skill"],
            permission_mode="bypassPermissions",
            system_prompt=SYSTEM_PROMPT,
            resume=resume_from_session,
            mcp_servers=mcp_servers,
        )
        client = ClaudeSDKClient(options)

        await client.connect()
        await client.query(prompt=objective)

        tool_calls = {}  # tool_use_id -> ToolCall

        session_id = None
        try:
            async for message in client.receive_messages():
                await pubsub.publish(message)
                if isinstance(message, SystemMessage):
                    session_id = message.data["session_id"]
                    yield InitMessage(session_id=message.data["session_id"], thread_id=thread_id, prompt=objective)
                    continue
                if session_id is None:
                    raise ValueError("Session ID is not set")
                if transformed := self._parse_message(message, tool_calls, session_id, thread_id):
                    yield transformed
                    if isinstance(transformed, Result):
                        break
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def run_for_result(
        self,
        objective: str,
        thread_id: int,
        resume_from_session: str | None = None,
    ) -> Result | None:
        async for message in self._run(objective, resume_from_session=resume_from_session, thread_id=thread_id):
            await pubsub.publish(message)
            if isinstance(message, Result):
                return message
