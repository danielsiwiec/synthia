import asyncio
import random
from pathlib import Path

from claude_agent_sdk import McpServerConfig
from loguru import logger

from synthia.agents.agent import ClaudeAgent
from synthia.helpers.pubsub import pubsub
from synthia.service.models import (
    AdminNotification,
    StopTaskRequest,
    TaskRequest,
    TaskResponse,
    TaskTrigger,
)
from synthia.service.session_repository import SessionRepository
from synthia.telemetry import traced


class TaskService:
    def __init__(
        self,
        mcp_servers: dict[str, McpServerConfig],
        session_repository: SessionRepository,
        cwd: str | Path | None = None,
    ):
        self._mcp_servers = mcp_servers
        self._cwd = cwd
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

    @traced("process_task")
    async def process_task(self, request: TaskRequest) -> TaskResponse:
        objective = request.task

        agent, session_id = self._session_repository.get(request.thread_id)
        if not agent:
            agent = await ClaudeAgent.create(self._mcp_servers, self._cwd, resume=session_id)

        task = asyncio.create_task(
            agent.run_for_result(
                objective=objective,
                thread_id=request.thread_id,
            )
        )
        self._tasks[request.thread_id] = task

        try:
            result_message = await task
        except asyncio.CancelledError:
            self._tasks.pop(request.thread_id, None)
            await agent.disconnect()
            raise

        self._tasks.pop(request.thread_id, None)

        if not result_message:
            await agent.disconnect()
            raise Exception("Timeout: No ResultMessage received within expected time")

        self._session_repository.save(request.thread_id, result_message.session_id, agent)

        return TaskResponse(
            thread_id=request.thread_id, result=result_message.result, session_id=result_message.session_id
        )

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
