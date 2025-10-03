import uuid
from collections.abc import AsyncIterator
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


def _parse_message(message: Any, tool_calls: dict[str, ToolCall], session_id: str, objective: str) -> Any | None:
    if isinstance(message, SystemMessage):
        return InitMessage(session_id=session_id, prompt=objective)

    elif isinstance(message, ResultMessage):
        return Result(session_id=session_id, success=message.subtype == "success", result=message.result)

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

                if tool_use_id and tool_use_id in tool_calls:
                    tool_call = tool_calls[tool_use_id]
                    completed_tool_call = ToolCall(
                        session_id=tool_call.session_id,
                        name=tool_call.name,
                        input=tool_call.input,
                        output=output,
                        error=error,
                    )
                    del tool_calls[tool_use_id]
                    return completed_tool_call

    return None


async def run(objective: str) -> AsyncIterator[Any]:
    options = ClaudeAgentOptions(permission_mode="bypassPermissions")
    client = ClaudeSDKClient(options)
    session_id = str(uuid.uuid4())

    await client.connect()
    await client.query(objective)

    tool_calls = {}  # tool_use_id -> ToolCall

    async for message in client.receive_messages():
        if transformed := _parse_message(message, tool_calls, session_id, objective):
            yield transformed
            if isinstance(transformed, Result):
                break


async def run_for_result(objective: str) -> Result | None:
    async for message in run(objective):
        if isinstance(message, Result):
            return message
