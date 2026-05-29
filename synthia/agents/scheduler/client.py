from collections.abc import Callable

from synthia.agents.scheduler.service import SchedulerService


def create_scheduler_tools(postgres_url: str) -> tuple[list[Callable], SchedulerService]:
    from synthia.agents.scheduler.tools.add_job import create_add_job_tool
    from synthia.agents.scheduler.tools.delete_all_jobs import create_delete_all_jobs_tool
    from synthia.agents.scheduler.tools.delete_job import create_delete_job_tool
    from synthia.agents.scheduler.tools.list_jobs import create_list_jobs_tool
    from synthia.agents.scheduler.tools.trigger_job import create_trigger_job_tool

    scheduler_service = SchedulerService(postgres_url=postgres_url)

    tools = [
        create_add_job_tool(scheduler_service),
        create_list_jobs_tool(scheduler_service),
        create_delete_job_tool(scheduler_service),
        create_delete_all_jobs_tool(scheduler_service),
        create_trigger_job_tool(scheduler_service),
    ]
    return tools, scheduler_service
