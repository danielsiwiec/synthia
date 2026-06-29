from collections.abc import Callable
from pathlib import Path

import asyncpg

from synthia.agents.episodic.attachments import attachments_for_thread, render_attachments_block
from synthia.agents.tools import error_response, success_response


def create_show_tool(pool: asyncpg.Pool, cwd: str | Path | None = None) -> Callable:
    async def episodic_show(conversation_id: str) -> str:
        """Retrieve the full transcript of a specific Synthia conversation by ID, including the paths
        of any files (images, documents) that were attached in that conversation.

        Args:
            conversation_id: The UUID of the conversation to retrieve.
        """
        try:
            async with pool.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT id, transcript, summary, created_at, thread_id
                    FROM conversations
                    WHERE id = $1::uuid
                    """,
                    conversation_id,
                )

                if not result:
                    return success_response(f"No conversation found with ID: {conversation_id}")

            attachments_block = ""
            if result["thread_id"] is not None:
                attachments = await attachments_for_thread(pool, cwd, result["thread_id"])
                attachments_block = render_attachments_block(attachments)

            return success_response(f"""**Conversation {result["id"]}**
- Date: {result["created_at"].strftime("%Y-%m-%d %H:%M")}

**Summary:**
{result["summary"]}

**Full Transcript:**
{result["transcript"]}
{attachments_block}""")
        except Exception as e:
            return error_response(f"Error retrieving conversation: {e}")

    return episodic_show
