from typing import Any

from claude_agent_sdk import tool

from synthia.agents.scheduler.service import SchedulerService
from synthia.agents.tools import error_response, success_response


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
        try:
            job_info = scheduler_service.add_job(args["name"], args["start_date"], args["seconds"], args["task"])
            return success_response(
                f"Job '{job_info['name']}' added successfully with start_date "
                f"'{job_info['start_date']}' and interval {job_info['seconds']} seconds"
            )
        except Exception as error:
            return error_response(f"Error adding job: {error}")

    return add_job
