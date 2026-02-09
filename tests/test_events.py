import asyncio
from unittest.mock import Mock

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from synthia.helpers.pubsub import Consumer, PubSub


class TaskAgentMessage:
    def __init__(self, content: str):
        self.content = content


class DummyMessage:
    def __init__(self, content: str):
        self.content = content


class ParentMessage:
    def __init__(self, content: str):
        self.content = content


class ChildMessage(ParentMessage):
    def __init__(self, content: str, extra: str):
        super().__init__(content)
        self.extra = extra


class Foo:
    def __init__(self, value: str):
        self.value = value


class Bar:
    def __init__(self, value: int):
        self.value = value


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
    await pubsub.publish(TaskAgentMessage("test message"))

    await asyncio.sleep(0.1)  # Give time for dispatch

    handler1.assert_called_once()
    handler2.assert_called_once()
    await pubsub.stop()


async def test_pubsub_with_no_handlers():
    pubsub = PubSub()

    await pubsub.start()
    await pubsub.publish(TaskAgentMessage("test message"))

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
    await pubsub.publish(DummyMessage("test message"))

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
    await pubsub.publish(TaskAgentMessage("test message"))

    await asyncio.sleep(0.1)  # Give time for dispatch

    sync_handler.assert_called_once()
    async_handler.assert_called_once()
    await pubsub.stop()


async def test_pubsub_subtype_triggers_parent_handler():
    pubsub = PubSub()

    handler = Mock()

    def sync_handler(msg):
        handler(msg)

    pubsub.subscribe(ParentMessage, sync_handler)

    await pubsub.start()
    await pubsub.publish(ChildMessage("test message", "extra data"))

    await asyncio.sleep(0.1)

    handler.assert_called_once()
    assert isinstance(handler.call_args[0][0], ChildMessage)
    assert handler.call_args[0][0].content == "test message"
    assert handler.call_args[0][0].extra == "extra data"
    await pubsub.stop()


async def test_pubsub_union_type_subscription():
    pubsub = PubSub()

    FooOrBar = Foo | Bar

    handler = Mock()

    def sync_handler(msg):
        handler(msg)

    pubsub.subscribe(FooOrBar, sync_handler)

    await pubsub.start()

    await pubsub.publish(Foo("test foo"))
    await asyncio.sleep(0.1)

    assert handler.call_count == 1
    assert isinstance(handler.call_args[0][0], Foo)
    assert handler.call_args[0][0].value == "test foo"

    await pubsub.publish(Bar(42))
    await asyncio.sleep(0.1)

    assert handler.call_count == 2
    assert isinstance(handler.call_args[0][0], Bar)
    assert handler.call_args[0][0].value == 42

    await pubsub.stop()


async def test_pubsub_retains_otel_context_for_sync_handlers():
    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer("test")

    pubsub = PubSub()
    captured_span_ids: list[str] = []

    def sync_handler(msg):
        span = trace.get_current_span()
        span_context = span.get_span_context()
        if span_context.is_valid:
            captured_span_ids.append(format(span_context.span_id, "016x"))

    pubsub.subscribe(TaskAgentMessage, sync_handler)
    await pubsub.start()

    with tracer.start_as_current_span("test-span") as span:
        expected_span_id = format(span.get_span_context().span_id, "016x")
        await pubsub.publish(TaskAgentMessage("test message"))

    await asyncio.sleep(0.1)

    assert len(captured_span_ids) == 1
    assert captured_span_ids[0] == expected_span_id

    await pubsub.stop()


async def test_pubsub_retains_otel_context_for_async_handlers():
    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer("test")

    pubsub = PubSub()
    captured_span_ids: list[str] = []

    async def async_handler(msg):
        span = trace.get_current_span()
        span_context = span.get_span_context()
        if span_context.is_valid:
            captured_span_ids.append(format(span_context.span_id, "016x"))

    pubsub.subscribe(TaskAgentMessage, async_handler)
    await pubsub.start()

    with tracer.start_as_current_span("test-span") as span:
        expected_span_id = format(span.get_span_context().span_id, "016x")
        await pubsub.publish(TaskAgentMessage("test message"))

    await asyncio.sleep(0.1)

    assert len(captured_span_ids) == 1
    assert captured_span_ids[0] == expected_span_id

    await pubsub.stop()


class TaskAgentMessageConsumer(Consumer[TaskAgentMessage]):
    def __init__(self):
        self.received: list[TaskAgentMessage] = []

    async def consume(self, message: TaskAgentMessage) -> None:
        self.received.append(message)


async def test_pubsub_consumer():
    pubsub = PubSub()

    consumer = TaskAgentMessageConsumer()
    pubsub.subscribe(consumer)

    await pubsub.start()
    await pubsub.publish(TaskAgentMessage("hello from consumer"))

    await asyncio.sleep(0.1)

    assert len(consumer.received) == 1
    assert consumer.received[0].content == "hello from consumer"
    await pubsub.stop()


async def test_pubsub_consumer_not_called_for_different_event():
    pubsub = PubSub()

    consumer = TaskAgentMessageConsumer()
    pubsub.subscribe(consumer)

    await pubsub.start()
    await pubsub.publish(DummyMessage("should not match"))

    await asyncio.sleep(0.1)

    assert len(consumer.received) == 0
    await pubsub.stop()


async def test_pubsub_context_differs_per_publish():
    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer("test")

    pubsub = PubSub()
    captured_span_ids: list[str] = []

    def sync_handler(msg):
        span = trace.get_current_span()
        span_context = span.get_span_context()
        if span_context.is_valid:
            captured_span_ids.append(format(span_context.span_id, "016x"))

    pubsub.subscribe(TaskAgentMessage, sync_handler)
    await pubsub.start()

    with tracer.start_as_current_span("span-1") as span1:
        expected_span_id_1 = format(span1.get_span_context().span_id, "016x")
        await pubsub.publish(TaskAgentMessage("message 1"))

    with tracer.start_as_current_span("span-2") as span2:
        expected_span_id_2 = format(span2.get_span_context().span_id, "016x")
        await pubsub.publish(TaskAgentMessage("message 2"))

    await asyncio.sleep(0.1)

    assert len(captured_span_ids) == 2
    assert captured_span_ids[0] == expected_span_id_1
    assert captured_span_ids[1] == expected_span_id_2
    assert captured_span_ids[0] != captured_span_ids[1]

    await pubsub.stop()
