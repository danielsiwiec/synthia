import random

from loguru import logger
from telegram import Bot, ReactionTypeEmoji, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from synthia.helpers.pubsub import pubsub
from synthia.service.models import ProgressNotification
from synthia.service.task import TaskRequest, TaskService
from synthia.telegram.helpers import send_message


class Telegram:
    def __init__(self, token: str, telegram_users_map: dict[str, str], admin_chat_id: str, task_service: TaskService):
        self.authorized_chat_ids = set(telegram_users_map.values())
        self.telegram_users_map = telegram_users_map
        self.admin_chat_id = admin_chat_id
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
        pubsub.subscribe(ProgressNotification, self._handle_progress_notification)

    async def start(self):
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            await self._send_message_to_chat(text="_Synthia connected 👋_", chat_id=self.admin_chat_id)
        except Exception as _e:
            logger.error(f"telegram application failed to start: {_e}")

    async def stop(self):
        await self.application.stop()
        await self.application.shutdown()

    def _is_authorized(self, update: Update) -> bool:
        chat_id = str(update.message.chat.id)
        if chat_id not in self.authorized_chat_ids:
            logger.warning(f"unauthorized chat_id {chat_id} from user {update.message.from_user.id}")
            return False
        return True

    def _get_user_from_chat_id(self, chat_id: str) -> str | None:
        return next((user for user, user_chat_id in self.telegram_users_map.items() if user_chat_id == chat_id), None)

    async def _send_message_to_chat(self, text: str, chat_id: str):
        def _create_message_sender():
            async def message_sender(msg_text: str):
                await self.bot.send_message(chat_id=chat_id, text=msg_text, parse_mode=ParseMode.HTML)

            return message_sender

        message_sender = _create_message_sender()
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

        chat_id = str(update.message.chat.id)
        if not context.args:
            await self._send_message_to_chat(text="Please provide a task description", chat_id=chat_id)
            return
        user = self._get_user_from_chat_id(chat_id)
        result = await self.task_service.process_task(TaskRequest(task=" ".join(context.args), user=user), resume=False)
        await self._send_message_to_chat(text=result.result, chat_id=chat_id)

    async def _message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update):
            return

        await self._acknowledge_message(update, context)

        if not update.message.text:
            return

        chat_id = str(update.message.chat.id)
        user = self._get_user_from_chat_id(chat_id)
        result = await self.task_service.process_task(TaskRequest(task=update.message.text, user=user), resume=True)
        await self._send_message_to_chat(text=result.result, chat_id=chat_id)

    async def _handle_progress_notification(self, notification: ProgressNotification):
        try:
            emojis = ["⚙️", "🤔", "💭", "💡"]
            emoji = random.choice(emojis)
            if notification.user and notification.user in self.telegram_users_map:
                await self._send_message_to_chat(
                    text=f"{emoji} _{notification.summary}_",
                    chat_id=self.telegram_users_map[notification.user],
                )
        except Exception as _e:
            logger.error(f"failed to send progress notification: {_e}", exc_info=True)
