from typing import Any

from claude_agent_sdk import tool
from mem0 import AsyncMemory

from synthia.agents.tools import error_response, success_response


def _format_memory(result: dict) -> str:
    return f"ID: {result.get('id', '')}\nMemory: {result.get('memory', '')}\nRelevance: {result.get('score', '')}\n---"


def create_search_memories_tool(user: str, memory_client: AsyncMemory):
    @tool(
        "search-memories",
        (
            "Search through stored memories. Call this whenever you need to recall prior "
            "information relevant to the user query."
        ),
        {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query, typically derived from the user's current question.",
                },
                "userId": {
                    "type": "string",
                    "description": "User ID for memory storage. If omitted, uses config.defaultUserId.",
                },
            },
            "required": ["query"],
        },
    )
    async def search_memories(args: dict[str, Any]) -> dict[str, Any]:
        query = args["query"]
        user_id = args.get("userId") or user

        try:
            results = await memory_client.search(query, user_id=user_id)
            items = results.get("results") if isinstance(results, dict) else results
            if items:
                formatted_results = "\n".join(_format_memory(r) for r in items)
                return success_response(formatted_results)
            return success_response("No memories found")
        except Exception as error:
            return error_response(f"Error searching memories: {error}")

    return search_memories
