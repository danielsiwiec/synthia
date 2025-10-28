from loguru import logger
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from synthia.agents.agents import TaskAgentException
from synthia.agents.models import AgentSelection
from synthia.helpers.pubsub import pubsub
from synthia.service.task import TaskRequest, TaskService
from synthia.telegram.helpers import send_message


class Telegram:
    def __init__(self, token: str, chat_id: str, task_service: TaskService):
        self.chat_id = chat_id
        self.task_service = task_service
        self.application = Application.builder().token(token).build()
        self.application.add_handler(CommandHandler("task", self._task_handler, has_args=True))
        self.application.add_handler(
            MessageHandler(
                callback=self._message_handler,
                filters=filters.TEXT & ~filters.COMMAND,
            )
        )
        self.bot = Bot(token=token)
        pubsub.subscribe(AgentSelection, self.on_agent_selection)

    async def on_agent_selection(self, agent_selection: AgentSelection):
        if agent_selection.agent_name:
            await self._send_message(f"**Selected agent: {agent_selection.agent_name}**")
        else:
            await self._send_message("**No agent selected**")

    async def start(self):
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            await self._send_message("*Synthia connected 👋*")
        except Exception as _e:
            logger.error(f"Telegram application failed to start: {_e}")

    async def stop(self):
        await self.application.stop()
        await self.application.shutdown()

    def _is_authorized(self, update: Update) -> bool:
        if update.message.from_user.id != int(self.chat_id):
            logger.debug(f"Unauthorized user {update.message.from_user.id}")
            return False
        return True

    async def _send_message(self, text: str):
        async def message_sender(text: str):
            await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=ParseMode.HTML)

        await send_message(message_sender, text)

    async def _task_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return

        if not context.args:
            await self._send_message("Please provide a task description")
            return

        try:
            result = await self.task_service.process_task(TaskRequest(task=" ".join(context.args)), resume=False)
            await self._send_message(result.result)
        except TaskAgentException as e:
            await self._send_message(str(e))

    async def _message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return

        if not update.message.text:
            return

        try:
            result = await self.task_service.process_task(TaskRequest(task=update.message.text), resume=True)
            await self._send_message(result.result)
        except TaskAgentException as e:
            await self._send_message(str(e))
