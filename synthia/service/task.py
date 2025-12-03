import asyncio
import random

from synthia.agents.claude import ClaudeAgent
from synthia.helpers.pubsub import pubsub
from synthia.helpers.schema import validate_schema
from synthia.output import parse_from_schema
from synthia.service.models import AdminNotification, TaskRequest, TaskResponse, TaskTrigger


class TaskService:
    def __init__(self, claude_agent: ClaudeAgent):
        self._claude_agent = claude_agent
        self._tasks: dict[int, tuple[str | None, asyncio.Task]] = {}
        pubsub.subscribe(TaskTrigger, self._handle_scheduled_task)

    async def _handle_scheduled_task(self, trigger: TaskTrigger) -> None:
        thread_id = random.randint(0, 2**63 - 1)
        await self.process_task(TaskRequest(task=trigger.task, thread_id=thread_id))
        await pubsub.publish(AdminNotification(content=f"✅ *Task '{trigger.name}' completed*"))

    async def process_task(self, request: TaskRequest) -> TaskResponse:
        validate_schema(request.response_schema)

        resume_from_session = self._tasks[request.thread_id][0] if request.thread_id in self._tasks else None

        task = asyncio.create_task(
            self._claude_agent.run_for_result(
                objective=request.task,
                resume_from_session=resume_from_session,
                thread_id=request.thread_id,
            )
        )
        self._tasks[request.thread_id] = (resume_from_session, task)

        try:
            result_message = await task
        except asyncio.CancelledError:
            self._tasks.pop(request.thread_id, None)
            raise

        if not result_message:
            self._tasks.pop(request.thread_id, None)
            raise Exception("Timeout: No ResultMessage received within expected time")

        result = (
            await parse_from_schema(result_message.result, request.response_schema)
            if request.response_schema
            else result_message.result
        )

        self._tasks[request.thread_id] = (result_message.session_id, task)

        return TaskResponse(result=result, session_id=result_message.session_id)

    async def stop_task(self, thread_id: int) -> bool:
        entry = self._tasks.get(thread_id)
        if not entry:
            return False
        _, task = entry
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True
