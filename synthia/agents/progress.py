from collections import defaultdict
from typing import cast

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from synthia.agents.claude import InitMessage, Message, Result
from synthia.helpers.pubsub import pubsub
from synthia.service.models import ProgressNotification


class Summary(BaseModel):
    summary: str


_messages_by_session: dict[str, list[str]] = defaultdict(list)


async def _summarize_messages(session_id: str, thread_id: int | None):
    messages = _messages_by_session[session_id]
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


async def analyze_progress(message: Message):
    if isinstance(message, InitMessage):
        _messages_by_session[message.session_id] = []
        return

    if isinstance(message, Result):
        _messages_by_session.pop(message.session_id, None)
        return

    session_id = message.session_id

    if session_id not in _messages_by_session:
        return

    _messages_by_session[session_id].append(message.render(short=True))

    if len(_messages_by_session[session_id]) % 3 == 0:
        await _summarize_messages(session_id, message.thread_id)
        _messages_by_session[session_id] = []
