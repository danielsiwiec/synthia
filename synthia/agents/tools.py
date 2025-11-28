from typing import Any


def success_response(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def error_response(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": True}
