import re

from daimos.agents.claude import Message, Result
from daimos.agents.claude import run as claude_run
from daimos.agents.subagents import get_matching_subagents
from daimos.helpers.events import EventEmitter
from daimos.service.models import TaskRequest


async def run(request: TaskRequest, emitter: EventEmitter[Message]) -> Result | None:
    agents = get_matching_subagents(request.task)
    objective = re.sub(r"#\w+", "", request.task).strip()
    async for message in claude_run(objective=objective, resume=request.resume, emitter=emitter, agents=agents):
        if isinstance(message, Result):
            return message
    return None
