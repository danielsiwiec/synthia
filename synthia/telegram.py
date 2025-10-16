from telegram import Bot, Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from loguru import logger


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.chat_id = chat_id
        self.bot = Bot(token=token)
        self.application = Application.builder().token(token).build()
        self.application.add_handler(MessageHandler(callback=self._on_message, filters=filters.TEXT))

    async def start(self):
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            await self.send_message(message="Synthia connected 👋")
        except Exception as _e:
            logger.error(f"Telegram application failed to start: {_e}")

    async def send_message(self, message: str):
        await self.bot.send_message(chat_id=self.chat_id, text=message)

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message is None or (update.message.from_user and update.message.from_user.id != int(self.chat_id)):
            return
        message = update.message.text
        await self.send_message(message=f"Right back at you: {message}")
