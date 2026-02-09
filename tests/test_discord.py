import os
import secrets
from collections.abc import AsyncGenerator

import discord
import pytest
from dotenv import load_dotenv

from synthia.discord.client import Discord
from tests.helpers import await_until

load_dotenv()

TEST_CHANNEL_ID: str = "1445470336639570121"


@pytest.fixture
def discord_token() -> str:
    token: str | None = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        pytest.skip("DISCORD_BOT_TOKEN not set")
        raise RuntimeError("unreachable")
    return token


@pytest.fixture
async def received_messages(discord_token: str) -> AsyncGenerator[tuple[list[discord.Message], Discord]]:
    messages: list[discord.Message] = []

    client: Discord = Discord(
        token=discord_token,
        channel_id=TEST_CHANNEL_ID,
    )

    @client._client.event
    async def on_ready() -> None:
        await client._send_message_to_channel(text="*Synthia connected*", channel_id=client._channel_id)
        client._ready_event.set()

    @client._client.event
    async def on_message(message: discord.Message) -> None:
        if str(message.channel.id) == TEST_CHANNEL_ID:
            messages.append(message)

    await client.start()

    yield messages, client

    await client.stop()


async def test_discord_messaging(
    received_messages: tuple[list[discord.Message], Discord],
) -> None:
    messages: list[discord.Message]
    client: Discord
    messages, client = received_messages

    await await_until(
        lambda: any("Synthia connected" in m.content for m in messages),
        name="connected message",
        timeout=10,
    )
    connected_messages: list[discord.Message] = [m for m in messages if "Synthia connected" in m.content]
    assert len(connected_messages) >= 1, f"Expected 'Synthia connected' message, got: {[m.content for m in messages]}"

    random_text: str = f"test message {secrets.token_hex(8)}"
    await client._send_message_to_channel(text=random_text, channel_id=TEST_CHANNEL_ID)
    await await_until(
        lambda: any(random_text in m.content for m in messages),
        name="random text message",
        timeout=10,
    )
    matching_messages: list[discord.Message] = [m for m in messages if random_text in m.content]
    assert len(matching_messages) >= 1, f"Expected message with '{random_text}', got: {[m.content for m in messages]}"

    part1: str = secrets.token_hex(900)
    part2: str = secrets.token_hex(200)
    long_text: str = f"{part1}\n{part2}"
    initial_message_count: int = len(messages)
    await client._send_message_to_channel(text=long_text, channel_id=TEST_CHANNEL_ID)
    await await_until(
        lambda: len(messages) >= initial_message_count + 2,
        name="long message chunks",
        timeout=10,
    )
    new_messages: list[discord.Message] = messages[initial_message_count:]
    assert len(new_messages) == 2, f"Expected 2 messages, got {len(new_messages)}"
    assert new_messages[0].content == part1, "First chunk content mismatch"
    assert new_messages[1].content == part2, "Second chunk content mismatch"
