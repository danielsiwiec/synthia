from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from synthia.service.project_repository import ProjectRepository

if TYPE_CHECKING:
    from synthia.service.chat import ChatService


def create_project_tools(repository: ProjectRepository) -> list[Callable]:
    from synthia.agents.projects.tools.delete_project import create_delete_project_tool
    from synthia.agents.projects.tools.list_projects import create_list_projects_tool
    from synthia.agents.projects.tools.update_project import create_update_project_tool

    return [
        create_list_projects_tool(repository),
        create_update_project_tool(repository),
        create_delete_project_tool(repository),
    ]


def create_project_thread_tools(
    repository: ProjectRepository, chat_service: ChatService, thread_id: int
) -> list[Callable]:
    from synthia.agents.projects.tools.add_section import create_add_section_tool
    from synthia.agents.projects.tools.attach_media import create_attach_media_tool
    from synthia.agents.projects.tools.create_project import create_create_project_tool
    from synthia.agents.projects.tools.select_project import create_select_project_tool

    return [
        create_create_project_tool(repository, chat_service.repository, thread_id),
        create_select_project_tool(repository, thread_id),
        create_add_section_tool(repository),
        create_attach_media_tool(repository, chat_service, thread_id),
    ]
