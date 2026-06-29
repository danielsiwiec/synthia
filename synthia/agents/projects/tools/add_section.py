from collections.abc import Callable

from synthia.agents.projects.tools._serialize import serialize_project
from synthia.agents.tools import error_response, success_response
from synthia.service.project_repository import ProjectRepository


def create_add_section_tool(repository: ProjectRepository) -> Callable:
    async def add_project_section(project_id: str, title: str, body: str = "") -> str:
        """Add a new section to a project. Sections are ordered blocks of markdown shown above the
        project's main document; a new section is appended after the existing ones. Use this to add
        a distinct, titled chunk of content (a plan, a checklist, findings, etc.) rather than editing
        the main document.

        Args:
            project_id: The id of the project to add the section to (from list_projects).
            title: A short heading for the section.
            body: The section's markdown content.
        """
        try:
            project = await repository.add_section(project_id, title, body)
            if project is None:
                return error_response(f"Project {project_id} not found.")
            return success_response(f"Section added:\n{serialize_project(project)}")
        except Exception as error:
            return error_response(f"Error adding section: {error}")

    return add_project_section
