import asyncio
import random
import re

import discord
from discord import app_commands
from loguru import logger
from table2ascii import table2ascii

from synthia.helpers.pubsub import pubsub
from synthia.service.models import AdminNotification, ProgressNotification
from synthia.service.task import TaskRequest, TaskService


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


def _convert_markdown_table(lines: list[str]) -> str:
    rows = []
    header = None
    for i, line in enumerate(lines):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if i == 0:
            header = cells
        elif i == 1 and all(re.match(r"^[-:]+$", cell) for cell in cells):
            continue
        else:
            rows.append(cells)
    return "```\n" + table2ascii(header=header, body=rows) + "\n```"


class Discord:
    def __init__(self, token: str, discord_users_map: dict[str, str], admin_channel_id: str, task_service: TaskService):
        self.token = token
        self.authorized_channel_ids = set(discord_users_map.values())
        self.discord_users_map = discord_users_map
        self.admin_channel_id = admin_channel_id
        self.task_service = task_service

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)
        self._tree = app_commands.CommandTree(self._client)

        self._setup_handlers()
        pubsub.subscribe(ProgressNotification, self._handle_progress_notification)
        pubsub.subscribe(AdminNotification, self._handle_admin_notification)

    def _setup_handlers(self):
        @self._client.event
        async def on_ready():
            await self._tree.sync()
            logger.info(f"discord bot logged in as {self._client.user}")
            await self._send_message_to_channel(text="*Synthia connected 👋*", channel_id=self.admin_channel_id)

        @self._tree.command(name="task", description="Execute a task")
        @app_commands.describe(description="The task to execute")
        async def task_command(interaction: discord.Interaction, description: str):
            if not self._is_authorized(interaction):
                await interaction.response.send_message("Unauthorized", ephemeral=True)
                return

            await interaction.response.send_message(f"**Task:** {description}")
            message = await interaction.original_response()

            thread_name = description[:100] if len(description) <= 100 else description[:97] + "..."
            thread = await message.create_thread(name=thread_name)

            request = TaskRequest(task=description, thread_id=str(thread.id))
            result = await self.task_service.process_task(request, resume=False)
            await self._send_message_to_thread(thread, result.result)

        @self._tree.command(name="stop", description="Stop the current task")
        async def stop_command(interaction: discord.Interaction):
            if not isinstance(interaction.channel, discord.Thread):
                await interaction.response.send_message("⚠️ /stop can only be used inside a task thread", ephemeral=True)
                return

            if not self._is_authorized_thread(interaction.channel):
                await interaction.response.send_message("Unauthorized", ephemeral=True)
                return

            await interaction.response.defer()

            stopped = await self.task_service.stop_current_task()
            if stopped:
                await interaction.followup.send("🛑 task stopped")

        @self._client.event
        async def on_message(message: discord.Message):
            if message.author == self._client.user:
                return

            if message.content.startswith("/"):
                return

            if isinstance(message.channel, discord.Thread):
                if not self._is_authorized_thread(message.channel):
                    return

                await self._add_message_reaction(message)

                request = TaskRequest(task=message.content, thread_id=str(message.channel.id))
                result = await self.task_service.process_task(request, resume=True)
                await self._send_message_to_thread(message.channel, result.result)
            elif isinstance(message.channel, discord.TextChannel):
                channel_id = str(message.channel.id)
                if channel_id not in self.authorized_channel_ids:
                    return

                await self._add_message_reaction(message)

                thread_name = message.content[:100] if len(message.content) <= 100 else message.content[:97] + "..."
                thread = await message.create_thread(name=thread_name)

                request = TaskRequest(task=message.content, thread_id=str(thread.id))
                result = await self.task_service.process_task(request, resume=False)
                await self._send_message_to_thread(thread, result.result)

    async def start(self):
        try:
            self._task = asyncio.create_task(self._client.start(self.token))
            await asyncio.sleep(2)
        except Exception as _e:
            logger.error(f"discord bot failed to start: {_e}")

    async def stop(self):
        await self._client.close()
        if hasattr(self, "_task"):
            self._task.cancel()

    def _is_authorized(self, interaction: discord.Interaction) -> bool:
        channel_id = str(interaction.channel_id)
        if channel_id not in self.authorized_channel_ids:
            logger.warning(f"unauthorized channel_id {channel_id} from user {interaction.user.id}")
            return False
        return True

    def _is_authorized_thread(self, thread: discord.Thread) -> bool:
        parent_channel_id = str(thread.parent_id)
        if parent_channel_id not in self.authorized_channel_ids:
            logger.warning(f"unauthorized thread parent channel_id {parent_channel_id}")
            return False
        return True

    def _get_user_from_channel_id(self, channel_id: str) -> str | None:
        return next(
            (user for user, user_channel_id in self.discord_users_map.items() if user_channel_id == channel_id), None
        )

    async def _send_message_to_thread(self, thread: discord.Thread, text: str):
        await thread.send(_format_tables(text), suppress_embeds=True)

    async def _send_message_to_channel(self, text: str, channel_id: str, silent: bool = False):
        channel = self._client.get_channel(int(channel_id))
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.error(f"channel {channel_id} not found or not a text channel")
            return
        await channel.send(_format_tables(text), suppress_embeds=True, silent=silent)

    async def _send_followup(self, interaction: discord.Interaction, text: str):
        await interaction.followup.send(_format_tables(text), suppress_embeds=True)

    async def _add_reaction(self, interaction: discord.Interaction):
        emojis = ["👍", "👌", "🫡"]
        emoji = random.choice(emojis)
        try:
            if interaction.message:
                await interaction.message.add_reaction(emoji)
        except Exception as _e:
            logger.error(f"failed to react to message: {_e}", exc_info=True)

    async def _add_message_reaction(self, message: discord.Message):
        emojis = ["👍", "👌", "🫡"]
        emoji = random.choice(emojis)
        try:
            await message.add_reaction(emoji)
        except Exception as _e:
            logger.error(f"failed to react to message: {_e}", exc_info=True)

    async def _handle_progress_notification(self, notification: ProgressNotification):
        emojis = ["⚙️", "🤔", "💭", "💡"]
        emoji = random.choice(emojis)
        if notification.thread_id:
            thread = self._client.get_channel(int(notification.thread_id))
            if thread and isinstance(thread, discord.Thread):
                await thread.send(f"{emoji} *{notification.summary}*", silent=True)

    async def _handle_admin_notification(self, notification: AdminNotification):
        await self._send_message_to_channel(text=notification.content, channel_id=self.admin_channel_id)
