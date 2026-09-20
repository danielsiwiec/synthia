import asyncio
import os
import uuid
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from synthia.agents.browser.jev import JevClient, JevUsage, jev_available
from synthia.agents.browser.loop import MAX_STEPS, TIMEOUT_S, BrowseResult, check, run_goal
from synthia.agents.browser.page import BrowserUnavailable, HostBrowser, Tab, dumps
from synthia.helpers.pubsub import pubsub
from synthia.service.models import OutgoingImage, ProgressNotification

_MAX_CONCURRENT = int(os.getenv("BROWSER_MAX_CONCURRENT", "2"))
_EVAL_MAX_CHARS = 20_000
_PROGRESS_EVERY = 3
_SCROLL = {"scroll_down": 1, "scroll_up": -1}


class BrowserService:
    def __init__(self, cdp_http: str | None = None, cwd: str | Path | None = None):
        self._host = HostBrowser(cdp_http)
        self._jev = JevClient() if jev_available() else None
        self._tabs: dict[int, Tab] = {}
        self._loops = asyncio.Semaphore(_MAX_CONCURRENT)
        self._cwd = Path(cwd) if cwd else Path.cwd()

    @property
    def jev(self) -> JevClient | None:
        return self._jev

    @property
    def endpoint(self) -> str:
        return self._host.endpoint

    def tab(self, thread_id: int) -> Tab:
        tab = self._tabs.get(thread_id)
        if tab is None:
            tab = self._tabs[thread_id] = Tab(self._host)
        return tab

    async def pages(self) -> list:
        return await self._host.pages()

    async def browse(
        self,
        goal: str,
        url: str = "",
        values: dict[str, str] | None = None,
        max_steps: int = MAX_STEPS,
        allow_irreversible: bool = False,
        tab: Tab | None = None,
        progress: Callable | None = None,
        timeout_s: float = TIMEOUT_S,
    ) -> BrowseResult:
        if self._jev is None:
            return BrowseResult(status="error", reason="browser decision model unavailable (TYPESAFE_API_KEY not set)")
        own = tab is None
        tab = tab or Tab(self._host)
        async with self._loops:
            try:
                if url:
                    await tab.open(url)
                return await run_goal(
                    tab,
                    self._jev,
                    goal,
                    values,
                    max_steps=max_steps,
                    timeout_s=timeout_s,
                    allow_irreversible=allow_irreversible,
                    on_step=progress,
                )
            except BrowserUnavailable as error:
                return BrowseResult(status="error", reason=str(error))
            except Exception as error:
                logger.warning(f"browser loop failed: {error}")
                return BrowseResult(status="error", reason=f"{type(error).__name__}: {str(error)[:300]}")
            finally:
                if own:
                    await tab.close()

    def screenshot_path(self) -> Path:
        return self._cwd / f".browser_{uuid.uuid4().hex}.png"

    async def close(self) -> None:
        for tab in list(self._tabs.values()):
            await tab.close()
        self._tabs.clear()
        if self._jev is not None:
            await self._jev.close()
        await self._host.close()


def _progress(thread_id: int, session_id: str | None) -> Callable:
    async def on_step(step: int, entry: str) -> None:
        if step % _PROGRESS_EVERY == 0 and session_id:
            await pubsub.publish(
                ProgressNotification(session_id=session_id, thread_id=thread_id, summary=f"Browsing: {entry[:120]}")
            )

    return on_step


def create_browser_tools(service: BrowserService, thread_id: int, show_images: bool = True) -> list[Callable]:
    tab = service.tab(thread_id)

    async def _guarded(action: Callable) -> str:
        try:
            return await action()
        except BrowserUnavailable as error:
            return f"Error: {error}"
        except Exception as error:
            return f"Error: {type(error).__name__}: {str(error)[:300]}"

    async def browser_open(url: str) -> str:
        """Open a URL in this conversation's browser tab (the real host Chrome, which passes
        Cloudflare and keeps logins) and return what is on the page: title, visible text
        excerpt, and numbered interactive elements (#ref) you can act on with browser_act. If the
        URL triggers a file download, returns "download started" (the file lands in /mounts/downloads).

        Args:
            url: The fully-qualified URL to open.
        """

        async def go() -> str:
            outcome = await tab.open(url)
            if outcome == "download started":
                return "download started (check /mounts/downloads)"
            return (await tab.observe()).render()

        return await _guarded(go)

    async def browser_observe() -> str:
        """Re-read the current page: url, title, alerts/dialogs, scroll position, visible text
        excerpt, and the numbered interactive elements (#ref). Refs are reassigned on every
        observation and go stale when the page changes, so observe again after any action."""

        return await _guarded(lambda: _render(tab))

    async def browser_act(action: str, ref: int = 0, value: str = "") -> str:
        """Perform one browser action and return the fresh page observation.

        Args:
            action: One of click, type, select, press, scroll_down, scroll_up, back.
                click/type/select need a ref from the latest observation; type fills the field
                with value and presses Enter; select picks the option whose label (or value)
                equals value; press sends a keyboard key named in value (e.g. "Enter", "Escape").
            ref: Element number (#ref) from the latest observation, for click/type/select/press.
            value: Text to type, option to select, or key to press.
        """

        async def act() -> str:
            if action == "click":
                outcome = await tab.click(ref)
            elif action == "type":
                outcome = await tab.type(ref, value, submit=True)
            elif action == "select":
                outcome = await tab.select(ref, value)
            elif action == "press":
                outcome = await tab.press(value or "Enter", ref or None)
            elif action in _SCROLL:
                outcome = await tab.scroll(_SCROLL[action])
            elif action == "back":
                outcome = await tab.back()
            else:
                return (
                    f"Error: unknown action {action!r}; use click, type, select, press, scroll_down, scroll_up, or back"
                )
            if outcome == "download started":
                return "download started (check /mounts/downloads)"
            return f"{outcome}\n\n{(await tab.observe()).render()}"

        return await _guarded(act)

    async def browser_eval(script: str) -> str:
        """Run JavaScript in the current page and return its JSON result. Use for deterministic
        extraction: hrefs, lists of titles, counts, attribute values. Example:
        "Array.from(document.querySelectorAll('article h2 a')).map(a => [a.textContent.trim(), a.href])".

        Args:
            script: A JavaScript expression evaluated in the page; its return value is serialized as JSON.
        """

        async def run() -> str:
            text = dumps(await tab.evaluate(script))
            return text if len(text) <= _EVAL_MAX_CHARS else text[:_EVAL_MAX_CHARS] + "\n... [truncated]"

        return await _guarded(run)

    async def browser_wait(text: str = "", selector: str = "", condition: str = "", seconds: float = 10) -> str:
        """Wait until visible text appears, a CSS selector is visible, or a JavaScript condition
        becomes true, up to `seconds`. With no criteria it simply waits `seconds`. Use it after
        opening Cloudflare-protected or slow pages instead of blind sleeps.

        Args:
            text: Visible text to wait for (substring match).
            selector: CSS selector that must become visible.
            condition: JavaScript expression that must evaluate to true, e.g.
                "document.querySelectorAll('article').length > 0".
            seconds: Maximum seconds to wait.
        """

        return await _guarded(lambda: tab.wait_for(text, selector, condition, seconds))

    async def browser_tabs(select: int = -1) -> str:
        """List the browser's open tabs (index, title, url), or adopt one as this conversation's
        tab by index — useful when a click opened a popup or a new tab.

        Args:
            select: Index of the tab to switch to; leave at -1 to only list.
        """

        async def tabs() -> str:
            pages = await service.pages()
            if 0 <= select < len(pages):
                tab.adopt(pages[select])
                return f"switched to tab {select}\n\n{(await tab.observe()).render()}"
            lines = []
            for i, page in enumerate(pages):
                marker = " (current)" if page is tab.page else ""
                try:
                    title = await page.title()
                except Exception:
                    title = ""
                lines.append(f"{i}: {title[:60]!r} {page.url[:100]}{marker}")
            return "\n".join(lines) or "no open tabs"

        return await _guarded(tabs)

    async def browser_screenshot(caption: str = "", full_page: bool = False) -> str:
        """Take a screenshot of the current page and show it to the user in the chat.

        Args:
            caption: Optional caption shown under the image.
            full_page: Capture the whole scrollable page instead of the viewport.
        """

        async def shot() -> str:
            path = await tab.screenshot(service.screenshot_path(), full_page)
            if show_images:
                await pubsub.publish(
                    OutgoingImage(
                        thread_id=thread_id,
                        source_path=str(path),
                        name=path.name,
                        content_type="image/png",
                        caption=caption,
                    )
                )
                return f"Screenshot shown to the user ({path})."
            return f"Screenshot saved to {path}."

        return await _guarded(shot)

    async def browser_close() -> str:
        """Close this conversation's browser tab (never the browser itself). Call it when you are
        done browsing so the host Chrome does not accumulate tabs."""

        await tab.close()
        return "tab closed"

    async def browser_do(
        goal: str,
        values: dict[str, str] | None = None,
        max_steps: int = MAX_STEPS,
        timeout_s: float = TIMEOUT_S,
        allow_irreversible: bool = False,
    ) -> str:
        """Let the fast browser decision model pursue a whole goal on the current tab, step by step
        (observe, pick an element and action, act, verify), and return a structured result. It is
        the preferred way to navigate: give it the complete outcome you want (e.g. "start
        downloading the PDF of this magazine issue", "reach the newest issue page", "dismiss any
        gate and reveal the download link") rather than one click at a time. It follows tabs that
        open along the way and stops as soon as a file download begins ("a file download was
        started"). It waits adaptively for loading, challenges, or file preparation. It never
        invents text: anything to type must be given in values keyed by a short name (e.g.
        {"query": "Wired USA"}); if it needs a value you did not give, the status is needs_input.
        Statuses: done, needs_input, needs_confirmation (an irreversible step is next; rerun with
        allow_irreversible=true if intended), blocked (the page itself says it cannot be done, e.g.
        an expired link or login wall; the reason quotes it), stuck, max_steps, timeout, error. On stuck, read
        the steps it reports, then observe the page yourself and continue with browser_act, or
        call it again with a more specific goal.

        Args:
            goal: The complete outcome wanted on this site, in plain words.
            values: Named strings the model may type or select, keyed by short names.
            max_steps: Upper bound on actions.
            timeout_s: Wall-clock budget in seconds; raise it for flows that wait on file preparation.
            allow_irreversible: Permit steps like submitting payments, sending, or deleting.
        """

        async def do() -> str:
            result = await service.browse(
                goal,
                "",
                values,
                max_steps=max_steps,
                timeout_s=timeout_s,
                allow_irreversible=allow_irreversible,
                tab=tab,
                progress=_progress(thread_id, None),
            )
            _record_cost(result.cost_usd)
            return result.render()

        return await _guarded(do)

    async def browser_check(question: str) -> str:
        """Ask the fast browser decision model a yes/no question about the current page's visible
        text and get the probability of "yes" (0..1). Cheap and instant; good for "is the
        download finished?", "is this a login page?", "does the page show an error?".

        Args:
            question: A yes/no question about the current page.
        """

        async def ask() -> str:
            assert service.jev is not None
            probability, usage = await check(tab, service.jev, question)
            _record_cost(usage.cost_usd)
            return f"p(yes) = {probability:.2f}"

        return await _guarded(ask)

    tools: list[Callable] = [
        browser_open,
        browser_observe,
        browser_act,
        browser_eval,
        browser_wait,
        browser_tabs,
        browser_screenshot,
        browser_close,
    ]
    if service.jev is not None:
        tools += [browser_do, browser_check]
    return tools


async def _render(tab: Tab) -> str:
    return (await tab.observe()).render()


def _record_cost(cost: float) -> None:
    from synthia.agents.agent import record_delegated_cost

    record_delegated_cost(cost)


def usage_line(usage: JevUsage) -> str:
    return f"{usage.calls} jev calls, {usage.input_tokens} tokens, ${usage.cost_usd:.5f}"
