from collections.abc import Callable

from synthia.agents.scheduler.service import SchedulerService
from synthia.agents.tools import error_response, success_response


def create_add_one_shot_job_tool(scheduler_service: SchedulerService) -> Callable:
    async def add_one_shot_job(name: str, run_date: str, task: str, silent: bool = False) -> str:
        """Schedule a job that runs exactly ONCE at a specific date/time and is then automatically
        removed. Use this for deferred or one-time tasks (e.g. "check on this later", "remind me at
        9am tomorrow"). Prefer this over add_job whenever the task should NOT repeat — add_job
        creates a recurring job that keeps firing on its interval until explicitly deleted.

        Args:
            name: Unique name/identifier for the job.
            run_date: Date/time to run the job in ISO format (e.g., '2024-01-01T09:00:00'). The job
                fires once at this time, then removes itself.
            task: The task description to execute when the job triggers.
            silent: If true, suppress admin notifications when the job completes. Defaults to false.
        """
        try:
            job_info = scheduler_service.add_one_shot_job(name, run_date, task, silent)
            return success_response(
                f"One-shot job '{job_info['name']}' scheduled to run once at '{job_info['run_date']}'"
            )
        except Exception as error:
            return error_response(f"Error adding one-shot job: {error}")

    return add_one_shot_job
