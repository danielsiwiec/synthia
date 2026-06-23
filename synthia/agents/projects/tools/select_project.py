from collections.abc import Callable

from synthia.agents.tools import error_response, success_response
from synthia.helpers.pubsub import pubsub
from synthia.service.models import ProjectSelected
from synthia.service.project_repository import ProjectRepository


def create_select_project_tool(repository: ProjectRepository, thread_id: int) -> Callable:
    async def select_project(project_id: str) -> str:
        """Open a project in the user's view and make it the selected one, so you are both working
        in the context of that project. Use this when the user asks to open, switch to, or start
        working on a specific project. If you don't know the project's id, call list_projects first
        to look it up, then pass that id here.

        Args:
            project_id: The id of the project to open (from list_projects).
        """
        try:
            project = await repository.get(project_id)
        except Exception as error:
            return error_response(f"Error selecting project: {error}")
        if project is None:
            return error_response(f"Project {project_id} not found.")
        await pubsub.publish(ProjectSelected(thread_id=thread_id, project_id=str(project["id"]), name=project["name"]))
        return success_response(f'Opened project "{project["name"]}" in the user\'s view.')

    return select_project
