import asyncio
from unittest.mock import Mock

from daimos.helpers.pubsub import PubSub


class TaskAgentMessage:
    def __init__(self, content: str):
        self.content = content


class DummyMessage:
    def __init__(self, content: str):
        self.content = content


async def test_pubsub_with_multiple_handlers():
    pubsub = PubSub()

    handler1 = Mock()
    handler2 = Mock()

    def sync_handler1(msg):
        handler1(msg)

    def sync_handler2(msg):
        handler2(msg)

    pubsub.subscribe(TaskAgentMessage, sync_handler1)
    pubsub.subscribe(TaskAgentMessage, sync_handler2)

    await pubsub.start()
    await pubsub.publish(TaskAgentMessage, TaskAgentMessage("test message"))

    await asyncio.sleep(0.1)  # Give time for dispatch

    handler1.assert_called_once()
    handler2.assert_called_once()
    await pubsub.stop()


async def test_pubsub_with_no_handlers():
    pubsub = PubSub()

    await pubsub.start()
    await pubsub.publish(TaskAgentMessage, TaskAgentMessage("test message"))

    await asyncio.sleep(0.1)  # Give time for dispatch

    assert True
    await pubsub.stop()


async def test_pubsub_handler_not_called_for_different_event():
    pubsub = PubSub()

    handler = Mock()

    def sync_handler(msg):
        handler(msg)

    pubsub.subscribe(TaskAgentMessage, sync_handler)

    await pubsub.start()
    await pubsub.publish(DummyMessage, DummyMessage("test message"))

    await asyncio.sleep(0.1)  # Give time for dispatch

    handler.assert_not_called()
    await pubsub.stop()


async def test_pubsub_mixed_sync_async_handlers():
    pubsub = PubSub()

    sync_handler = Mock()
    async_handler = Mock()

    def sync_fn(msg):
        sync_handler(msg)

    async def async_fn(msg):
        async_handler(msg)

    pubsub.subscribe(TaskAgentMessage, sync_fn)
    pubsub.subscribe(TaskAgentMessage, async_fn)

    await pubsub.start()
    await pubsub.publish(TaskAgentMessage, TaskAgentMessage("test message"))

    await asyncio.sleep(0.1)  # Give time for dispatch

    sync_handler.assert_called_once()
    async_handler.assert_called_once()
    await pubsub.stop()
