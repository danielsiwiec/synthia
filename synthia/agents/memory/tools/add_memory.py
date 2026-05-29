from collections.abc import Callable

from mem0 import AsyncMemory

from synthia.agents.tools import error_response, success_response


def create_add_memory_tool(memory_client: AsyncMemory) -> Callable:
    async def add_memory(content: str) -> str:
        """Store a fact about the user. Call this whenever the user shares preferences, facts about
        themselves, or explicitly asks you to remember something. Content is stored verbatim, so
        extract a concise factual statement (e.g. 'Favorite color is blue') rather than passing raw
        conversation text.

        Args:
            content: A concise factual statement to store, e.g. 'Favorite color is blue'.
        """
        try:
            messages = [{"role": "user", "content": content}]
            await memory_client.add(messages, user_id="default", infer=False)
            return success_response("Memory added successfully")
        except Exception as error:
            return error_response(f"Error adding memory: {error}")

    return add_memory
