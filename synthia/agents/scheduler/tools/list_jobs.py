import json
from collections.abc import Callable

from synthia.agents.scheduler.service import SchedulerService
from synthia.agents.tools import error_response, success_response


def create_list_jobs_tool(scheduler_service: SchedulerService) -> Callable:
    async def list_jobs() -> str:
        """List all currently scheduled jobs with their names, interval settings, and next run times."""
        try:
            jobs = scheduler_service.list_jobs()
            if not jobs:
                return success_response("No scheduled jobs found.")
            return success_response(json.dumps(jobs, indent=2))
        except Exception as error:
            return error_response(f"Error listing jobs: {error}")

    return list_jobs
