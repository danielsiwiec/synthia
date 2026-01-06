import asyncio
import random

from loguru import logger

from synthia.agents.claude import ClaudeAgent
from synthia.helpers.pubsub import pubsub
from synthia.helpers.schema import validate_schema
from synthia.output import parse_from_schema
from synthia.service.models import (
    AdminNotification,
    StopTaskRequest,
    TaskRequest,
    TaskResponse,
    TaskTrigger,
)
from synthia.service.session_repository import SessionRepository


class TaskService:
    def __init__(self, claude_agent: ClaudeAgent, session_repository: SessionRepository):
        self._claude_agent = claude_agent
        self._tasks: dict[int, asyncio.Task] = {}
        self._session_repository = session_repository
        pubsub.subscribe(TaskTrigger, self._handle_scheduled_task)
        pubsub.subscribe(TaskRequest, self._handle_pubsub_task)
        pubsub.subscribe(StopTaskRequest, self._handle_stop_task)

    async def _handle_scheduled_task(self, trigger: TaskTrigger) -> None:
        thread_id = random.randint(0, 2**63 - 1)
        await self.process_task(TaskRequest(task=trigger.task, thread_id=thread_id))
        if not trigger.silent:
            await pubsub.publish(AdminNotification(content=f"✅ *Task '{trigger.name}' completed*", silent=True))

    async def _handle_pubsub_task(self, request: TaskRequest) -> None:
        try:
            response = await self.process_task(request)
            await pubsub.publish(response)
        except Exception as e:
            logger.error(f"error processing pubsub task: {e}")

    async def process_task(self, request: TaskRequest) -> TaskResponse:
        validate_schema(request.response_schema)

        resume_from_session = self._session_repository.get(request.thread_id)

        task = asyncio.create_task(
            self._claude_agent.run_for_result(
                objective=request.task,
                resume_from_session=resume_from_session,
                thread_id=request.thread_id,
            )
        )
        self._tasks[request.thread_id] = task

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

        self._tasks.pop(request.thread_id, None)
        asyncio.create_task(self._session_repository.save(request.thread_id, result_message.session_id))

        return TaskResponse(thread_id=request.thread_id, result=result, session_id=result_message.session_id)

    async def _handle_stop_task(self, request: StopTaskRequest) -> None:
        await self.stop_task(request.thread_id)

    async def stop_task(self, thread_id: int) -> bool:
        task = self._tasks.get(thread_id)
        if not task:
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True
