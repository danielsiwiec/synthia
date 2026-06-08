import os

import litellm
from loguru import logger

_TITLE_MODEL = os.getenv("LLM_TITLE_MODEL", "anthropic/claude-haiku-4-5")
_TITLE_MAX_LEN = 60

_PROMPT = """Write a short, specific title for this conversation so the user can recognize it in a list of chats.

Rules:
- 3 to 6 words
- no surrounding quotes
- no trailing punctuation
- capture the concrete topic, not generic words like "help" or "question"

User:
{user}

Assistant:
{assistant}

Title:"""


def _clean(title: str) -> str:
    title = title.strip()
    if title:
        title = title.splitlines()[0].strip()
    title = title.strip("\"'").rstrip(".").strip()
    return title[:_TITLE_MAX_LEN]


async def generate_title(user_message: str, assistant_reply: str) -> str | None:
    prompt = _PROMPT.format(user=user_message[:2000], assistant=assistant_reply[:2000])
    try:
        response = await litellm.acompletion(
            model=_TITLE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=24,
            temperature=0.3,
        )
    except Exception as error:
        logger.warning(f"title generation failed: {error}")
        return None
    content = response.choices[0].message.content or ""
    title = _clean(content)
    return title or None
