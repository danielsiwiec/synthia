from typing import Any

from claude_agent_sdk import create_sdk_mcp_server

from synthia.agents.scheduler.service import SchedulerService


def create_scheduler_mcp_server(scheduler_service: SchedulerService) -> Any:
    from synthia.agents.scheduler.tools.add_job import create_add_job_tool
    from synthia.agents.scheduler.tools.delete_all_jobs import create_delete_all_jobs_tool
    from synthia.agents.scheduler.tools.delete_job import create_delete_job_tool
    from synthia.agents.scheduler.tools.list_jobs import create_list_jobs_tool
    from synthia.agents.scheduler.tools.trigger_job import create_trigger_job_tool

    tools = [
        create_add_job_tool(scheduler_service),
        create_list_jobs_tool(scheduler_service),
        create_delete_job_tool(scheduler_service),
        create_delete_all_jobs_tool(scheduler_service),
        create_trigger_job_tool(scheduler_service),
    ]
    return create_sdk_mcp_server(name="scheduler", version="0.0.1", tools=tools)
