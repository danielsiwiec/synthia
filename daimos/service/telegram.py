from telegram import Bot, Update
from telegram.ext import ContextTypes

from daimos.service.task import TaskRequest, TaskService


class Telegram:
    def __init__(self, token: str, chat_id: str, task_service: TaskService):
        self.bot = Bot(token=token)
        self.chat_id = chat_id
        self.task_service = task_service

    async def send_message(self, message: str):
        await self.bot.send_message(text=message, chat_id=self.chat_id, parse_mode="Markdown")

    async def task_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Please provide a task description")
            return

        result = await self.task_service.process_task(TaskRequest(task=" ".join(context.args)))
        await update.message.reply_text(result.result)
