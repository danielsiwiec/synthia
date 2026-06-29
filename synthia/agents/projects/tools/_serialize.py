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
            "sections": [
                {"id": s["id"], "title": s.get("title", ""), "body": s.get("body", "")}
                for s in project.get("sections", [])
            ],
            "media": [
                {"id": m["id"], "name": m.get("name", ""), "caption": m.get("caption", "")}
                for m in project.get("media", [])
            ],
            "created_at": project["created_at"].isoformat() if project.get("created_at") else None,
            "updated_at": project["updated_at"].isoformat() if project.get("updated_at") else None,
        },
        indent=2,
    )
