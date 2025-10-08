from unittest.mock import Mock

from daimos.helpers.events import EventEmitter, EventType


async def test_event_emitter_with_multiple_handlers():
    emitter = EventEmitter()

    handler1 = Mock()
    handler2 = Mock()

    emitter.on(EventType.TASK_AGENT_MESSAGE, handler1)
    emitter.on(EventType.TASK_AGENT_MESSAGE, handler2)

    await emitter.emit(EventType.TASK_AGENT_MESSAGE, "test message")

    handler1.assert_called_once_with("test message")
    handler2.assert_called_once_with("test message")


async def test_event_emitter_with_no_handlers():
    emitter = EventEmitter()

    await emitter.emit(EventType.TASK_AGENT_MESSAGE, "test message")

    assert True


async def test_event_emitter_handler_not_called_for_different_event():
    from enum import Enum

    emitter = EventEmitter()

    handler = Mock()

    emitter.on(EventType.TASK_AGENT_MESSAGE, handler)

    class DummyEventType(Enum):
        DUMMY = "dummy"

    await emitter.emit(EventType.DUMMY, "test message")

    handler.assert_not_called()
