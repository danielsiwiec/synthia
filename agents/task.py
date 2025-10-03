from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from loguru import logger


async def process_objective(objective: str) -> AsyncIterator[Any]:
    options = ClaudeAgentOptions(permission_mode="bypassPermissions")
    client = ClaudeSDKClient(options)

    logger.debug("connecting to Claude SDK client")
    await client.connect()
    logger.debug("querying Claude SDK client")
    await client.query(objective)

    async for message in client.receive_messages():
        logger.debug(f"received message: {message}")
        yield message
