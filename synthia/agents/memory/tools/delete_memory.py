from typing import Any

from claude_agent_sdk import tool
from mem0 import AsyncMemory

from synthia.agents.tools import error_response, success_response


def create_delete_memory_tool(memory_client: AsyncMemory):
    @tool(
        "delete-memory",
        ("Delete a memory by its ID. Call this when the user explicitly asks to forget or remove a specific memory."),
        {
            "type": "object",
            "properties": {
                "memoryId": {
                    "type": "string",
                    "description": "The unique ID of the memory to delete.",
                },
            },
            "required": ["memoryId"],
        },
    )
    async def delete_memory(args: dict[str, Any]) -> dict[str, Any]:
        try:
            await memory_client.delete(args["memoryId"])
            return success_response("Memory deleted successfully")
        except Exception as error:
            return error_response(f"Error deleting memory: {error}")

    return delete_memory
