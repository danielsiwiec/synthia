

from daimos.agents.claude import Message
from daimos.agents.task import run
from daimos.helpers.events import EventEmitter
from daimos.helpers.schema import validate_schema
from daimos.output import parse
from daimos.service.models import TaskRequest, TaskResponse


class TaskService:
    def __init__(self, event_emitter: EventEmitter[Message]):
        self.event_emitter = event_emitter

    async def process_task(self, request: TaskRequest) -> TaskResponse:
        validate_schema(request.response_schema)

        result_message = None
        result_message = await run(request, self.event_emitter)

        if not result_message:
            raise Exception("Timeout: No ResultMessage received within expected time")

        result = (
            await parse(result_message.result, request.response_schema)
            if request.response_schema
            else result_message.result
        )
        return TaskResponse(result=result, session_id=result_message.session_id)
