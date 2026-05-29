from collections.abc import Callable

from mem0 import AsyncMemory

from synthia.agents.tools import error_response, success_response


def create_delete_memory_tool(memory_client: AsyncMemory) -> Callable:
    async def delete_memory(memory_id: str) -> str:
        """Delete a memory by its ID. Call this when the user explicitly asks to forget or remove a
        specific memory.

        Args:
            memory_id: The unique ID of the memory to delete.
        """
        try:
            await memory_client.delete(memory_id)
            return success_response("Memory deleted successfully")
        except Exception as error:
            return error_response(f"Error deleting memory: {error}")

    return delete_memory
