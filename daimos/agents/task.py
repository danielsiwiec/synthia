
from daimos.agents.claude import Message, Result
from daimos.agents.claude import run as claude_run
from daimos.helpers.events import EventEmitter
from daimos.service.models import TaskRequest


async def run(request: TaskRequest, emitter: EventEmitter[Message]) -> Result | None:
    async for message in claude_run(objective=request.task, resume=request.resume, emitter=emitter):
        if isinstance(message, Result):
            return message
    return None
