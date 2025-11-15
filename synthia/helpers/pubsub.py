import asyncio
import inspect
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from loguru import logger

T = TypeVar("T")


class PubSub:
    def __init__(self):
        self.async_subscribers: dict[type, list[Callable[[Any], Coroutine]]] = defaultdict(list)
        self.sync_subscribers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)
        self.queues: dict[type, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.tasks: list[asyncio.Task] = []

    def subscribe(self, topic: type[T], handler: Callable[[T], Coroutine] | Callable[[T], None]):
        if inspect.iscoroutinefunction(handler):
            self.async_subscribers[topic].append(handler)
        else:
            self.sync_subscribers[topic].append(handler)

    async def publish(self, message: T):
        all_topics = set(self.async_subscribers.keys()) | set(self.sync_subscribers.keys())

        for topic in all_topics:
            if isinstance(message, topic):
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


pubsub = PubSub()
