from loguru import logger

from synthia.agents.claude import Message
from synthia.helpers.pubsub import pubsub

pubsub.subscribe(Message, lambda message: logger.info(f"{message.render()}"))
# pubsub.subscribe(ClaudeMessage, lambda message: logger.info(f"claude message: {message}"))
