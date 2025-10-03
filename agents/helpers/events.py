import asyncio
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

T = TypeVar("T")


class EventType(Enum):
    TASK_AGENT_MESSAGE = "message_transformed"


class EventEmitter[T]:
    def __init__(self):
        self._handlers: dict[str, list[Callable[[T], Awaitable[None] | None]]] = {}

    def on(self, event_type: EventType, handler: Callable[[T], Awaitable[None] | None]) -> None:
        event_name = event_type.value
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)

    async def emit(self, event_type: EventType, message: T) -> None:
        event_name = event_type.value
        if event_name in self._handlers:
            tasks = []
            for handler in self._handlers[event_name]:
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(handler(message))
                else:
                    handler(message)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
