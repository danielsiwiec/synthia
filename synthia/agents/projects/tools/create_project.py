from collections.abc import Callable

from synthia.agents.projects.tools._serialize import serialize_project
from synthia.agents.tools import error_response, success_response
from synthia.service.project_repository import ProjectRepository


def create_create_project_tool(repository: ProjectRepository) -> Callable:
    async def create_project(name: str, document: str = "", next_step: str = "") -> str:
        """Create a new project for the user. A project is a tracked piece of work with a status, a
        creation date, a single next step, and a markdown document holding its details, plan, or notes.

        Args:
            name: A short title for the project (shown in the project list).
            document: The project's markdown document — its details, plan, or notes. Optional; you
                can fill it in or expand it later with update_project.
            next_step: A short statement (about 5-10 words) of the single next action for this
                project. Keep it concise and actionable.
        """
        try:
            project = await repository.create(name=name, document=document, next_step=next_step)
            return success_response(f"Project created:\n{serialize_project(project)}")
        except Exception as error:
            return error_response(f"Error creating project: {error}")

    return create_project
