from loguru import logger

from daimos.agents.claude import Message
from daimos.helpers.pubsub import pubsub

pubsub.subscribe(Message, lambda message: logger.info(f"{message.render()}"))
# pubsub.subscribe(ClaudeMessage, lambda message: logger.info(f"claude message: {message}"))
