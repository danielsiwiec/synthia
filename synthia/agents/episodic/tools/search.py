import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import asyncpg

from synthia.agents.episodic.db import generate_embedding
from synthia.agents.tools import error_response, success_response


def create_search_tool(pool: asyncpg.Pool) -> Callable:
    async def episodic_search(query: str, days: int = 30) -> str:
        """Search past Synthia conversations by semantic similarity and keyword matching. Use this to
        find relevant context from previous sessions.

        Args:
            query: The search query (keywords or natural language description).
            days: Number of days to search back (default: 30).
        """
        try:
            query_embedding = generate_embedding(query)
            date_threshold = datetime.now(tz=UTC) - timedelta(days=days)

            async with pool.acquire() as conn:
                results = await conn.fetch(
                    """
                    SELECT
                        id,
                        summary,
                        created_at,
                        1 - (embedding <=> $1::vector) as similarity,
                        ts_rank(to_tsvector('english', summary || ' ' || transcript),
                                plainto_tsquery('english', $2)) as keyword_rank
                    FROM conversations
                    WHERE created_at >= $3
                    ORDER BY
                        (1 - (embedding <=> $1::vector)) * 0.7 +
                        COALESCE(ts_rank(to_tsvector('english', summary || ' ' || transcript),
                                 plainto_tsquery('english', $2)), 0) * 0.3 DESC
                    LIMIT 5
                    """,
                    json.dumps(query_embedding),
                    query,
                    date_threshold,
                )

                if not results:
                    return success_response("No matching conversations found.")

                output = []
                for i, row in enumerate(results, 1):
                    summary = row["summary"]
                    output.append(f"""
**Result {i}**
- ID: `{row["id"]}`
- Date: {row["created_at"].strftime("%Y-%m-%d %H:%M")}
- Similarity: {row["similarity"]:.2%}
- Summary: {summary[:500]}{"..." if len(summary) > 500 else ""}
""")

                return success_response("\n".join(output))
        except Exception as e:
            return error_response(f"Error searching conversations: {e}")

    return episodic_search
