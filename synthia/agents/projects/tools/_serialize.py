import json
from typing import Any


def serialize_project(project: dict[str, Any]) -> str:
    return json.dumps(
        {
            "id": str(project["id"]),
            "name": project["name"],
            "status": project["status"],
            "next_step": project.get("next_step", ""),
            "document": project["document"],
            "created_at": project["created_at"].isoformat() if project.get("created_at") else None,
            "updated_at": project["updated_at"].isoformat() if project.get("updated_at") else None,
        },
        indent=2,
    )
