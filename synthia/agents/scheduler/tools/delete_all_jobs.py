from collections.abc import Callable

from synthia.agents.scheduler.service import SchedulerService
from synthia.agents.tools import error_response, success_response


def create_delete_all_jobs_tool(scheduler_service: SchedulerService) -> Callable:
    async def delete_all_jobs() -> str:
        """Delete all scheduled jobs. Use this to clear the entire job schedule."""
        try:
            await scheduler_service.delete_all_jobs()
            return success_response("All jobs deleted successfully.")
        except Exception as error:
            return error_response(f"Error deleting all jobs: {error}")

    return delete_all_jobs
