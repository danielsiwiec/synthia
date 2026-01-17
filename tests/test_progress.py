from dotenv import load_dotenv

from synthia.agents.agent import InitMessage, Message, ToolCall
from synthia.agents.progress import analyze_progress
from synthia.helpers.pubsub import pubsub
from synthia.service.models import ProgressNotification
from tests.helpers import await_until

load_dotenv()


async def test_progress(clean_pubsub):
    progress_notifications = []

    def capture_notification(notification: ProgressNotification):
        progress_notifications.append(notification)

    pubsub.subscribe(Message, analyze_progress)
    pubsub.subscribe(ProgressNotification, capture_notification)

    await pubsub.start()

    session_id = "test_session"

    await pubsub.publish(InitMessage(session_id=session_id, prompt="test"))

    await pubsub.publish(ToolCall(session_id=session_id, name="test_tool", input={"key": "value"}))
    await pubsub.publish(ToolCall(session_id=session_id, name="test_tool2", input={"key2": "value2"}))
    await pubsub.publish(ToolCall(session_id=session_id, name="test_tool3", input={"key3": "value3"}))

    await await_until(lambda: len(progress_notifications) == 1, "ProgressNotification", timeout=10)

    assert len(progress_notifications) == 1
    assert progress_notifications[0].session_id == session_id
    assert isinstance(progress_notifications[0].summary, str)
    assert len(progress_notifications[0].summary) > 0

    await pubsub.publish(ToolCall(session_id=session_id, name="test_tool4", input={"key4": "value4"}))
    await pubsub.publish(ToolCall(session_id=session_id, name="test_tool5", input={"key5": "value5"}))
    await pubsub.publish(ToolCall(session_id=session_id, name="test_tool6", input={"key6": "value6"}))

    await await_until(lambda: len(progress_notifications) >= 2, "ProgressNotification", timeout=30)
