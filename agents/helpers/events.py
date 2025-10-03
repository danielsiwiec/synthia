import asyncio
from enum import Enum


class EventType(Enum):
    TASK_AGENT_MESSAGE = "message_transformed"


class EventEmitter:
    def __init__(self):
        self._handlers = {}

    def on(self, event_type: EventType, handler):
        event_name = event_type.value
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)

    async def emit(self, event_type: EventType, *args, **kwargs):
        event_name = event_type.value
        if event_name in self._handlers:
            tasks = []
            for handler in self._handlers[event_name]:
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(handler(*args, **kwargs))
                else:
                    handler(*args, **kwargs)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
