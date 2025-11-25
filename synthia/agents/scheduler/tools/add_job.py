from typing import Any

from claude_agent_sdk import tool

from synthia.agents.scheduler.service import SchedulerService


def create_add_job_tool(scheduler_service: SchedulerService):
    @tool(
        "add-job",
        (
            "Add a new scheduled job that will trigger a task at specified intervals. "
            "Use this to schedule recurring tasks like daily reports, periodic checks, or reminders."
        ),
        {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name/identifier for the job",
                },
                "start_date": {
                    "type": "string",
                    "description": (
                        "Start date/time for the job in ISO format (e.g., '2024-01-01T09:00:00'). "
                        "The job will first run at this time, then repeat at the specified interval."
                    ),
                },
                "seconds": {
                    "type": "number",
                    "description": "Interval in seconds between job executions",
                },
                "task": {
                    "type": "string",
                    "description": "The task description to execute when the job triggers",
                },
            },
            "required": ["name", "start_date", "seconds", "task"],
        },
    )
    async def add_job(args: dict[str, Any]) -> dict[str, Any]:
        name = args.get("name", "")
        start_date = args.get("start_date", "")
        seconds = args.get("seconds", 0)
        task = args.get("task", "")

        try:
            job_info = scheduler_service.add_job(name, start_date, seconds, task)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Job '{job_info['name']}' added successfully with start_date "
                            f"'{job_info['start_date']}' and interval {job_info['seconds']} seconds"
                        ),
                    }
                ]
            }
        except Exception as error:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error adding job: {str(error)}",
                    }
                ],
                "isError": True,
            }

    return add_job
