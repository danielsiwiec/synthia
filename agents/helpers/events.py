from enum import Enum


class EventType(Enum):
    CLAUDE_MESSAGE = "message_transformed"


class EventEmitter:
    def __init__(self):
        self._handlers = {}

    def on(self, event_type: EventType, handler):
        event_name = event_type.value
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)

    def emit(self, event_type: EventType, *args, **kwargs):
        event_name = event_type.value
        if event_name in self._handlers:
            for handler in self._handlers[event_name]:
                handler(*args, **kwargs)
