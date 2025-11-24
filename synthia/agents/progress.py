from collections import defaultdict

from claude_agent_sdk import SystemMessage
from langchain_openai import ChatOpenAI

from synthia.agents.claude import InitMessage, Message, Result
from synthia.helpers.pubsub import pubsub
from synthia.service.models import ProgressNotification, TaskCompletion

_messages_by_session: dict[str, list[str]] = defaultdict(list)
_message_counts: dict[str, int] = defaultdict(int)
_enabled_sessions: set[str] = set()


async def _summarize_messages(session_id: str):
    if session_id not in _messages_by_session or not _messages_by_session[session_id]:
        return

    messages = _messages_by_session[session_id][-3:]
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
    summary = await model.ainvoke(prompt)

    if hasattr(summary, "content"):
        content = summary.content
        if isinstance(content, str):
            summary_text = content
        elif isinstance(content, list) and content and isinstance(content[0], str):
            summary_text = content[0]
        else:
            summary_text = str(content)
    else:
        summary_text = str(summary)

    await pubsub.publish(ProgressNotification(session_id=session_id, summary=summary_text))


async def analyze_progress(message: Message):
    if isinstance(message, SystemMessage):
        return

    if isinstance(message, InitMessage):
        _enabled_sessions.add(message.session_id)
        return

    if isinstance(message, Result):
        _enabled_sessions.discard(message.session_id)
        if message.session_id in _messages_by_session:
            del _messages_by_session[message.session_id]
        if message.session_id in _message_counts:
            del _message_counts[message.session_id]
        return

    session_id = message.session_id

    if session_id not in _enabled_sessions:
        return

    message_text = message.render() if hasattr(message, "render") else str(message)
    _messages_by_session[session_id].append(message_text)
    _message_counts[session_id] += 1

    if len(_messages_by_session[session_id]) > 3:
        _messages_by_session[session_id] = _messages_by_session[session_id][-3:]

    if _message_counts[session_id] % 3 == 0:
        await _summarize_messages(session_id)


async def _handle_task_completion(completion: TaskCompletion):
    session_id = completion.session_id

    if session_id in _messages_by_session:
        messages = _messages_by_session[session_id][-3:]
        if messages:
            await _summarize_messages(session_id)

        del _messages_by_session[session_id]
        if session_id in _message_counts:
            del _message_counts[session_id]
        _enabled_sessions.discard(session_id)


pubsub.subscribe(Message, analyze_progress)
pubsub.subscribe(TaskCompletion, _handle_task_completion)
