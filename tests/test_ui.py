import asyncio
import base64
import json
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import Page, expect
from pydantic import BaseModel

_STATIC_DIR = Path(__file__).parent.parent / "synthia" / "static"
_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
_APP_INDEX = _STATIC_DIR / "app" / "index.html"


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


_PORT = _free_port()
_BASE_URL = f"http://localhost:{_PORT}"

_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_PNG_PAYLOAD = {"name": "pixel.png", "mimeType": "image/png", "buffer": _PNG_BYTES}

_threads_store: dict[str, dict] = {}
_messages_store: dict[str, list[dict]] = {}
_sse_queues: dict[str, asyncio.Queue] = {}


def _reset_stores():
    _threads_store.clear()
    _messages_store.clear()
    _sse_queues.clear()


def _stub_app() -> FastAPI:
    app = FastAPI()

    class _Attachment(BaseModel):
        name: str
        content_type: str = ""
        data: str

    class _SendMessageRequest(BaseModel):
        content: str
        reaction: str | None = None
        attachments: list[_Attachment] | None = None

    @app.get("/chat")
    async def chat_ui():
        return FileResponse(_APP_INDEX, headers={"Cache-Control": "no-cache"})

    @app.get("/chat/threads")
    async def list_threads():
        return sorted(_threads_store.values(), key=lambda t: t["updated_at"], reverse=True)

    @app.delete("/chat/threads/{thread_id}")
    async def delete_thread(thread_id: str):
        _threads_store.pop(thread_id, None)
        _messages_store.pop(thread_id, None)
        return {"ok": True}

    @app.get("/chat/threads/{thread_id}/messages")
    async def get_messages(thread_id: str):
        return _messages_store.get(thread_id, [])

    @app.post("/chat/threads/{thread_id}/messages")
    async def send_message(thread_id: str, body: _SendMessageRequest):
        if thread_id not in _threads_store:
            title = body.content[:100] if len(body.content) <= 100 else body.content[:97] + "..."
            _threads_store[thread_id] = {
                "id": thread_id,
                "title": title,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }
        metadata = {"reaction": body.reaction} if body.reaction else None
        attachments = None
        if body.attachments:
            attachments = [
                {
                    "id": f"{thread_id}-{i}",
                    "type": "image" if a.content_type.startswith("image/") else "file",
                    "name": a.name,
                    "content_type": a.content_type,
                    "url": f"data:{a.content_type};base64,{a.data}",
                }
                for i, a in enumerate(body.attachments)
            ]
        msgs = _messages_store.setdefault(thread_id, [])
        msgs.append(
            {
                "id": str(len(msgs) + 1),
                "thread_id": thread_id,
                "role": "user",
                "message_type": "user",
                "content": body.content,
                "metadata": metadata,
                "created_at": "2026-01-01T00:00:00",
                "attachments": attachments,
            }
        )
        queue = _sse_queues.get(thread_id)
        if queue:
            await queue.put({"type": "init"})
            await asyncio.sleep(0.05)
            await queue.put({"type": "progress", "summary": "Thinking..."})
            await asyncio.sleep(0.05)
            thinking_text = f"Pondering: {body.content}"
            await queue.put({"type": "thought", "thinking": thinking_text})
            msgs = _messages_store.setdefault(thread_id, [])
            msgs.append(
                {
                    "id": str(len(msgs) + 1),
                    "thread_id": thread_id,
                    "role": "assistant",
                    "message_type": "thought",
                    "content": thinking_text,
                    "metadata": None,
                    "created_at": "2026-01-01T00:00:01",
                }
            )
            if body.content == "no-result-thought":
                return {"ok": True}
            await asyncio.sleep(0.05)
            await queue.put({"type": "result", "result": f"Echo: {body.content}"})
            msgs = _messages_store.setdefault(thread_id, [])
            msgs.append(
                {
                    "id": str(len(msgs) + 1),
                    "thread_id": thread_id,
                    "role": "assistant",
                    "message_type": "result",
                    "content": f"Echo: {body.content}",
                    "metadata": None,
                    "created_at": "2026-01-01T00:00:02",
                }
            )
        return {"ok": True}

    @app.post("/chat/threads/{thread_id}/stop")
    async def stop_task(thread_id: str):
        return {"ok": True}

    @app.get("/chat/threads/{thread_id}/events")
    async def thread_events(thread_id: str):
        queue: asyncio.Queue = asyncio.Queue()
        _sse_queues[thread_id] = queue

        async def _stream():
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    event_type = event.get("type", "message")
                    data = json.dumps(event)
                    yield f"event: {event_type}\ndata: {data}\n\n"
                except (TimeoutError, asyncio.CancelledError):
                    break

        return StreamingResponse(_stream(), media_type="text/event-stream")

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    return app


class ChatPage:
    def __init__(self, page: Page):
        self._page = page

    def navigate(self):
        self._page.goto(f"{_BASE_URL}/chat")
        self._page.wait_for_load_state("networkidle")

    @property
    def composer(self):
        return self._page.locator(".aui-composer-input")

    @property
    def send_button(self):
        return self._page.locator(".aui-composer-send")

    @property
    def stop_button(self):
        return self._page.locator(".aui-composer-cancel")

    @property
    def new_thread_button(self):
        return self._page.locator(".aui-thread-list-new")

    def send(self, text: str):
        self.composer.fill(text)
        self.composer.press("Enter")

    def attach(self, payload):
        with self._page.expect_file_chooser() as fc:
            self._page.get_by_role("button", name="Add Attachment").dispatch_event("click")
        fc.value.set_files(payload)

    def composer_attachment_tiles(self):
        return self._page.locator(".aui-composer-attachments .aui-attachment-tile")

    def message_attachment_tiles(self):
        return self._page.locator(".aui-user-message-attachments-end .aui-attachment-tile")

    def user_messages(self):
        return self._page.locator(".aui-user-message-content")

    def thread_items(self):
        return self._page.locator(".aui-thread-list-item")

    def thread_item_titles(self):
        return self._page.locator(".aui-thread-list-item-title")

    def open_thread(self, title: str):
        self._page.locator(".aui-thread-list-item-trigger", has_text=title).first.click()

    def text(self, value: str):
        return self._page.get_by_text(value)


_server_thread: threading.Thread | None = None
_server: uvicorn.Server | None = None


@pytest.fixture(scope="session", autouse=True)
def _ensure_frontend_built():
    if not _APP_INDEX.exists():
        try:
            subprocess.run(["npm", "run", "build"], cwd=_FRONTEND_DIR, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            pytest.skip(f"frontend build unavailable: {e}")
    yield


@pytest.fixture(scope="session", autouse=True)
def _start_stub_server(_ensure_frontend_built):
    global _server_thread, _server
    config = uvicorn.Config(_stub_app(), host="127.0.0.1", port=_PORT, log_level="warning")
    _server = uvicorn.Server(config)
    _server_thread = threading.Thread(target=_server.run, daemon=True)
    _server_thread.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", _PORT), timeout=0.5):
                break
        except OSError:
            time.sleep(0.1)
    yield
    _server.should_exit = True


@pytest.fixture(autouse=True)
def _clean_state():
    _reset_stores()
    yield
    _reset_stores()


@pytest.fixture
def chat(page: Page) -> ChatPage:
    cp = ChatPage(page)
    cp.navigate()
    return cp


def test_app_loads(chat: ChatPage):
    expect(chat.composer).to_be_visible()
    expect(chat.new_thread_button).to_be_visible()


def test_collapse_and_expand_sidebar(chat: ChatPage):
    expect(chat.new_thread_button).to_be_visible()
    chat._page.get_by_role("button", name="Collapse sidebar").click()
    expect(chat.new_thread_button).to_have_count(0)
    chat._page.get_by_role("button", name="Expand sidebar").click()
    expect(chat.new_thread_button).to_be_visible()


def test_send_message_shows_user_text(chat: ChatPage):
    chat.send("Hello world")
    expect(chat.user_messages().first).to_contain_text("Hello world")


def test_assistant_response_appears(chat: ChatPage):
    chat.send("ping")
    expect(chat.text("Echo: ping")).to_be_visible(timeout=5000)


def test_composer_clears_after_send(chat: ChatPage):
    chat.send("clear me")
    expect(chat.composer).to_have_value("")


def test_thread_appears_in_list(chat: ChatPage):
    chat.send("My first thread")
    expect(chat.text("Echo: My first thread")).to_be_visible(timeout=5000)
    expect(chat.thread_items()).to_have_count(1, timeout=5000)
    expect(chat.thread_item_titles().first).to_contain_text("My first thread")


def test_delete_thread_via_trash(chat: ChatPage):
    chat.send("delete me")
    expect(chat.text("Echo: delete me")).to_be_visible(timeout=5000)
    expect(chat.thread_items()).to_have_count(1, timeout=5000)
    chat.thread_items().first.hover()
    chat._page.get_by_role("button", name="Delete thread").first.click()
    expect(chat.thread_items()).to_have_count(0, timeout=5000)


def test_multiple_messages_in_thread(chat: ChatPage):
    chat.send("first")
    expect(chat.text("Echo: first")).to_be_visible(timeout=5000)
    chat.send("second")
    expect(chat.text("Echo: second")).to_be_visible(timeout=5000)
    expect(chat.user_messages()).to_have_count(2)


def test_new_thread_button_starts_empty(chat: ChatPage):
    chat.send("seed thread")
    expect(chat.text("Echo: seed thread")).to_be_visible(timeout=5000)
    chat.new_thread_button.click()
    expect(chat.user_messages()).to_have_count(0)
    expect(chat.composer).to_be_visible()


def test_stop_button_visible_while_running(chat: ChatPage):
    chat.send("no-result-thought")
    expect(chat.stop_button).to_be_visible(timeout=5000)


def test_thought_reasoning_visible_while_running(chat: ChatPage):
    chat.send("no-result-thought")
    expect(chat.text("Pondering: no-result-thought")).to_be_visible(timeout=5000)


def test_typing_indicator_visible_while_running(chat: ChatPage):
    chat.send("no-result-thought")
    expect(chat._page.get_by_test_id("typing-indicator")).to_be_visible(timeout=5000)


def test_typing_indicator_hidden_after_response(chat: ChatPage):
    chat.send("ping")
    expect(chat.text("Echo: ping")).to_be_visible(timeout=5000)
    expect(chat._page.get_by_test_id("typing-indicator")).to_have_count(0)


def test_in_progress_clears_after_reopen_when_task_finished_while_away(chat: ChatPage):
    chat.send("no-result-thought")
    expect(chat._page.get_by_test_id("typing-indicator")).to_be_visible(timeout=5000)
    expect(chat.text("Pondering: no-result-thought")).to_be_visible(timeout=5000)

    thread_id = next(iter(_threads_store))
    msgs = _messages_store.setdefault(thread_id, [])
    msgs.append(
        {
            "id": str(len(msgs) + 1),
            "thread_id": thread_id,
            "role": "assistant",
            "message_type": "result",
            "content": "Done while away",
            "metadata": None,
            "created_at": "2026-01-01T00:00:05",
        }
    )

    chat._page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")

    expect(chat._page.get_by_test_id("typing-indicator")).to_have_count(0, timeout=5000)
    expect(chat.text("Done while away")).to_be_visible(timeout=5000)


def test_no_assistant_action_bar(chat: ChatPage):
    chat.send("ping")
    expect(chat.text("Echo: ping")).to_be_visible(timeout=5000)
    expect(chat._page.locator(".aui-assistant-action-bar-root")).to_have_count(0)


def test_switch_between_threads(chat: ChatPage):
    _threads_store["aaa"] = {
        "id": "aaa",
        "title": "Thread A",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }
    _messages_store["aaa"] = [
        {
            "id": "1",
            "thread_id": "aaa",
            "role": "user",
            "message_type": "user",
            "content": "alpha message",
            "metadata": None,
            "created_at": "2026-01-01T00:00:00",
        }
    ]
    _threads_store["bbb"] = {
        "id": "bbb",
        "title": "Thread B",
        "created_at": "2026-06-01T00:00:00",
        "updated_at": "2026-06-01T00:00:00",
    }
    _messages_store["bbb"] = [
        {
            "id": "2",
            "thread_id": "bbb",
            "role": "user",
            "message_type": "user",
            "content": "bravo message",
            "metadata": None,
            "created_at": "2026-06-01T00:00:00",
        }
    ]
    chat.navigate()
    expect(chat.thread_items()).to_have_count(2)
    chat.open_thread("Thread A")
    expect(chat.text("alpha message")).to_be_visible()
    chat.open_thread("Thread B")
    expect(chat.text("bravo message")).to_be_visible()


def test_assistant_message_renders_markdown(chat: ChatPage):
    _threads_store["md"] = {
        "id": "md",
        "title": "Markdown test",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }
    _messages_store["md"] = [
        {
            "id": "1",
            "thread_id": "md",
            "role": "assistant",
            "message_type": "result",
            "content": "Here is **bold** and `code`",
            "metadata": None,
            "created_at": "2026-01-01T00:00:00",
        }
    ]
    chat.navigate()
    chat.open_thread("Markdown test")
    expect(chat._page.locator("strong", has_text="bold")).to_be_visible()
    expect(chat._page.locator("code", has_text="code")).to_be_visible()


def test_xss_in_user_message_not_executed(chat: ChatPage):
    chat.send("<script>alert('xss')</script>")
    expect(chat.user_messages().first).to_contain_text("<script>alert('xss')</script>")
    expect(chat._page.locator("script:has-text(\"alert('xss')\")")).to_have_count(0)


def test_attachment_tile_appears_in_composer(chat: ChatPage):
    chat.attach(_PNG_PAYLOAD)
    expect(chat.composer_attachment_tiles().first).to_be_visible(timeout=5000)


def test_attachment_can_be_removed(chat: ChatPage):
    chat.attach(_PNG_PAYLOAD)
    expect(chat.composer_attachment_tiles().first).to_be_visible(timeout=5000)
    chat.composer_attachment_tiles().first.hover()
    chat._page.get_by_role("button", name="Remove file").first.dispatch_event("click")
    expect(chat.composer_attachment_tiles()).to_have_count(0)


def test_send_with_attachment_shows_on_message(chat: ChatPage):
    chat.attach(_PNG_PAYLOAD)
    expect(chat.composer_attachment_tiles().first).to_be_visible(timeout=5000)
    chat.send("look at this")
    expect(chat.text("Echo: look at this")).to_be_visible(timeout=5000)
    expect(chat.message_attachment_tiles().first).to_be_visible()


def test_attachment_persists_after_thread_switch(chat: ChatPage):
    chat.attach(_PNG_PAYLOAD)
    expect(chat.composer_attachment_tiles().first).to_be_visible(timeout=5000)
    chat.send("with photo")
    expect(chat.text("Echo: with photo")).to_be_visible(timeout=5000)
    expect(chat.message_attachment_tiles().first).to_be_visible()

    chat.new_thread_button.click()
    expect(chat.user_messages()).to_have_count(0)

    chat.open_thread("with photo")
    expect(chat.text("Echo: with photo")).to_be_visible(timeout=5000)
    expect(chat.message_attachment_tiles().first).to_be_visible()

