from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, UserMessage
from loguru import logger
from pydantic import BaseModel


class ToolCall(BaseModel):
    name: str
    input: dict
    output: str | None = None
    error: str | None = None


class Result(BaseModel):
    status: str
    result: str


def _transform_messages(all_messages: list[Any]) -> list[Any]:
    transformed_messages = []
    tool_calls = {}  # tool_use_id -> ToolCall

    for message in all_messages:
        if isinstance(message, ResultMessage):
            status = getattr(message, "subtype", "unknown")
            result = getattr(message, "result", "")
            transformed_messages.append(Result(status=status, result=result))

        elif isinstance(message, (UserMessage, AssistantMessage)):
            content_blocks = getattr(message, "content", [])
            if not isinstance(content_blocks, list):
                continue

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
                        transformed_messages.append(completed_tool_call)
                        del tool_calls[tool_use_id]

    return transformed_messages


async def process_objective(objective: str) -> list[Any]:
    options = ClaudeAgentOptions(permission_mode="bypassPermissions")
    client = ClaudeSDKClient(options)

    await client.connect()
    await client.query(objective)

    all_messages = []
    async for message in client.receive_messages():
        logger.debug(f"Received message: {message}")
        all_messages.append(message)
        if isinstance(message, ResultMessage):
            break

    transformed_messages = _transform_messages(all_messages)
    return transformed_messages
