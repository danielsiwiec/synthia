from typing import Any

from loguru import logger

from agents.claude import Result, run_for_result


def log_message(message: Any) -> None:
    logger.info(f"Transformed message: {message}")


class Summarizer:
    def __init__(self):
        self.messages = []

    async def process_message(self, message: Any) -> None:
        self.messages.append(message)
        if isinstance(message, Result):
            await self._summarize_session()

    async def _summarize_session(self) -> None:
        if not self.messages:
            return

        session_summary = "Please summarize the following conversation messages:\n\n"
        for i, msg in enumerate(self.messages, 1):
            session_summary += f"Message {i}: {msg}\n"

        session_summary += "\nPlease provide a concise summary of the key points and outcomes."

        async for result in run_for_result(session_summary):
            logger.info(f"Session summary: {result.result}")
