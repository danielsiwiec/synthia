from typing import Any

from claude_agent_sdk import tool

from synthia.agents.scheduler.service import SchedulerService


def create_trigger_job_tool(scheduler_service: SchedulerService):
    @tool(
        "trigger-job",
        "Trigger an existing scheduled job to run immediately, without waiting for its next scheduled time.",
        {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name/identifier of the job to trigger",
                },
            },
            "required": ["name"],
        },
    )
    async def trigger_job(args: dict[str, Any]) -> dict[str, Any]:
        name = args.get("name", "")

        try:
            triggered = await scheduler_service.trigger_job(name)
            if triggered:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Job '{name}' triggered for immediate execution.",
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
                        "text": f"Error triggering job: {str(error)}",
                    }
                ],
                "isError": True,
            }

    return trigger_job
