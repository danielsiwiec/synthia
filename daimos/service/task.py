from daimos.agents.agents import get_agent_system_prompt
from daimos.agents.claude import run_for_result
from daimos.agents.learning.learner import Learner
from daimos.helpers.pubsub import pubsub
from daimos.helpers.schema import validate_schema
from daimos.output import parse_from_schema
from daimos.service.models import TaskCompletion, TaskRequest, TaskResponse


class TaskService:
    def __init__(self, learner: Learner):
        self._last_session_id: str | None = None
        self.learner = learner

    async def process_task(self, request: TaskRequest, resume: bool = False) -> TaskResponse:
        validate_schema(request.response_schema)

        resume_from_session = self._last_session_id if resume else None

        system_prompt, agent_name = await get_agent_system_prompt(request.task, self.learner)
        objective = request.task
        result_message = await run_for_result(
            objective=objective,
            resume_from_session=resume_from_session,
            system_prompt=system_prompt,
        )

        if not result_message:
            raise Exception("Timeout: No ResultMessage received within expected time")

        result = (
            await parse_from_schema(result_message.result, request.response_schema)
            if request.response_schema
            else result_message.result
        )

        self._last_session_id = result_message.session_id

        await pubsub.publish(TaskCompletion, TaskCompletion(session_id=result_message.session_id))

        return TaskResponse(result=result, session_id=result_message.session_id)
