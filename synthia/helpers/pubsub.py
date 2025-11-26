import asyncio
import inspect
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar, cast, get_args

from loguru import logger

T = TypeVar("T")


def _is_union_type(topic: type) -> bool:
    return hasattr(topic, "__args__") and type(topic).__name__ == "UnionType"


def _matches_topic(message: Any, topic: type) -> bool:
    if _is_union_type(topic):
        union_args = get_args(topic)
        return any(isinstance(message, arg) for arg in union_args)
    return isinstance(message, topic)


class PubSub:
    def __init__(self):
        self.async_subscribers: dict[type, list[Callable[[Any], Coroutine]]] = defaultdict(list)
        self.sync_subscribers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)
        self.queues: dict[type, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.tasks: list[asyncio.Task] = []

    def subscribe(self, topic: type[T], handler: Callable[[T], Coroutine] | Callable[[T], None]):
        if inspect.iscoroutinefunction(handler):
            self.async_subscribers[topic].append(cast(Callable[[Any], Coroutine], handler))
        else:
            self.sync_subscribers[topic].append(cast(Callable[[Any], None], handler))

    async def publish(self, message: T):
        all_topics = set(self.async_subscribers.keys()) | set(self.sync_subscribers.keys())

        for topic in all_topics:
            if _matches_topic(message, topic):
                await self.queues[topic].put(message)

    async def _dispatch(self, topic: type):
        while True:
            msg = await self.queues[topic].get()

            sync_handlers = self.sync_subscribers.get(topic, [])
            for handler in sync_handlers:
                try:
                    handler(msg)
                except Exception as e:
                    logger.error(f"error in sync handler for {topic.__name__}: {e}")

            async_handlers = self.async_subscribers.get(topic, [])
            for handler in async_handlers:
                asyncio.create_task(handler(msg))

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
