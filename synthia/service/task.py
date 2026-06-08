import asyncio
import random
from pathlib import Path
from typing import Any

from google.adk.sessions import BaseSessionService
from google.adk.tools.skill_toolset import SkillToolset
from loguru import logger

from synthia.agents.agent import Agent, Result, create_diagram_tool, create_image_tool
from synthia.agents.skills import reload_skills
from synthia.agents.skilltools import versions
from synthia.helpers.pubsub import pubsub
from synthia.service.job_execution_repository import JobExecutionRepository
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
        tools: list[Any],
        session_repository: SessionRepository,
        session_service: BaseSessionService,
        cwd: str | Path | None = None,
        job_execution_repo: JobExecutionRepository | None = None,
        user_skills_dir: str | Path | None = None,
        skill_toolset: SkillToolset | None = None,
    ):
        self._tools = tools
        self._session_service = session_service
        self._cwd = cwd
        self._tasks: dict[int, asyncio.Task] = {}
        self._session_repository = session_repository
        self._job_execution_repo = job_execution_repo
        self._skill_toolset = skill_toolset
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
            agent = await Agent.create(
                tools=[*self._tools, image_tool, diagram_tool],
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
        task = self._tasks.get(thread_id)
        if not task:
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True
