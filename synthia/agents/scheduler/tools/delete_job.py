from collections.abc import Callable

from synthia.agents.scheduler.service import SchedulerService
from synthia.agents.tools import error_response, success_response


def create_delete_job_tool(scheduler_service: SchedulerService) -> Callable:
    async def delete_job(name: str) -> str:
        """Delete a scheduled job by its name.

        Args:
            name: The name/identifier of the job to delete.
        """
        try:
            if scheduler_service.delete_job(name):
                return success_response(f"Job '{name}' deleted successfully.")
            return error_response(f"Job '{name}' not found.")
        except Exception as error:
            return error_response(f"Error deleting job: {error}")

    return delete_job
