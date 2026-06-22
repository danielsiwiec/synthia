import asyncio
import os
import random
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from google.adk.sessions import BaseSessionService
from google.adk.tools.skill_toolset import SkillToolset
from loguru import logger

from synthia.agents.agent import (
    FRONT_MODEL,
    Agent,
    Result,
    build_front_instruction,
    create_diagram_tool,
    create_image_tool,
    record_delegated_cost,
)
from synthia.agents.skills import reload_skills
from synthia.agents.skilltools import versions
from synthia.helpers.pubsub import pubsub
from synthia.service.chat import MessageRepository
from synthia.service.job_execution_repository import JobExecutionRepository
from synthia.service.models import (
    AdminNotification,
    StopTaskRequest,
    TaskRequest,
    TaskResponse,
    TaskTrigger,
)
from synthia.service.session_repository import SessionRepository
from synthia.service.task_repository import TaskRepository
from synthia.telemetry import traced

_MAX_CONCURRENT_TASKS = int(os.getenv("FRONT_MAX_CONCURRENT_TASKS", "3"))
_RECENT_TASKS_LIMIT = int(os.getenv("FRONT_RECENT_TASKS", "10"))
_FRONT_ENABLED = os.getenv("FRONT_AGENT_ENABLED", "1") != "0"

_TASK_AGENT_DESCRIPTION = (
    "A powerful agent that can control a computer: run shell commands and scripts, read and write "
    "files, drive a real web browser, manage downloads, and use many skills, plus full web and "
    "memory access. Hand it complete, self-contained instructions for any real, operational work."
)


class TaskService:
    def __init__(
        self,
        tools: list[Any],
        session_repository: SessionRepository,
        session_service: BaseSessionService,
        cwd: str | Path | None = None,
        job_execution_repo: JobExecutionRepository | None = None,
        user_skills_dir: str | Path | None = None,
        skill_toolset: SkillToolset | None = None,
        message_repository: MessageRepository | None = None,
        task_repository: TaskRepository | None = None,
        front_tools: list[Any] | None = None,
    ):
        self._tools = tools
        self._front_tools = front_tools or []
        self._session_service = session_service
        self._cwd = cwd
        self._tasks: dict[int, asyncio.Task] = {}
        self._session_repository = session_repository
        self._job_execution_repo = job_execution_repo
        self._skill_toolset = skill_toolset
        self._message_repository = message_repository
        self._task_repo = task_repository
        self._bg_handles: dict[str, asyncio.Task] = {}
        self._bg_threads: dict[str, int] = {}
        self._bg_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_TASKS)
        self._user_skills_dir = Path(user_skills_dir) if user_skills_dir else Path.home() / ".claude" / "skills"
        pubsub.subscribe(TaskTrigger, self._handle_scheduled_task)
        pubsub.subscribe(TaskRequest, self._handle_pubsub_task)
        pubsub.subscribe(StopTaskRequest, self._handle_stop_task)

    async def _handle_scheduled_task(self, trigger: TaskTrigger) -> None:
        thread_id = random.randint(0, 2**63 - 1)
        result = await self._run_task(TaskRequest(task=trigger.task, thread_id=thread_id))
        if result:
            await self._record_and_self_heal(trigger, result)
        if not trigger.silent:
            await pubsub.publish(AdminNotification(content=f"✅ *Task '{trigger.name}' completed*", silent=True))

    async def _handle_pubsub_task(self, request: TaskRequest) -> None:
        try:
            response = await self.process_task(request)
            await pubsub.publish(response)
        except Exception as e:
            logger.error(f"error processing pubsub task: {e}")

    async def process_task(self, request: TaskRequest) -> TaskResponse:
        result = await self._run_task(request)
        if not result:
            raise Exception("Timeout: No result received within expected time")
        return TaskResponse(thread_id=request.thread_id, result=result.result, session_id=result.session_id)

    @traced("process_task")
    async def _run_task(self, request: TaskRequest) -> Result | None:
        objective = request.task

        if self._skill_toolset is not None:
            try:
                reload_skills(self._skill_toolset, self._cwd)
            except Exception as error:
                logger.warning(f"skill reload failed: {error}")

        agent, _ = self._session_repository.get(request.thread_id)
        if not agent:
            image_tool = create_image_tool(request.thread_id, self._cwd)
            diagram_tool = create_diagram_tool(request.thread_id, self._cwd)
            task_tools = [*self._tools, image_tool, diagram_tool]
            if self._front_enabled(request.thread_id):
                agent = await self._create_front_agent(request.thread_id, task_tools)
            else:
                agent = await Agent.create(
                    tools=task_tools,
                    cwd=self._cwd,
                    session_service=self._session_service,
                )

        task = asyncio.create_task(
            agent.run_for_result(
                objective=objective,
                thread_id=request.thread_id,
                images=request.images,
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
            return None

        self._session_repository.save(request.thread_id, result_message.session_id, agent)
        return result_message

    def _front_enabled(self, thread_id: int) -> bool:
        if not _FRONT_ENABLED or self._message_repository is None:
            return False
        if not self._message_repository.is_chat_thread(thread_id):
            return False
        if FRONT_MODEL.startswith("openai/") and not os.getenv("OPENAI_API_KEY"):
            return False
        return True

    async def _create_front_agent(self, thread_id: int, task_tools: list[Any]) -> Agent:
        task_agent = await Agent.create(
            tools=task_tools,
            cwd=self._cwd,
            session_service=self._session_service,
            name="task_agent",
            description=_TASK_AGENT_DESCRIPTION,
        )
        front_tools = [
            *self._build_delegation_tools(thread_id, task_agent),
            self._build_find_past_work_tool(),
            *self._front_tools,
        ]
        instruction = build_front_instruction(await self._recent_tasks_block(thread_id))
        return await Agent.create(
            tools=front_tools,
            cwd=self._cwd,
            session_service=self._session_service,
            model=FRONT_MODEL,
            system_prompt=instruction,
            include_builtins=False,
            name="synthia",
            prompt_thread_hint=False,
        )

    def _build_delegation_tools(self, thread_id: int, task_agent: Agent) -> list[Callable]:
        async def delegate_to_task_agent(request: str, task_id: str = "") -> str:
            """Run the capable task agent now, wait for its result, and return it for you to relay to
            the user. The task agent is powerful and runs silently: it can control a computer, run
            shell commands and scripts, read/write files, drive a real web browser, manage downloads,
            and use many skills — assume it can do almost any operational task.

            Args:
                request: A complete, self-contained instruction for the task agent, including all
                    context it needs.
                task_id: Optional. Pass an existing task_id ONLY to continue that SAME task with its
                    prior context. Omit it to start a fresh, unrelated task.

            Returns:
                The task agent's result, prefixed with a `task_id=<id>` line. Reuse that task_id to
                continue this task later.
            """
            session_id = task_id or f"task-{uuid.uuid4().hex}"
            await self._start_task(session_id, thread_id, request, request, background=False)
            result = await task_agent.run_for_result(objective=request, thread_id=None, session_id=session_id)
            await self._finish_task(session_id, result)
            record_delegated_cost(result.cost_usd if result else None)
            answer = result.result if result and result.success else (result.error if result else None)
            return f"task_id={session_id}\n\n{answer or '(the task agent returned no result)'}"

        async def dispatch_background_task(request: str, label: str = "", task_id: str = "") -> str:
            """Start the task agent in the background and return immediately. The result is delivered
            into this chat automatically when it is ready. Use for long-running work or when the user
            wants to keep chatting. The task agent is powerful: it can control a computer, run shell
            commands and scripts, read/write files, drive a real web browser, and use many skills.

            Args:
                request: A complete, self-contained instruction for the task agent.
                label: A short human-readable label for this task (shown to the user and in check_tasks).
                task_id: Optional. Pass an existing task_id ONLY to continue that SAME task. Omit it to
                    start a fresh, unrelated task.
            """
            session_id = task_id or f"task-{uuid.uuid4().hex}"
            await self._start_task(session_id, thread_id, label or request, request, background=True)
            bg = asyncio.create_task(self._run_background(task_agent, request, session_id, thread_id))
            self._bg_handles[session_id] = bg
            self._bg_threads[session_id] = thread_id
            shown = label or request[:40]
            return (
                f"Started background task (task_id={session_id}, label={shown!r}). "
                "I'll deliver the result here when it's ready."
            )

        async def check_tasks() -> str:
            """List this conversation's tasks (in-flight and finished) with their task_id, label,
            status, and a short result summary."""
            if self._task_repo is None:
                return "Task history is unavailable."
            records = await self._task_repo.for_thread(thread_id)
            if not records:
                return "No tasks have been started in this conversation yet."
            lines = []
            for record in records:
                line = f"- task_id={record['id']} | {record['label']} | {record['status']}"
                if record["status"] in ("done", "error") and record["result"]:
                    line += f" | result: {record['result'][:300]}"
                lines.append(line)
            return "\n".join(lines)

        return [delegate_to_task_agent, dispatch_background_task, check_tasks]

    def _build_find_past_work_tool(self) -> Callable:
        async def find_past_work(query: str = "", kind: str = "all", limit: int = 10) -> str:
            """Look up your past tasks and scheduled jobs — your full history beyond the few most
            recent tasks already in view. Use it to recall what was done before, find an earlier task
            to resume (it returns task_ids), or check whether a scheduled job ran and how it went.

            Args:
                query: Optional text to filter by (matches a task's request/result/label or a job's
                    name/error). Leave empty for the most recent.
                kind: "task", "job", or "all" (default).
                limit: Max items to return per kind.
            """
            sections: list[str] = []
            if kind in ("task", "all") and self._task_repo is not None:
                tasks = await self._task_repo.search(query, limit)
                if tasks:
                    lines = [
                        f"- task_id={t['id']} | {t['label']} | {t['status']} | "
                        f"{((t.get('result') or t.get('request')) or '').strip().replace(chr(10), ' ')[:200]}"
                        for t in tasks
                    ]
                    sections.append("Tasks:\n" + "\n".join(lines))
            if kind in ("job", "all") and self._job_execution_repo is not None:
                jobs = await self._job_execution_repo.recent(limit, query)
                if jobs:
                    lines = []
                    for job in jobs:
                        when = job["created_at"].strftime("%Y-%m-%d %H:%M") if job.get("created_at") else "?"
                        status = "✅" if job["success"] else "🔴"
                        line = f"- {job['job_name']} | {status} | {when}"
                        if job.get("error"):
                            line += f" | error: {job['error'][:120]}"
                        lines.append(line)
                    sections.append("Jobs:\n" + "\n".join(lines))
            return "\n\n".join(sections) if sections else "No matching tasks or jobs found."

        return find_past_work

    async def _start_task(
        self, task_id: str, thread_id: int, label_source: str, request: str, background: bool
    ) -> None:
        if self._task_repo is None:
            return
        label = (label_source or "").strip().replace("\n", " ")[:80]
        await self._task_repo.start(
            task_id=task_id, thread_id=thread_id, label=label, request=request, background=background
        )

    async def _finish_task(self, task_id: str, result: Result | None) -> None:
        if self._task_repo is None:
            return
        success = bool(result and result.success)
        text = result.result if result and result.success else ((result.error if result else None) or "no result")
        await self._task_repo.finish(task_id=task_id, success=success, result=text)

    async def _run_background(self, task_agent: Agent, request: str, session_id: str, thread_id: int) -> None:
        try:
            async with self._bg_semaphore:
                if self._task_repo is not None:
                    await self._task_repo.set_status(session_id, "running")
                result = await task_agent.run_for_result(objective=request, thread_id=None, session_id=session_id)
        except asyncio.CancelledError:
            if self._task_repo is not None:
                await self._task_repo.set_status(session_id, "cancelled")
            raise
        except Exception as error:
            logger.error(f"background task {session_id} failed: {error}")
            if self._task_repo is not None:
                await self._task_repo.finish(task_id=session_id, success=False, result=str(error))
            await self._deliver_background(thread_id, session_id, False, f"🔴 Background task failed: {error}", None)
            return
        finally:
            self._bg_handles.pop(session_id, None)
            self._bg_threads.pop(session_id, None)
        await self._finish_task(session_id, result)
        if result and result.success:
            text = f"✅ Background task complete:\n\n{result.result}"
        else:
            text = f"🔴 Background task failed: {result.error if result else 'no result'}"
        await self._deliver_background(
            thread_id, session_id, bool(result and result.success), text, result.cost_usd if result else None
        )

    async def _deliver_background(
        self, thread_id: int, session_id: str, success: bool, text: str, cost: float | None
    ) -> None:
        await pubsub.publish(
            Result(session_id=session_id, thread_id=thread_id, success=success, result=text, cost_usd=cost)
        )

    async def _recent_tasks_block(self, thread_id: int) -> str:
        if self._task_repo is None:
            return ""
        try:
            rows = await self._task_repo.recent(_RECENT_TASKS_LIMIT)
        except Exception as error:
            logger.warning(f"recent tasks lookup failed: {error}")
            return ""
        blocks = []
        for row in rows:
            request = (row.get("request") or "").strip().replace("\n", " ")[:300]
            result = (row.get("result") or "").strip().replace("\n", " ")[:500]
            if not request and not result:
                continue
            label = row.get("label") or ""
            blocks.append(f"- task_id={row['id']} | [{label}] task: {request}\n  result: {result}")
        return "\n".join(blocks)

    def _skill_dir(self, skill: str) -> Path | None:
        skill_dir = self._user_skills_dir / skill
        if not skill_dir.is_dir():
            return None
        if not (skill_dir / versions.VERSIONS_DIR / versions.LEDGER_FILE).exists():
            return None
        return skill_dir

    async def _record_and_self_heal(self, trigger: TaskTrigger, result: Result) -> None:
        skill_versions: dict[str, str] = {}
        for skill in result.skill_names:
            skill_dir = self._skill_dir(skill)
            if skill_dir is None:
                continue
            ledger = versions.status(skill_dir)
            active = ledger.get("active")
            if active:
                skill_versions[skill] = active
                try:
                    versions.record_outcome(skill_dir, active, result.success)
                except ValueError:
                    pass

        if self._job_execution_repo is not None:
            await self._job_execution_repo.record(
                job_name=trigger.name,
                skill_names=result.skill_names,
                thread_id=result.thread_id,
                success=result.success,
                error=result.error,
                cost_usd=result.cost_usd,
                duration_s=result.duration_s,
                tool_call_count=len(result.tool_call_names),
                skill_versions=skill_versions,
            )

        if result.success:
            await self._maybe_promote(skill_versions)
        else:
            await self._maybe_rollback_and_rerun(trigger, skill_versions)

    async def _maybe_promote(self, skill_versions: dict[str, str]) -> None:
        for skill, active in skill_versions.items():
            skill_dir = self._skill_dir(skill)
            if skill_dir is None:
                continue
            ledger = versions.status(skill_dir)
            if ledger.get("canary") != active:
                continue
            version = next((v for v in ledger["versions"] if v["tag"] == active), None)
            if version and versions.should_promote(version):
                versions.promote(skill_dir)
                await pubsub.publish(
                    AdminNotification(
                        content=f"⬆️ Promoted canary `{active}` of skill *{skill}* to stable "
                        f"after {version['successes']} successful runs."
                    )
                )

    async def _maybe_rollback_and_rerun(self, trigger: TaskTrigger, skill_versions: dict[str, str]) -> None:
        rolled_back = []
        for skill, active in skill_versions.items():
            skill_dir = self._skill_dir(skill)
            if skill_dir is None:
                continue
            ledger = versions.status(skill_dir)
            if ledger.get("canary") == active and ledger.get("stable") and ledger.get("stable") != active:
                versions.rollback(skill_dir)
                rolled_back.append((skill, active, ledger["stable"]))

        if not rolled_back:
            return

        summary = ", ".join(f"*{s}* canary `{c}` → stable `{st}`" for s, c, st in rolled_back)
        await pubsub.publish(
            AdminNotification(
                content=f"⚠️ Task '{trigger.name}' failed on a canary; rolled back {summary}. Re-running on stable."
            )
        )

        rerun_thread = random.randint(0, 2**63 - 1)
        rerun = await self._run_task(TaskRequest(task=trigger.task, thread_id=rerun_thread))
        if rerun and self._job_execution_repo is not None:
            stable_versions = {s: st for s, _, st in rolled_back}
            await self._job_execution_repo.record(
                job_name=f"{trigger.name} (self-heal rerun)",
                skill_names=rerun.skill_names,
                thread_id=rerun.thread_id,
                success=rerun.success,
                error=rerun.error,
                cost_usd=rerun.cost_usd,
                duration_s=rerun.duration_s,
                tool_call_count=len(rerun.tool_call_names),
                skill_versions=stable_versions,
            )
            for skill, st in stable_versions.items():
                skill_dir = self._skill_dir(skill)
                if skill_dir is not None:
                    try:
                        versions.record_outcome(skill_dir, st, rerun.success)
                    except ValueError:
                        pass

    async def _handle_stop_task(self, request: StopTaskRequest) -> None:
        await self.stop_task(request.thread_id)

    async def stop_task(self, thread_id: int) -> bool:
        cancelled = False
        for task_id, owner_thread in list(self._bg_threads.items()):
            handle = self._bg_handles.get(task_id)
            if owner_thread == thread_id and handle and not handle.done():
                handle.cancel()
                cancelled = True
        task = self._tasks.get(thread_id)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            cancelled = True
        return cancelled
