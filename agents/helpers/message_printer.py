from collections import defaultdict

from loguru import logger

from agents.claude import Message, Result, run_for_result


def log_message(message: Message) -> None:
    logger.info(f"Transformed message: {message}")


class Summarizer:
    def __init__(self):
        self.sessions = defaultdict(list)

    async def process_message(self, message: Message) -> None:
        session_id = message.session_id
        self.sessions[session_id].append(message)
        if isinstance(message, Result):
            if len(self.sessions) % 3 == 0:
                await self._summarize_session(session_id)

    async def _summarize_session(self, session_id: str) -> None:
        if not self.sessions[session_id]:
            return

        session_summary = "Please summarize the following conversation messages:\n\n"
        for i, msg in enumerate(self.sessions[session_id], 1):
            session_summary += f"Message {i}: {msg}\n"

        session_summary += "\nPlease provide a concise summary of the key points and outcomes."

        result = await run_for_result(session_summary)
        if result:
            logger.info(f"Session summary: {result.result}")
