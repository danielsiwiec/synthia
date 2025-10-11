from loguru import logger
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from daimos.agents.agents import TaskAgentException
from daimos.service.task import TaskRequest, TaskService


class Telegram:
    def __init__(self, token: str, chat_id: str, task_service: TaskService):
        self.chat_id = chat_id
        self.task_service = task_service
        self.application = Application.builder().token(token).build()
        self.application.add_handler(CommandHandler("task", self._task_handler, has_args=True))
        self.application.add_handler(MessageHandler(callback=self._message_handler, filters=filters.TEXT))

    async def send_message(self, message: str):
        await self.application.bot.send_message(text=message, chat_id=self.chat_id, parse_mode="Markdown")

    async def start(self):
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
        except Exception as _e:
            logger.error(f"Telegram application failed to start: {_e}")

    async def stop(self):
        await self.application.stop()
        await self.application.shutdown()

    async def _task_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.debug(f"Task handler called with context.args: {context.args}")
        if update.message.from_user.id != int(self.chat_id):
            logger.debug(f"Unauthorized user {update.message.from_user.id}")
            return

        if not context.args:
            await update.message.reply_text("Please provide a task description")
            return

        try:
            result = await self.task_service.process_task(TaskRequest(task=" ".join(context.args)), resume=False)
            await update.message.reply_text(result.result)
        except TaskAgentException as e:
            await update.message.reply_text(str(e))

    async def _message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.from_user.id != int(self.chat_id):
            logger.debug(f"Unauthorized user {update.message.from_user.id}")
            return

        if not update.message.text:
            return

        try:
            result = await self.task_service.process_task(TaskRequest(task=update.message.text), resume=True)
            await update.message.reply_text(result.result)
        except TaskAgentException as e:
            await update.message.reply_text(str(e))
