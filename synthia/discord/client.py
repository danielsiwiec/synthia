import asyncio
import random
import re

import discord
from discord import app_commands
from loguru import logger
from table2ascii import table2ascii

from synthia.helpers.pubsub import pubsub
from synthia.service.models import (
    AdminNotification,
    ImageCreated,
    ProgressNotification,
    StopTaskRequest,
    TaskRequest,
    TaskResponse,
)
from synthia.telemetry import current_span, traced


def _truncate_message(message: str, max_len: int = 200) -> str:
    return message[:max_len] if len(message) <= max_len else message[: max_len - 3] + "..."


def _format_tables(text: str) -> str:
    lines = text.split("\n")
    result = []
    table_lines = []
    in_table = False

    for line in lines:
        is_table_line = re.match(r"^\|.+\|$", line.strip())
        if is_table_line:
            if not in_table:
                in_table = True
            table_lines.append(line)
        else:
            if in_table:
                result.append(_convert_markdown_table(table_lines))
                table_lines = []
                in_table = False
            result.append(line)

    if in_table:
        result.append(_convert_markdown_table(table_lines))

    return "\n".join(result)


def _strip_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text


def _convert_markdown_table(lines: list[str]) -> str:
    rows = []
    header = None
    for i, line in enumerate(lines):
        cells = [_strip_markdown(cell.strip()) for cell in line.strip().strip("|").split("|")]
        if i == 0:
            header = cells
        elif i == 1 and all(re.match(r"^[-:]+$", cell) for cell in cells):
            continue
        else:
            rows.append(cells)
    return "```\n" + table2ascii(header=header, body=rows) + "\n```"


def _split_message(text: str, max_length: int = 2000) -> list[str]:
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    current_chunk: str = ""

    for line in text.split("\n"):
        if len(line) > max_length:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            for i in range(0, len(line), max_length):
                chunks.append(line[i : i + max_length])
        elif len(current_chunk) + len(line) + 1 <= max_length:
            current_chunk = f"{current_chunk}\n{line}" if current_chunk else line
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


class Discord:
    def __init__(self, token: str, authorized_channels: list[str], admin_channel_id: str):
        self.token = token
        self._authorized_channels = set(authorized_channels)
        self.admin_channel_id = admin_channel_id

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)
        self._tree = app_commands.CommandTree(self._client)

        self._ready_event = asyncio.Event()
        self._setup_handlers()
        pubsub.subscribe(ProgressNotification, self._handle_progress_notification)
        pubsub.subscribe(AdminNotification, self._handle_admin_notification)
        pubsub.subscribe(TaskResponse, self._handle_task_response)
        pubsub.subscribe(ImageCreated, self._handle_image_created)

    def _setup_handlers(self):
        @self._client.event
        async def on_ready():
            await self._tree.sync()
            await self._send_message_to_channel(text="*Synthia connected 👋*", channel_id=self.admin_channel_id)
            self._ready_event.set()

        @self._tree.command(name="stop", description="Stop the current task")
        async def stop_command(interaction: discord.Interaction):
            if not isinstance(interaction.channel, discord.Thread):
                await interaction.response.send_message("⚠️ /stop can only be used inside a task thread", ephemeral=True)
                return

            if not self._is_authorized_thread(interaction.channel):
                await interaction.response.send_message("Unauthorized", ephemeral=True)
                return

            await interaction.response.defer()

            await pubsub.publish(StopTaskRequest(thread_id=interaction.channel.id))
            await interaction.followup.send("🛑 task stopped")

        @self._client.event
        async def on_message(message: discord.Message):
            if message.author == self._client.user:
                return

            if message.content.startswith("/"):
                return

            if isinstance(message.channel, discord.Thread):
                if self._is_authorized_thread(message.channel):
                    await self._handle_thread_message(message)

            elif isinstance(message.channel, discord.TextChannel):
                if str(message.channel.id) in self._authorized_channels:
                    await self._handle_channel_message(message)

    async def start(self):
        try:
            self._task = asyncio.create_task(self._client.start(self.token))
            await asyncio.wait_for(self._ready_event.wait(), timeout=10)
        except Exception as _e:
            logger.error(f"discord bot failed to start: {_e}")

    async def stop(self):
        await self._client.close()
        if hasattr(self, "_task"):
            self._task.cancel()

    def _is_authorized(self, interaction: discord.Interaction) -> bool:
        channel_id = str(interaction.channel_id)
        if channel_id not in self._authorized_channels:
            logger.warning(f"unauthorized channel_id {channel_id} from user {interaction.user.id}")
            return False
        return True

    def _is_authorized_thread(self, thread: discord.Thread) -> bool:
        parent_channel_id = str(thread.parent_id)
        if parent_channel_id not in self._authorized_channels:
            logger.warning(f"unauthorized thread parent channel_id {parent_channel_id}")
            return False
        return True

    async def _send_message_to_thread(self, thread: discord.Thread, text: str):
        logger.debug(f"📤 Sending message to thread {thread.id}: {text[:50]}...")
        for chunk in _split_message(_format_tables(text)):
            await thread.send(chunk, suppress_embeds=True)

    async def _send_message_to_channel(self, text: str, channel_id: str, silent: bool = False):
        channel = self._client.get_channel(int(channel_id))
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.error(f"channel {channel_id} not found or not a text channel")
            return
        for chunk in _split_message(_format_tables(text)):
            await channel.send(chunk, suppress_embeds=True, silent=silent)

    async def _add_message_reaction(self, message: discord.Message):
        emojis = ["👍", "👌", "🫡", "🚀", "✨"]
        emoji = random.choice(emojis)
        try:
            await message.add_reaction(emoji)
        except Exception as _e:
            logger.error(f"failed to react to message: {_e}", exc_info=True)

    @traced("discord_thread_message")
    async def _handle_thread_message(self, message: discord.Message):
        current_span().update_name(_truncate_message(message.content))
        logger.debug(f"📥 Discord message received in thread {message.channel.id}: {message.content[:50]}...")
        asyncio.create_task(self._add_message_reaction(message))
        await pubsub.publish(TaskRequest(task=message.content, thread_id=message.channel.id))

    @traced("discord_channel_message")
    async def _handle_channel_message(self, message: discord.Message):
        current_span().update_name(_truncate_message(message.content))
        logger.debug(f"📥 Discord message received in channel {message.channel.id}: {message.content[:50]}...")
        asyncio.create_task(self._add_message_reaction(message))
        thread_name = message.content[:100] if len(message.content) <= 100 else message.content[:97] + "..."
        thread = await message.create_thread(name=thread_name)
        await pubsub.publish(TaskRequest(task=message.content, thread_id=thread.id))

    async def _handle_progress_notification(self, notification: ProgressNotification):
        emojis = ["⚙️", "🤔", "💭", "💡", "🏃‍♂️"]
        emoji = random.choice(emojis)
        if notification.thread_id:
            thread = self._client.get_channel(notification.thread_id)
            if thread and isinstance(thread, discord.Thread):
                await thread.send(f"{emoji} *{notification.summary}*", silent=True)

    async def _handle_admin_notification(self, notification: AdminNotification):
        await self._send_message_to_channel(
            text=notification.content, channel_id=self.admin_channel_id, silent=notification.silent
        )

    async def _handle_task_response(self, response: TaskResponse):
        thread = self._client.get_channel(response.thread_id)
        if thread and isinstance(thread, discord.Thread):
            result_str = str(response.result) if response.result is not None else ""
            if result_str.strip():
                await self._send_message_to_thread(thread, result_str)
            else:
                logger.warning(f"skipping empty response for thread {response.thread_id}")

    async def _handle_image_created(self, image_created: ImageCreated):
        thread = self._client.get_channel(image_created.thread_id)
        if thread and isinstance(thread, discord.Thread):
            try:
                await thread.send(file=discord.File(image_created.filename))
            except FileNotFoundError:
                logger.error(f"image file not found: {image_created.filename}")
            except Exception as _e:
                logger.error(f"failed to send image: {_e}", exc_info=True)
