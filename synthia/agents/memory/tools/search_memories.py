from collections.abc import Callable

from mem0 import AsyncMemory

from synthia.agents.tools import error_response, success_response


def _format_memory(result: dict) -> str:
    return f"ID: {result.get('id', '')}\nMemory: {result.get('memory', '')}\nRelevance: {result.get('score', '')}\n---"


def create_search_memories_tool(memory_client: AsyncMemory) -> Callable:
    async def search_memories(query: str) -> str:
        """Search through stored memories. Call this whenever you need to recall prior information
        relevant to the user query.

        Args:
            query: The search query, typically derived from the user's current question.
        """
        try:
            results = await memory_client.search(query, filters={"user_id": "default"})
            items = results.get("results") if isinstance(results, dict) else results
            if items:
                formatted_results = "\n".join(_format_memory(r) for r in items)
                return success_response(formatted_results)
            return success_response("No memories found")
        except Exception as error:
            return error_response(f"Error searching memories: {error}")

    return search_memories
