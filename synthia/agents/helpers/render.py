from typing import Any


def _get_message_emoji(message_type: str) -> str:
    emoji_map = {
        "ResultMessage": "✅",
        "UserMessage": "👤",
        "AssistantMessage": "🤖",
        "SystemMessage": "⚙️",
    }
    return emoji_map.get(message_type, "📨")


def _parse_content_blocks(content_blocks) -> str:
    if not content_blocks:
        return ""

    parsed_blocks = []
    for block in content_blocks:
        block_type = type(block).__name__

        if block_type == "ToolUseBlock":
            tool_name = getattr(block, "name", "unknown_tool")
            tool_input = getattr(block, "input", "")
            parsed_blocks.append(f"🔧 {tool_name}: {tool_input}")

        elif block_type == "ToolResultBlock":
            content = getattr(block, "content", "")
            if len(content) > 200:
                content = content[:200] + "..."
            parsed_blocks.append(f"📋 {content}")

        elif block_type == "TextBlock":
            text = getattr(block, "text", "")
            if len(text) > 200:
                text = text[:200] + "..."
            parsed_blocks.append(text)

        else:
            parsed_blocks.append(str(block))

    return " | ".join(parsed_blocks)


def _parse_message_content(message: Any) -> str:
    message_type = type(message).__name__

    if message_type == "SystemMessage" and hasattr(message, "subtype") and message.subtype == "init":
        return "starting agent..."

    if hasattr(message, "content") and message.content:
        if isinstance(message.content, list):
            return _parse_content_blocks(message.content)
        else:
            content = str(message.content)
            if len(content) > 200:
                content = content[:200] + "..."
            return content

    if hasattr(message, "result") and message.result:
        content = str(message.result)
    elif hasattr(message, "message") and message.message:
        content = str(message.message)
    else:
        content = str(message)

    if len(content) > 200:
        content = content[:200] + "..."

    return content


def render_message(message: Any) -> str:
    message_type = type(message).__name__
    emoji = _get_message_emoji(message_type)
    content = _parse_message_content(message)

    return f"{emoji} [{message_type}] {content}"
