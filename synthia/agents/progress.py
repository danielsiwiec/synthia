import os
from collections import defaultdict
from typing import cast

from langchain_openai import ChatOpenAI
from loguru import logger
from pydantic import BaseModel

from synthia.agents.agent import InitMessage, Message, Result
from synthia.helpers.pubsub import Consumer, pubsub
from synthia.service.models import ProgressNotification


class Summary(BaseModel):
    summary: str


class ProgressAnalyzer(Consumer[Message]):
    def __init__(self):
        self._openai_key_present = bool(os.getenv("OPENAI_API_KEY"))
        if not self._openai_key_present:
            logger.warning("OpenAI key absent - progress analysis disabled")
        self._messages_by_session: dict[str, list[str]] = defaultdict(list)

    async def _summarize_messages(self, session_id: str, thread_id: int | None):
        messages = self._messages_by_session[session_id]
        if not messages:
            return

        combined_messages = "\n".join(messages)

        model = ChatOpenAI(model="gpt-4o-mini", temperature=0)  # type: ignore[arg-type]
        prompt = (
            "Summarize the following activity messages into a very short, concise phrase "
            "in present continuous tense (just the core action, no extra details, use -ing form). "
            "Always respond with only one statement. If there are multiple actions, use only the most relevant one: "
            f"{combined_messages}"
        )
        result = cast(Summary, await model.with_structured_output(Summary).ainvoke(prompt))

        await pubsub.publish(ProgressNotification(session_id=session_id, summary=result.summary, thread_id=thread_id))

    async def consume(self, message: Message):
        if not self._openai_key_present:
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
