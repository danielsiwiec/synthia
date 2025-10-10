from typing import Any

from pydantic import BaseModel

from daimos.agents.claude import Message, Result, run
from daimos.helpers.events import EventEmitter
from daimos.helpers.schema import validate_schema
from daimos.output import parse


class TaskRequest(BaseModel):
    task: str
    response_schema: dict[str, Any] | None = None
    resume: str | None = None


class TaskResponse(BaseModel):
    result: Any
    session_id: str


class TaskService:
    def __init__(self, event_emitter: EventEmitter[Message]):
        self.event_emitter = event_emitter

    async def process_task(self, request: TaskRequest) -> TaskResponse:
        validate_schema(request.response_schema)

        result_message = None
        async for message in run(objective=request.task, resume=request.resume, emitter=self.event_emitter):
            if isinstance(message, Result):
                result_message = message

        if not result_message:
            raise Exception("Timeout: No ResultMessage received within expected time")

        result = (
            await parse(result_message.result, request.response_schema)
            if request.response_schema
            else result_message.result
        )
        return TaskResponse(result=result, session_id=result_message.session_id)
