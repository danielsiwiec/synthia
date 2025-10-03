from typing import Any

from loguru import logger


def log_message(message: Any) -> None:
    logger.info(f"Transformed message: {message}")


class MessageCounter:
    def __init__(self):
        self.count = 0

    def count_message(self, message: Any) -> None:
        self.count += 1
        if self.count % 3 == 0:
            logger.info(f"Message count: {self.count}")
