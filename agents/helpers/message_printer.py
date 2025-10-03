from typing import Any

from loguru import logger


def log_message(message: Any) -> None:
    logger.info(f"Transformed message: {message}")
