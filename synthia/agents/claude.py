from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    UserMessage,
)
from pydantic import BaseModel

from synthia.helpers.pubsub import pubsub

SYSTEM_PROMPT = """
Your name is Synthia. You are a helpful assistant that can help with tasks and questions.

## Browser downloads
All browser downloads, by default, are saved in the `/mounts/downloads` folder.
"""


class ToolCall(BaseModel):
    session_id: str
    name: str
    input: dict
    output: str | None = None
    error: str | None = None

    def render(self) -> str:
        parts = ["🔧"]
        parts.append(f"[{self.name}]")
        parts.append(f"input={self.input}")
        if self.output is not None:
            parts.append(f"output='{self.output}'")
        if self.error is not None:
            parts.append(f"error='{self.error}'")
        return " ".join(parts)


class Result(BaseModel):
    session_id: str
    success: bool
    result: str
    error: str | None = None

    def render(self) -> str:
        parts = ["✅" if self.success else "🔴"]
        parts.append(self.result if self.success else self.error)
        return " ".join(parts)


class InitMessage(BaseModel):
    session_id: str
    prompt: str

    def render(self) -> str:
        parts = ["⚙️"]
        parts.append(self.prompt)
        return " ".join(parts)


Message = ToolCall | Result | InitMessage


class ClaudeAgent:
    def __init__(self, user: str, memory_mcp_server: dict[str, Any] | None = None):
        self.user = user
        self._memory_mcp_server = memory_mcp_server

    def _parse_message(
        self, message: Any, tool_calls: dict[str, ToolCall], objective: str, session_id: str
    ) -> Any | None:
        if isinstance(message, ResultMessage):
            return Result(
                session_id=message.session_id, success=message.subtype == "success", result=message.result.strip()
            )

        elif isinstance(message, (UserMessage, AssistantMessage)):
            content_blocks = getattr(message, "content", [])
            if not isinstance(content_blocks, list):
                return None

            for block in content_blocks:
                block_type = type(block).__name__

                if block_type == "ToolUseBlock":
                    tool_use_id = getattr(block, "id", None)
                    name = getattr(block, "name", "")
                    input_data = getattr(block, "input", {})

                    if tool_use_id:
                        tool_calls[tool_use_id] = ToolCall(session_id=session_id, name=name, input=input_data)

                elif block_type == "ToolResultBlock":
                    tool_use_id = getattr(block, "tool_use_id", None)
                    output = getattr(block, "content", "")
                    is_error = getattr(block, "is_error", False)
                    error = "Error occurred" if is_error else None

                    if isinstance(output, list):
                        output = str(output)
                    elif output is None:
                        output = ""

                    if tool_use_id and tool_use_id in tool_calls:
                        tool_call = tool_calls[tool_use_id]
                        completed_tool_call = ToolCall(
                            session_id=tool_call.session_id,
                            name=tool_call.name,
                            input=tool_call.input,
                            output=output.strip(),
                            error=error,
                        )
                        del tool_calls[tool_use_id]
                        return completed_tool_call

        return None

    async def run(
        self,
        objective: str,
        resume_from_session: str | None = None,
    ) -> AsyncIterator[Any]:
        project_root = Path(__file__).parent.parent.parent
        claude_sessions_dir = project_root / "claude_sessions"
        claude_sessions_dir.mkdir(parents=True, exist_ok=True)

        mcp_servers = {
            "browser": {"type": "http", "url": "http://host.docker.internal:8931/mcp"},
        }
        if self._memory_mcp_server:
            mcp_servers["memory"] = self._memory_mcp_server

        options = ClaudeAgentOptions(
            cwd=str(claude_sessions_dir),
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
        async for message in client.receive_messages():
            await pubsub.publish(message)
            if isinstance(message, SystemMessage):
                session_id = message.data["session_id"]
                yield InitMessage(session_id=message.data["session_id"], prompt=objective)
                continue
            if session_id is None:
                raise ValueError("Session ID is not set")
            if transformed := self._parse_message(message, tool_calls, objective, session_id):
                yield transformed
                if isinstance(transformed, Result):
                    break

    async def run_for_result(
        self,
        objective: str,
        resume_from_session: str | None = None,
    ) -> Result | None:
        async for message in self.run(objective, resume_from_session=resume_from_session):
            await pubsub.publish(message)
            if isinstance(message, Result):
                return message
