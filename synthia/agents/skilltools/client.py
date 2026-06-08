from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from synthia.agents.skilltools import versions
from synthia.agents.tools import error_response, success_response
from synthia.service.job_execution_repository import JobExecutionRepository


def _default_user_skills_dir() -> Path:
    return Path.home() / ".claude" / "skills"


def create_skilltools_tools(
    job_execution_repo: JobExecutionRepository | None = None,
    user_skills_dir: str | Path | None = None,
) -> list[Callable]:
    skills_root = Path(user_skills_dir) if user_skills_dir else _default_user_skills_dir()

    def _resolve(skill: str) -> tuple[Path | None, str | None]:
        skill_dir = skills_root / skill
        if not skill_dir.is_dir():
            return None, (
                f"Skill '{skill}' is not a user-defined skill under {skills_root}. "
                "The optimizer may only modify user skills, not built-in skills."
            )
        return skill_dir, None

    async def skill_version_status(skill: str) -> str:
        """Show the version ledger for a user skill: active/stable/canary tags and per-version
        run outcomes (runs/successes/failures).

        Args:
            skill: The user skill name (folder under the user skills directory).
        """
        skill_dir, err = _resolve(skill)
        if skill_dir is None:
            return error_response(err or "")
        return success_response(json.dumps(versions.status(skill_dir), indent=2, default=str))

    async def skill_baseline(skill: str) -> str:
        """Capture the CURRENT, unmodified skill files as the stable baseline version. Call this
        BEFORE editing a skill so the optimizer can always roll back to the last known-good version.
        No-op if a stable baseline already exists.

        Args:
            skill: The user skill name.
        """
        skill_dir, err = _resolve(skill)
        if skill_dir is None:
            return error_response(err or "")
        tag = versions.ensure_baseline(skill_dir)
        return success_response(f"Baseline stable version is '{tag}'.")

    async def skill_set_canary(skill: str, notes: str = "") -> str:
        """Snapshot the current (already edited) skill files as a new CANARY version and make it the
        active version. The canary stays live but is monitored: the daily-run self-heal guard
        automatically rolls back to stable if a canary run fails, and promotes it to stable after it
        accumulates enough successful runs. Call this AFTER editing the skill and validating its
        changed subcomponents.

        Args:
            skill: The user skill name.
            notes: Short description of what changed and why.
        """
        skill_dir, err = _resolve(skill)
        if skill_dir is None:
            return error_response(err or "")
        versions.ensure_baseline(skill_dir)
        status = versions.status(skill_dir)
        tag = versions.snapshot(skill_dir, status="canary", notes=notes)
        if tag == status.get("stable"):
            return error_response("Current files are identical to the stable version — nothing to canary.")
        return success_response(f"Canary version '{tag}' is now active (stable fallback: {status.get('stable')}).")

    async def skill_promote(skill: str) -> str:
        """Promote the active canary version to stable. Normally the self-heal guard does this
        automatically after enough successful runs; use this only to promote manually.

        Args:
            skill: The user skill name.
        """
        skill_dir, err = _resolve(skill)
        if skill_dir is None:
            return error_response(err or "")
        try:
            result = versions.promote(skill_dir)
        except ValueError as e:
            return error_response(str(e))
        return success_response(json.dumps(result))

    async def skill_rollback(skill: str) -> str:
        """Restore the stable version's files over the live skill files and retire the canary. Use
        this to manually abandon a bad optimization.

        Args:
            skill: The user skill name.
        """
        skill_dir, err = _resolve(skill)
        if skill_dir is None:
            return error_response(err or "")
        try:
            result = versions.rollback(skill_dir)
        except (ValueError, FileNotFoundError) as e:
            return error_response(str(e))
        return success_response(json.dumps(result))

    async def skill_list_executions(skill: str, days: int = 14) -> str:
        """List recent recorded executions of a skill (success/failure, cost, duration, tool-call
        count) from the job execution ledger. Use this to find which skills are failing, slow, or
        expensive and worth optimizing.

        Args:
            skill: The user skill name.
            days: How many days back to look (default 14).
        """
        if job_execution_repo is None:
            return error_response("Job execution ledger is not available.")
        rows = await job_execution_repo.recent_for_skill(skill, days=days)
        if not rows:
            return success_response(f"No recorded executions for skill '{skill}' in the last {days} days.")
        return success_response(json.dumps(rows, indent=2, default=str))

    async def skill_record_outcome(skill: str, version_tag: str, success: bool) -> str:
        """Record the outcome of running a specific skill version against the version ledger.

        Args:
            skill: The user skill name.
            version_tag: The version tag that ran.
            success: Whether the run succeeded.
        """
        skill_dir, err = _resolve(skill)
        if skill_dir is None:
            return error_response(err or "")
        try:
            version = versions.record_outcome(skill_dir, version_tag, success)
        except ValueError as e:
            return error_response(str(e))
        return success_response(json.dumps(version, default=str))

    return [
        skill_version_status,
        skill_baseline,
        skill_set_canary,
        skill_promote,
        skill_rollback,
        skill_list_executions,
        skill_record_outcome,
    ]
