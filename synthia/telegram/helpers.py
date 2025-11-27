import re
from collections.abc import Callable, Coroutine

import bleach
import markdown

MAX_MESSAGE_LENGTH = 4096

_TELEGRAM_ALLOWED_TAGS = [
    "b",
    "strong",
    "i",
    "em",
    "u",
    "s",
    "strike",
    "del",
    "code",
    "pre",
    "a",
    "tg-spoiler",
    "blockquote",
]

_TELEGRAM_ALLOWED_ATTRIBUTES = {
    "a": ["href"],
    "code": ["class"],
}


def _sanitize_html_for_telegram(html: str) -> str:
    html = re.sub(r"<h[1-6]>(.*?)</h[1-6]>", r"<b>\1</b>\n", html)

    while re.search(r"<ul>\s*<li>", html):
        html = re.sub(r"<ul>\s*", "", html)
        html = re.sub(r"</ul>", "", html)

    while re.search(r"<li>", html):
        html = re.sub(r"<li>(.*?)</li>", r"\n• \1", html)

    html = re.sub(r"</?(ul|ol|p)>", "\n", html)

    html = bleach.clean(html, tags=_TELEGRAM_ALLOWED_TAGS, attributes=_TELEGRAM_ALLOWED_ATTRIBUTES, strip=True)

    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


async def send_message(message_sender: Callable[[str], Coroutine], text: str):
    html = markdown.markdown(text)
    text = _sanitize_html_for_telegram(html)

    if len(text) <= MAX_MESSAGE_LENGTH:
        await message_sender(text)
        return

    chunks = []
    while text:
        if len(text) <= MAX_MESSAGE_LENGTH:
            chunks.append(text)
            break

        split_pos = text.rfind("\n", 0, MAX_MESSAGE_LENGTH)
        if split_pos == -1:
            split_pos = MAX_MESSAGE_LENGTH

        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()

    for i, chunk in enumerate(chunks):
        await message_sender(f"[Part {i + 1}/{len(chunks)}]\n\n{chunk}")
