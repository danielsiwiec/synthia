from typing import Any

import asyncpg
from claude_agent_sdk import tool

from synthia.agents.tools import error_response, success_response


def create_show_tool(pool: asyncpg.Pool):
    @tool(
        "episodic-show",
        "Retrieve the full transcript of a specific Synthia conversation by ID.",
        {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "The UUID of the conversation to retrieve",
                },
            },
            "required": ["conversation_id"],
        },
    )
    async def show(args: dict[str, Any]) -> dict[str, Any]:
        conversation_id = args["conversation_id"]

        try:
            async with pool.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT id, transcript, summary, created_at
                    FROM conversations
                    WHERE id = $1::uuid
                    """,
                    conversation_id,
                )

                if not result:
                    return success_response(f"No conversation found with ID: {conversation_id}")

                return success_response(f"""**Conversation {result["id"]}**
- Date: {result["created_at"].strftime("%Y-%m-%d %H:%M")}

**Summary:**
{result["summary"]}

**Full Transcript:**
{result["transcript"]}
""")
        except Exception as e:
            return error_response(f"Error retrieving conversation: {e}")

    return show
