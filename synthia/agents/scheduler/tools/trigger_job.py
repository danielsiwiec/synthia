from collections.abc import Callable

from synthia.agents.scheduler.service import SchedulerService
from synthia.agents.tools import error_response, success_response


def create_trigger_job_tool(scheduler_service: SchedulerService) -> Callable:
    async def trigger_job(name: str) -> str:
        """Trigger an existing scheduled job to run immediately, without waiting for its next
        scheduled time.

        Args:
            name: The name/identifier of the job to trigger.
        """
        try:
            if await scheduler_service.trigger_job(name):
                return success_response(f"Job '{name}' triggered for immediate execution.")
            return error_response(f"Job '{name}' not found.")
        except Exception as error:
            return error_response(f"Error triggering job: {error}")

    return trigger_job
