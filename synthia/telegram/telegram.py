import random

from loguru import logger
from telegram import Bot, ReactionTypeEmoji, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

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

    async def start(self):
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            await self._send_message("*Synthia connected 👋*")
        except Exception as _e:
            logger.error(f"telegram application failed to start: {_e}")

    async def stop(self):
        await self.application.stop()
        await self.application.shutdown()

    def _is_authorized(self, update: Update) -> bool:
        if update.message.from_user.id != int(self.chat_id):
            logger.warning(f"unauthorized user {update.message.from_user.id}")
            return False
        return True

    async def _send_message(self, text: str):
        async def message_sender(text: str):
            await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=ParseMode.HTML)

        await send_message(message_sender, text)

    async def _acknowledge_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        emojis = ["👍", "👌", "🫡"]
        emoji = random.choice(emojis)
        try:
            await update.message.set_reaction(reaction=[ReactionTypeEmoji(emoji=emoji)])
        except Exception as _e:
            logger.error(f"failed to react to message: {_e}", exc_info=True)

    async def _task_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return

        await self._acknowledge_message(update, context)

        if not context.args:
            await self._send_message("Please provide a task description")
            return

        result = await self.task_service.process_task(TaskRequest(task=" ".join(context.args)), resume=False)
        await self._send_message(result.result)

    async def _message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return

        await self._acknowledge_message(update, context)

        if not update.message.text:
            return

        result = await self.task_service.process_task(TaskRequest(task=update.message.text), resume=True)
        await self._send_message(result.result)
