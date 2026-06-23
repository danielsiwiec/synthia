from collections.abc import Callable

from synthia.service.project_repository import ProjectRepository


def create_project_tools(repository: ProjectRepository) -> list[Callable]:
    from synthia.agents.projects.tools.create_project import create_create_project_tool
    from synthia.agents.projects.tools.delete_project import create_delete_project_tool
    from synthia.agents.projects.tools.list_projects import create_list_projects_tool
    from synthia.agents.projects.tools.update_project import create_update_project_tool

    return [
        create_create_project_tool(repository),
        create_list_projects_tool(repository),
        create_update_project_tool(repository),
        create_delete_project_tool(repository),
    ]
