from collections import defaultdict

from loguru import logger
from openai import AsyncOpenAI

from synthia.agents.agent import InitMessage, Message, Result
from synthia.helpers.pubsub import Consumer, pubsub
from synthia.service.models import ProgressNotification


class ProgressAnalyzer(Consumer[Message]):
    def __init__(self, openai_client: AsyncOpenAI | None):
        self._client = openai_client
        self._messages_by_session: dict[str, list[str]] = defaultdict(list)
        if not self._client:
            logger.warning("OPENAI_API_KEY not set - progress summarization disabled")

    async def _summarize_messages(self, session_id: str, thread_id: int | None):
        messages = self._messages_by_session[session_id]
        if not messages or not self._client:
            return

        combined_messages = "\n".join(messages)

        prompt = (
            "Summarize the following activity messages into a very short, concise phrase "
            "in present continuous tense (just the core action, no extra details, use -ing form). "
            "Always respond with only one statement. If there are multiple actions, use only the most relevant one: "
            f"{combined_messages}"
        )
        response = await self._client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        summary = response.choices[0].message.content

        await pubsub.publish(ProgressNotification(session_id=session_id, summary=summary, thread_id=thread_id))

    async def consume(self, message: Message):
        if not self._client:
            return

        if isinstance(message, InitMessage):
            self._messages_by_session[message.session_id] = []
            return

        if isinstance(message, Result):
            self._messages_by_session.pop(message.session_id, None)
            return

        session_id = message.session_id

        if session_id not in self._messages_by_session:
            return

        self._messages_by_session[session_id].append(message.render(short=True))

        if len(self._messages_by_session[session_id]) % 3 == 0:
            await self._summarize_messages(session_id, message.thread_id)
            self._messages_by_session[session_id] = []
