from collections.abc import Callable

from synthia.agents.tools import error_response, success_response
from synthia.service.project_repository import ProjectRepository


def create_delete_project_tool(repository: ProjectRepository) -> Callable:
    async def delete_project(project_id: str) -> str:
        """Delete a project permanently by its id.

        Args:
            project_id: The id of the project to delete (from list_projects).
        """
        try:
            if await repository.delete(project_id):
                return success_response(f"Project {project_id} deleted.")
            return error_response(f"Project {project_id} not found.")
        except Exception as error:
            return error_response(f"Error deleting project: {error}")

    return delete_project
