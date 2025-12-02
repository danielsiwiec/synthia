import asyncio

from synthia.agents.claude import ClaudeAgent
from synthia.helpers.pubsub import pubsub
from synthia.helpers.schema import validate_schema
from synthia.output import parse_from_schema
from synthia.service.models import AdminNotification, TaskCompletion, TaskRequest, TaskResponse, TaskTrigger


class TaskService:
    def __init__(self, claude_agent: ClaudeAgent):
        self._last_session_id: str | None = None
        self._claude_agent = claude_agent
        self._current_task: asyncio.Task | None = None
        pubsub.subscribe(TaskTrigger, self._handle_scheduled_task)

    async def _handle_scheduled_task(self, trigger: TaskTrigger) -> None:
        await self.process_task(TaskRequest(task=trigger.task))
        await pubsub.publish(AdminNotification(content=f"✅ *Task '{trigger.name}' completed*"))

    async def process_task(self, request: TaskRequest, resume: bool = False) -> TaskResponse:
        validate_schema(request.response_schema)

        resume_from_session = self._last_session_id if resume else None

        task = asyncio.create_task(
            self._claude_agent.run_for_result(
                objective=request.task,
                resume_from_session=resume_from_session,
                thread_id=request.thread_id,
            )
        )
        self._current_task = task

        try:
            result_message = await task
        except asyncio.CancelledError:
            self._current_task = None
            raise
        finally:
            if self._current_task == task:
                self._current_task = None

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

    async def stop_current_task(self) -> bool:
        if not self._current_task:
            return False
        self._current_task.cancel()
        try:
            await self._current_task
        except asyncio.CancelledError:
            pass
        return True
