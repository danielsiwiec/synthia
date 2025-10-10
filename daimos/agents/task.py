import re

from daimos.agents.claude import Message, Result, run_for_result
from daimos.agents.subagents import get_matching_subagents
from daimos.helpers.events import EventEmitter
from daimos.service.models import TaskRequest


async def run(request: TaskRequest, emitter: EventEmitter[Message]) -> Result | None:
    agents = get_matching_subagents(request.task)
    objective = re.sub(r"#\w+", "", request.task).strip()
    return await run_for_result(objective=objective, resume=request.resume, emitter=emitter, agents=agents)
