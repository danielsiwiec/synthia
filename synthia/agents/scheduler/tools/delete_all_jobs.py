from typing import Any

from claude_agent_sdk import tool

from synthia.agents.scheduler.service import SchedulerService
from synthia.agents.tools import error_response, success_response


def create_delete_all_jobs_tool(scheduler_service: SchedulerService):
    @tool(
        "delete-all-jobs",
        "Delete all scheduled jobs. Use this to clear the entire job schedule.",
        {
            "type": "object",
            "properties": {},
            "required": [],
        },
    )
    async def delete_all_jobs(args: dict[str, Any]) -> dict[str, Any]:
        try:
            await scheduler_service.delete_all_jobs()
            return success_response("All jobs deleted successfully.")
        except Exception as error:
            return error_response(f"Error deleting all jobs: {error}")

    return delete_all_jobs
