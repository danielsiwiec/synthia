from typing import Any

from claude_agent_sdk import tool
from mem0 import AsyncMemory


def create_delete_memory_tool(user: str, memory_client: AsyncMemory):
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
                "userId": {
                    "type": "string",
                    "description": "User ID for memory storage. If omitted, uses config.defaultUserId.",
                },
            },
            "required": ["memoryId"],
        },
    )
    async def delete_memory(args: dict[str, Any]) -> dict[str, Any]:
        memory_id = args.get("memoryId", "")

        try:
            await memory_client.delete(memory_id)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Memory deleted successfully",
                    }
                ]
            }
        except Exception as error:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error deleting memory: {str(error)}",
                    }
                ],
                "isError": True,
            }

    return delete_memory
