from typing import Any

from claude_agent_sdk import tool

from synthia.agents.scheduler.service import SchedulerService


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
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "All jobs deleted successfully.",
                    }
                ]
            }
        except Exception as error:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error deleting all jobs: {str(error)}",
                    }
                ],
                "isError": True,
            }

    return delete_all_jobs
