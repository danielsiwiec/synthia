import asyncio
import inspect
import types
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any, cast, get_args

from loguru import logger
from opentelemetry import context as otel_context

type TopicType = type | types.UnionType


def _is_union_type(topic: TopicType) -> bool:
    return hasattr(topic, "__args__") and type(topic).__name__ == "UnionType"


def _get_topic_name(topic: TopicType) -> str:
    if isinstance(topic, type):
        return topic.__name__
    return str(topic)


def _matches_topic(message: Any, topic: TopicType) -> bool:
    if _is_union_type(topic):
        union_args = get_args(topic)
        return any(isinstance(message, arg) for arg in union_args)
    if isinstance(topic, type):
        return isinstance(message, topic)
    return False


class _MessageWithContext:
    def __init__(self, message: Any, ctx: otel_context.Context | None):
        self.message = message
        self.ctx = ctx


class PubSub:
    def __init__(self):
        self.async_subscribers: dict[TopicType, list[Callable[[Any], Coroutine[Any, Any, Any]]]] = defaultdict(list)
        self.sync_subscribers: dict[TopicType, list[Callable[[Any], None]]] = defaultdict(list)
        self.queues: dict[TopicType, asyncio.Queue[Any]] = defaultdict(asyncio.Queue)
        self.tasks: list[asyncio.Task[None]] = []

    def subscribe[T](
        self, topic: type[T] | types.UnionType, handler: Callable[[T], Coroutine[Any, Any, Any]] | Callable[[T], None]
    ):
        if inspect.iscoroutinefunction(handler):
            self.async_subscribers[topic].append(cast(Callable[[Any], Coroutine[Any, Any, Any]], handler))
        else:
            self.sync_subscribers[topic].append(cast(Callable[[Any], None], handler))

    async def publish[T](self, message: T):
        all_topics = set(self.async_subscribers.keys()) | set(self.sync_subscribers.keys())
        current_ctx = otel_context.get_current()

        for topic in all_topics:
            if _matches_topic(message, topic):
                await self.queues[topic].put(_MessageWithContext(message, current_ctx))

    async def _dispatch(self, topic: TopicType):
        while True:
            wrapped = await self.queues[topic].get()
            msg = wrapped.message
            ctx = wrapped.ctx

            token = otel_context.attach(ctx) if ctx else None
            try:
                sync_handlers = self.sync_subscribers.get(topic, [])
                for handler in sync_handlers:
                    try:
                        handler(msg)
                    except Exception as e:
                        logger.error(f"error in sync handler for {_get_topic_name(topic)}: {e}")

                async_handlers = self.async_subscribers.get(topic, [])
                for handler in async_handlers:
                    asyncio.create_task(self._dispatch_async(handler, msg, ctx))
            finally:
                if token is not None:
                    otel_context.detach(token)

    async def _dispatch_async(
        self, handler: Callable[[Any], Coroutine[Any, Any, Any]], msg: Any, ctx: otel_context.Context | None
    ):
        token = otel_context.attach(ctx) if ctx else None
        try:
            await handler(msg)
        finally:
            if token is not None:
                otel_context.detach(token)

    async def start(self):
        all_topics = set(self.async_subscribers.keys()) | set(self.sync_subscribers.keys())
        for topic in all_topics:
            self.tasks.append(asyncio.create_task(self._dispatch(topic)))

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []


pubsub = PubSub()
