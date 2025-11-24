from typing import Any

from claude_agent_sdk import tool
from mem0 import AsyncMemory


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
        query = args.get("query", "")
        user_id = args.get("userId") or user

        try:
            results = await memory_client.search(query, user_id=user_id)
            if results and isinstance(results, dict) and results.get("results"):
                formatted_results = "\n".join(
                    [
                        f"ID: {result.get('id', '')}\nMemory: {result.get('memory', '')}\n"
                        f"Relevance: {result.get('score', '')}\n---"
                        for result in results["results"]
                    ]
                )
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": formatted_results,
                        }
                    ]
                }
            elif results and isinstance(results, list):
                formatted_results = "\n".join(
                    [
                        f"ID: {result.get('id', '')}\nMemory: {result.get('memory', '')}\n"
                        f"Relevance: {result.get('score', '')}\n---"
                        for result in results
                    ]
                )
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": formatted_results,
                        }
                    ]
                }
            else:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "No memories found",
                        }
                    ]
                }
        except Exception as error:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error searching memories: {str(error)}",
                    }
                ],
                "isError": True,
            }

    return search_memories
