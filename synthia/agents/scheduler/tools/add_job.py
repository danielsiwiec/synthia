from collections.abc import Callable

from synthia.agents.scheduler.service import SchedulerService
from synthia.agents.tools import error_response, success_response


def create_add_job_tool(scheduler_service: SchedulerService) -> Callable:
    async def add_job(name: str, start_date: str, seconds: float, task: str, silent: bool = False) -> str:
        """Add a new scheduled job that will trigger a task at specified intervals. Use this to
        schedule recurring tasks like daily reports, periodic checks, or reminders.

        Args:
            name: Unique name/identifier for the job.
            start_date: Start date/time for the job in ISO format (e.g., '2024-01-01T09:00:00'). The
                job will first run at this time, then repeat at the specified interval.
            seconds: Interval in seconds between job executions.
            task: The task description to execute when the job triggers.
            silent: If true, suppress admin notifications when the job completes. Defaults to false.
        """
        try:
            job_info = scheduler_service.add_job(name, start_date, seconds, task, silent)
            return success_response(
                f"Job '{job_info['name']}' added successfully with start_date "
                f"'{job_info['start_date']}' and interval {job_info['seconds']} seconds"
            )
        except Exception as error:
            return error_response(f"Error adding job: {error}")

    return add_job
