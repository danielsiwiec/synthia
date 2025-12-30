#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.request


def publish(content: str, title: str = "Document") -> str:
    url = "https://markdownpaste-api.onrender.com/api/documents"

    if not content or not content.strip():
        raise ValueError("Content cannot be empty")

    content = content.strip()

    payload = {
        "title": title,
        "content": content,
        "visibility": "public",
        "password": "",
        "editKey": "",
        "expiresAt": "",
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        raise ValueError(f"API request failed with status {e.code}: {error_body}") from e

    slug = response_data.get("data", {}).get("slug")

    if not slug:
        raise ValueError(f"Failed to get slug from response: {response_data}")

    return f"https://www.markdownpaste.com/document/{slug}"


if __name__ == "__main__":
    if not sys.stdin.isatty():
        content = sys.stdin.read()
        title = sys.argv[1] if len(sys.argv) > 1 else "Document"
    else:
        if len(sys.argv) < 2:
            usage = "Usage: echo <content> | python publish.py [title]"
            print(usage, file=sys.stderr)
            sys.exit(1)
        content = sys.argv[1]
        title = sys.argv[2] if len(sys.argv) > 2 else "Document"

    try:
        link = publish(content, title)
        print(link)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
