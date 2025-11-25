import json
from typing import Any

from claude_agent_sdk import tool

from synthia.agents.scheduler.service import SchedulerService


def create_list_jobs_tool(scheduler_service: SchedulerService):
    @tool(
        "list-jobs",
        "List all currently scheduled jobs with their names, interval settings, and next run times.",
        {
            "type": "object",
            "properties": {},
            "required": [],
        },
    )
    async def list_jobs(args: dict[str, Any]) -> dict[str, Any]:
        try:
            jobs = scheduler_service.list_jobs()
            if not jobs:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "No scheduled jobs found.",
                        }
                    ]
                }
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(jobs, indent=2),
                    }
                ]
            }
        except Exception as error:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error listing jobs: {str(error)}",
                    }
                ],
                "isError": True,
            }

    return list_jobs
