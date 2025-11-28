from typing import Any

from claude_agent_sdk import tool

from synthia.agents.scheduler.service import SchedulerService
from synthia.agents.tools import error_response, success_response


def create_delete_job_tool(scheduler_service: SchedulerService):
    @tool(
        "delete-job",
        "Delete a scheduled job by its name.",
        {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name/identifier of the job to delete",
                },
            },
            "required": ["name"],
        },
    )
    async def delete_job(args: dict[str, Any]) -> dict[str, Any]:
        name = args["name"]
        try:
            if scheduler_service.delete_job(name):
                return success_response(f"Job '{name}' deleted successfully.")
            return error_response(f"Job '{name}' not found.")
        except Exception as error:
            return error_response(f"Error deleting job: {error}")

    return delete_job
