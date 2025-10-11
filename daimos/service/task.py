import re

from daimos.agents.claude import Message, run_for_result
from daimos.agents.subagents import get_matching_subagents
from daimos.helpers.events import EventEmitter
from daimos.helpers.schema import validate_schema
from daimos.output import parse
from daimos.service.models import TaskRequest, TaskResponse


class TaskService:
    def __init__(self, event_emitter: EventEmitter[Message]):
        self.event_emitter = event_emitter

    async def process_task(self, request: TaskRequest, resume_from_session: str | None = None) -> TaskResponse:
        validate_schema(request.response_schema)

        agents = get_matching_subagents(request.task)
        objective = re.sub(r"#\w+", "", request.task).strip()
        result_message = await run_for_result(
            objective=objective, resume_from_session=resume_from_session, emitter=self.event_emitter, agents=agents
        )

        if not result_message:
            raise Exception("Timeout: No ResultMessage received within expected time")

        result = (
            await parse(result_message.result, request.response_schema)
            if request.response_schema
            else result_message.result
        )
        return TaskResponse(result=result, session_id=result_message.session_id)
