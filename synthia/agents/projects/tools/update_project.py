from collections.abc import Callable

from synthia.agents.projects.tools._serialize import serialize_project
from synthia.agents.tools import error_response, success_response
from synthia.service.project_repository import VALID_STATUSES, ProjectRepository


def create_update_project_tool(repository: ProjectRepository) -> Callable:
    async def update_project(
        project_id: str, name: str = "", status: str = "", document: str = "", next_step: str = ""
    ) -> str:
        """Update an existing project. Use this to rename it, change its status, edit its markdown
        document, or set its next step. Only the fields you pass are changed; omit a field to leave
        it unchanged.

        Args:
            project_id: The id of the project to update (from list_projects).
            name: Optional new title.
            status: Optional new status — either 'active' or 'closed'.
            document: Optional new markdown document. This REPLACES the existing document, so include
                the full updated content, not just the change.
            next_step: Optional new next step — a short statement (about 5-10 words) of the single
                next action. Keep it updated as the project progresses.
        """
        if status and status not in VALID_STATUSES:
            return error_response(f"Invalid status '{status}'. Use one of: {', '.join(VALID_STATUSES)}.")
        try:
            project = await repository.update(
                project_id=project_id,
                name=name or None,
                status=status or None,
                document=document or None,
                next_step=next_step or None,
            )
            if project is None:
                return error_response(f"Project {project_id} not found.")
            return success_response(f"Project updated:\n{serialize_project(project)}")
        except Exception as error:
            return error_response(f"Error updating project: {error}")

    return update_project
