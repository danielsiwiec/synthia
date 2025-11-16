from synthia.agents.claude import ClaudeAgent
from synthia.helpers.pubsub import pubsub
from synthia.helpers.schema import validate_schema
from synthia.output import parse_from_schema
from synthia.service.models import TaskCompletion, TaskRequest, TaskResponse


class TaskService:
    def __init__(self, claude_agent: ClaudeAgent):
        self._last_session_id: str | None = None
        self._claude_agent = claude_agent

    async def process_task(self, request: TaskRequest, resume: bool = False) -> TaskResponse:
        validate_schema(request.response_schema)

        resume_from_session = self._last_session_id if resume else None

        objective = request.task
        result_message = await self._claude_agent.run_for_result(
            objective=objective,
            resume_from_session=resume_from_session,
        )

        if not result_message:
            raise Exception("Timeout: No ResultMessage received within expected time")

        result = (
            await parse_from_schema(result_message.result, request.response_schema)
            if request.response_schema
            else result_message.result
        )

        self._last_session_id = result_message.session_id

        await pubsub.publish(TaskCompletion(session_id=result_message.session_id))

        return TaskResponse(result=result, session_id=result_message.session_id)
