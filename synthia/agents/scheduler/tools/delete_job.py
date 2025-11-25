from typing import Any

from claude_agent_sdk import tool

from synthia.agents.scheduler.service import SchedulerService


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
        name = args.get("name", "")

        try:
            deleted = scheduler_service.delete_job(name)
            if deleted:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Job '{name}' deleted successfully.",
                        }
                    ]
                }
            else:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Job '{name}' not found.",
                        }
                    ],
                    "isError": True,
                }
        except Exception as error:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error deleting job: {str(error)}",
                    }
                ],
                "isError": True,
            }

    return delete_job
