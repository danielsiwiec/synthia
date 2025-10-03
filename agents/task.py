from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
from pydantic import BaseModel


class ToolCall(BaseModel):
    name: str
    input: dict
    output: str | None = None
    error: str | None = None


class Result(BaseModel):
    status: str
    result: str


async def process_objective(objective: str) -> list[Any]:
    options = ClaudeAgentOptions(permission_mode="bypassPermissions")
    client = ClaudeSDKClient(options)

    await client.connect()
    await client.query(objective)

    all_messages = []
    async for message in client.receive_messages():
        all_messages.append(message)
        if isinstance(message, ResultMessage):
            break

    return all_messages
