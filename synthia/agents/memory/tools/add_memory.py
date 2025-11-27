from typing import Any

from claude_agent_sdk import tool
from mem0 import AsyncMemory

from synthia.agents.tools import error_response, success_response


def create_add_memory_tool(user: str, memory_client: AsyncMemory):
    @tool(
        "add-memory",
        (
            "Add a new memory about the user. Call this whenever the user shares preferences, "
            "facts about themselves, or explicitly asks you to remember something."
        ),
        {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The content to store in memory"},
                "userId": {
                    "type": "string",
                    "description": "User ID for memory storage. If omitted, uses config.defaultUserId.",
                },
            },
            "required": ["content"],
        },
    )
    async def add_memory(args: dict[str, Any]) -> dict[str, Any]:
        content = args["content"]
        user_id = args.get("userId") or user

        try:
            messages = [{"role": "user", "content": content}]
            await memory_client.add(messages, user_id=user_id)
            return success_response("Memory added successfully")
        except Exception as error:
            return error_response(f"Error adding memory: {error}")

    return add_memory
