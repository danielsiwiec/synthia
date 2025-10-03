from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
from loguru import logger

from agents.helpers.render import render_message


async def process_objective(objective: str) -> AsyncIterator[Any]:
    options = ClaudeAgentOptions(permission_mode="bypassPermissions")
    client = ClaudeSDKClient(options)

    await client.connect()
    await client.query(objective)

    async for message in client.receive_messages():
        logger.debug(render_message(message))
        yield message
