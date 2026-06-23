import json
from collections.abc import Callable

from synthia.agents.projects.tools._serialize import serialize_project
from synthia.agents.tools import error_response, success_response
from synthia.service.project_repository import ProjectRepository


def create_list_projects_tool(repository: ProjectRepository) -> Callable:
    async def list_projects() -> str:
        """List all of the user's projects with their id, name, status (active/closed), creation
        date, and markdown document."""
        try:
            projects = await repository.list_all()
            if not projects:
                return success_response("No projects found.")
            return success_response(json.dumps([json.loads(serialize_project(p)) for p in projects], indent=2))
        except Exception as error:
            return error_response(f"Error listing projects: {error}")

    return list_projects
