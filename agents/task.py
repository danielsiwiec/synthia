from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, UserMessage
from pydantic import BaseModel

from agents.helpers.events import EventType


class ToolCall(BaseModel):
    name: str
    input: dict
    output: str | None = None
    error: str | None = None


class Result(BaseModel):
    status: str
    result: str


def _parse_message(message: Any, tool_calls: dict[str, ToolCall]) -> Any | None:
    if isinstance(message, ResultMessage):
        status = getattr(message, "subtype", "unknown")
        result = getattr(message, "result", "")
        return Result(status=status, result=result)

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
                    tool_calls[tool_use_id] = ToolCall(name=name, input=input_data)

            elif block_type == "ToolResultBlock":
                tool_use_id = getattr(block, "tool_use_id", None)
                output = getattr(block, "content", "")
                is_error = getattr(block, "is_error", False)
                error = "Error occurred" if is_error else None

                if tool_use_id and tool_use_id in tool_calls:
                    tool_call = tool_calls[tool_use_id]
                    completed_tool_call = ToolCall(
                        name=tool_call.name, input=tool_call.input, output=output, error=error
                    )
                    del tool_calls[tool_use_id]
                    return completed_tool_call

    return None


async def process_objective(objective: str, event_emitter=None) -> AsyncIterator[Any]:
    options = ClaudeAgentOptions(permission_mode="bypassPermissions")
    client = ClaudeSDKClient(options)

    await client.connect()
    await client.query(objective)

    tool_calls = {}  # tool_use_id -> ToolCall

    async for message in client.receive_messages():
        transformed = _parse_message(message, tool_calls)
        if transformed is not None:
            if event_emitter is not None:
                event_emitter.emit(EventType.MESSAGE_TRANSFORMED, transformed)
            yield transformed

        if isinstance(message, ResultMessage):
            break
