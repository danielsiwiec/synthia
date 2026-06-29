import mimetypes
from collections.abc import Callable
from pathlib import Path

from synthia.agents.projects.tools._serialize import serialize_project
from synthia.agents.tools import error_response, success_response
from synthia.service.chat import ChatService
from synthia.service.project_repository import ProjectRepository


def create_attach_media_tool(repository: ProjectRepository, chat_service: ChatService, thread_id: int) -> Callable:
    async def attach_project_media(project_id: str, path: str, caption: str = "") -> str:
        """Attach a media file (image, document, or any file you have on disk) to a project. The file
        is stored with the project and shown at the bottom of the project view. Use this for files
        the user should see attached to the project — screenshots, generated images, PDFs, etc.

        Args:
            project_id: The id of the project to attach the file to (from list_projects).
            path: The local filesystem path to the file to attach. The file must already exist.
            caption: Optional short caption shown with the media.
        """
        src = Path(path)
        if not src.is_file():
            return error_response(f"File not found: {path}")
        try:
            dest = await chat_service.save_file_by_path(thread_id, src)
            content_type = mimetypes.guess_type(dest.name)[0] or "application/octet-stream"
            project = await repository.add_media(
                project_id, name=src.name, content_type=content_type, file=dest.name, caption=caption
            )
            if project is None:
                return error_response(f"Project {project_id} not found.")
            return success_response(f"Media attached:\n{serialize_project(project)}")
        except Exception as error:
            return error_response(f"Error attaching media: {error}")

    return attach_project_media
