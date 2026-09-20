import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright.async_api import Error as PlaywrightError

from synthia.agents.browser.actions import Observation

DEFAULT_CDP_HTTP = "http://192.168.65.254:9222"
_OBSERVE_JS = (Path(__file__).parent / "observe.js").read_text()
_NAV_TIMEOUT_MS = 30_000
_ACTION_TIMEOUT_MS = 8_000
_SETTLE_MS = 800
_SCROLL_FRACTION = 0.8
_DOWNLOAD_ERROR = re.compile(r"Download is starting", re.I)
_CLEAR_OBSTRUCTION_JS = """el => {
  el.scrollIntoView({block: 'center', inline: 'center'});
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  const cleared = [];
  for (let i = 0; i < 6; i++) {
    const top = document.elementFromPoint(x, y);
    if (!top || top === el || el.contains(top) || top.contains(el)) break;
    let block = top;
    while (block.parentElement && block.parentElement !== document.body && !block.parentElement.contains(el)) {
      block = block.parentElement;
    }
    block.style.setProperty('pointer-events', 'none', 'important');
    const cls = typeof block.className === 'string' ? block.className.trim().split(/\\s+/)[0] : '';
    cleared.push(block.tagName.toLowerCase() + (block.id ? '#' + block.id : '') + (cls ? '.' + cls : ''));
  }
  return cleared;
}"""


def cdp_endpoint() -> str:
    return os.getenv("BROWSER_CDP_HTTP") or os.getenv("ABR_CDP_HTTP") or DEFAULT_CDP_HTTP


class BrowserUnavailable(Exception):
    pass


class HostBrowser:
    def __init__(self, cdp_http: str | None = None):
        self._cdp_http = cdp_http or cdp_endpoint()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    @property
    def endpoint(self) -> str:
        return self._cdp_http

    async def context(self) -> BrowserContext:
        async with self._lock:
            if self._browser is not None and self._browser.is_connected():
                return self._browser.contexts[0]
            last: Exception | None = None
            for attempt in range(2):
                try:
                    if self._playwright is None:
                        self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.connect_over_cdp(self._cdp_http, timeout=20_000)
                    await self._keep_host_downloads(self._browser)
                    logger.info(f"🌐 attached to host Chrome at {self._cdp_http}")
                    return self._browser.contexts[0]
                except Exception as error:
                    last = error
                    if attempt == 0:
                        logger.warning(f"browser attach failed, restarting driver: {_short(error)}")
                        await self._reset()
            raise BrowserUnavailable(f"host Chrome unreachable at {self._cdp_http}: {last}") from last

    async def _keep_host_downloads(self, browser: Browser) -> None:
        session = await browser.new_browser_cdp_session()
        try:
            await session.send("Browser.setDownloadBehavior", {"behavior": "default", "eventsEnabled": True})
        finally:
            await session.detach()

    async def _reset(self) -> None:
        self._browser = None
        playwright, self._playwright = self._playwright, None
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass

    async def new_page(self) -> Page:
        page = await (await self.context()).new_page()
        page.set_default_timeout(_ACTION_TIMEOUT_MS)
        page.set_default_navigation_timeout(_NAV_TIMEOUT_MS)
        return page

    async def pages(self) -> list[Page]:
        return list((await self.context()).pages)

    async def close(self) -> None:
        async with self._lock:
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None


class Tab:
    def __init__(self, host: HostBrowser):
        self._host = host
        self._page: Page | None = None
        self._downloads: list[str] = []
        self._dialogs: list[str] = []
        self._watched: set[int] = set()

    @property
    def page(self) -> Page | None:
        return self._page if self._page is not None and not self._page.is_closed() else None

    async def ensure(self) -> Page:
        page = self.page
        if page is None:
            page = await self._host.new_page()
            self.adopt(page)
        return page

    def adopt(self, page: Page) -> None:
        self._page = page
        page.set_default_timeout(_ACTION_TIMEOUT_MS)
        page.set_default_navigation_timeout(_NAV_TIMEOUT_MS)
        if id(page) not in self._watched:
            self._watched.add(id(page))
            page.on("download", lambda download: self._downloads.append(download.suggested_filename))
            page.on("dialog", self._on_dialog)

    async def _on_dialog(self, dialog: Any) -> None:
        self._dialogs.append(f"{dialog.type}: {dialog.message[:120]}")
        try:
            if dialog.type == "beforeunload":
                await dialog.accept()
            else:
                await dialog.dismiss()
        except Exception:
            pass

    def take_download(self) -> str | None:
        if not self._downloads:
            return None
        name = self._downloads[-1]
        self._downloads.clear()
        return name

    async def _siblings(self) -> list[Page]:
        return await self._host.pages()

    async def _adopt_new(self, before: list[Page]) -> str | None:
        known = {id(p) for p in before}
        opened = [p for p in await self._siblings() if id(p) not in known and not p.is_closed()]
        if not opened:
            return None
        page = opened[-1]
        self.adopt(page)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=_NAV_TIMEOUT_MS)
        except PlaywrightError:
            pass
        await self.settle()
        return f"opened new tab {page.url}"

    async def _outcome(self, before: list[Page], default: str) -> str:
        if self.take_download():
            return "download started"
        adopted = await self._adopt_new(before)
        if self.take_download():
            return "download started"
        outcome = adopted or default
        if self._dialogs:
            outcome += " (dialog dismissed: " + "; ".join(self._dialogs) + ")"
            self._dialogs.clear()
        return outcome

    async def close(self) -> None:
        page = self.page
        self._page = None
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass

    async def open(self, url: str) -> str:
        page = await self.ensure()
        try:
            await page.goto(url, wait_until="domcontentloaded")
        except PlaywrightError as error:
            if _DOWNLOAD_ERROR.search(str(error)):
                return "download started"
            raise
        await self.settle()
        return "download started" if self.take_download() else "opened"

    async def settle(self, timeout_ms: int = _SETTLE_MS) -> None:
        page = await self.ensure()
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except PlaywrightError:
            pass
        await asyncio.sleep(timeout_ms / 1000 / 2)

    async def observe(self) -> Observation:
        page = await self.ensure()
        raw = await page.evaluate(_OBSERVE_JS)
        return Observation.from_raw(raw)

    async def evaluate(self, script: str) -> Any:
        page = await self.ensure()
        return await page.evaluate(script)

    def _locator(self, ref: int):
        assert self._page is not None
        return self._page.locator(f'[data-synthia-ref="{ref}"]').first

    async def click(self, ref: int) -> str:
        page = await self.ensure()
        before = await self._siblings()
        url_before = page.url
        locator = self._locator(ref)
        href = await self._link_target(locator)
        cleared = ""
        try:
            await locator.scroll_into_view_if_needed(timeout=_ACTION_TIMEOUT_MS)
            await locator.click(timeout=_ACTION_TIMEOUT_MS)
        except PlaywrightError as error:
            if _DOWNLOAD_ERROR.search(str(error)):
                return "download started"
            cleared = await self._clear_obstruction(locator)
            try:
                await locator.click(timeout=_ACTION_TIMEOUT_MS)
            except PlaywrightError as retry:
                if _DOWNLOAD_ERROR.search(str(retry)):
                    return "download started"
                try:
                    await locator.evaluate("el => el.click()")
                except PlaywrightError as scripted:
                    return f"click failed: {_short(scripted)}"
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=_SETTLE_MS * 2)
        except PlaywrightError:
            pass
        await self.settle()
        outcome = await self._outcome(before, "clicked")
        if cleared and outcome == "clicked":
            outcome = f"clicked (after clearing an overlay: {cleared})"
        if outcome == "clicked" and href and self.page is page and page.url == url_before:
            followed = await self.open(href)
            return (
                "download started"
                if followed == "download started"
                else "clicked (link did not navigate; opened its target directly)"
            )
        return outcome

    async def _clear_obstruction(self, locator: Any) -> str:
        try:
            cleared = await locator.evaluate(_CLEAR_OBSTRUCTION_JS, timeout=_ACTION_TIMEOUT_MS)
        except PlaywrightError:
            return ""
        return ", ".join(str(c) for c in (cleared or []))[:120]

    async def _link_target(self, locator: Any) -> str:
        try:
            href = await locator.evaluate("el => (el.closest('a[href]') || {}).href || ''", timeout=_ACTION_TIMEOUT_MS)
        except PlaywrightError:
            return ""
        href = str(href or "")
        if not href.startswith(("http://", "https://")) or href.split("#", 1)[0] == (
            self.page.url.split("#", 1)[0] if self.page else ""
        ):
            return ""
        return href

    async def type(self, ref: int, value: str, submit: bool = False) -> str:
        await self.ensure()
        before = await self._siblings()
        locator = self._locator(ref)
        try:
            await locator.fill(value, timeout=_ACTION_TIMEOUT_MS)
            if submit:
                await locator.press("Enter")
        except PlaywrightError as error:
            return f"type failed: {_short(error)}"
        await self.settle()
        return await self._outcome(before, "typed")

    async def select(self, ref: int, value: str) -> str:
        await self.ensure()
        locator = self._locator(ref)
        try:
            await locator.select_option(label=value, timeout=_ACTION_TIMEOUT_MS)
        except PlaywrightError:
            try:
                await locator.select_option(value=value, timeout=_ACTION_TIMEOUT_MS)
            except PlaywrightError as error:
                return f"select failed: {_short(error)}"
        await self.settle()
        return "selected"

    async def press(self, key: str, ref: int | None = None) -> str:
        page = await self.ensure()
        before = await self._siblings()
        try:
            if ref is not None:
                await self._locator(ref).press(key)
            else:
                await page.keyboard.press(key)
        except PlaywrightError as error:
            return f"press failed: {_short(error)}"
        await self.settle()
        return await self._outcome(before, "pressed")

    async def scroll(self, direction: int) -> str:
        page = await self.ensure()
        await page.evaluate(f"window.scrollBy(0, {direction} * window.innerHeight * {_SCROLL_FRACTION})")
        await asyncio.sleep(0.3)
        return "scrolled"

    async def back(self) -> str:
        page = await self.ensure()
        try:
            await page.go_back(wait_until="domcontentloaded")
        except PlaywrightError as error:
            return f"back failed: {_short(error)}"
        await self.settle()
        return "went back"

    async def sleep(self, seconds: float) -> str:
        deadline = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < deadline:
            if self.take_download():
                return "download started"
            await asyncio.sleep(min(0.5, max(deadline - asyncio.get_event_loop().time(), 0)))
        await self.settle()
        return "download started" if self.take_download() else "waited"

    async def wait_for(self, text: str = "", selector: str = "", condition: str = "", timeout_s: float = 10) -> str:
        page = await self.ensure()
        timeout_ms = int(timeout_s * 1000)
        try:
            if text:
                await page.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=timeout_ms)
                return f"text {text!r} is visible"
            if selector:
                await page.locator(selector).first.wait_for(state="visible", timeout=timeout_ms)
                return f"selector {selector!r} is visible"
            if condition:
                await page.wait_for_function(condition, timeout=timeout_ms)
                return "condition is true"
            await asyncio.sleep(timeout_s)
            return f"waited {timeout_s}s"
        except PlaywrightError as error:
            return f"wait timed out after {timeout_s}s: {_short(error)}"

    async def screenshot(self, path: Path, full_page: bool = False) -> Path:
        page = await self.ensure()
        path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(path), full_page=full_page)
        return path


def _short(error: BaseException) -> str:
    return str(error).splitlines()[0][:200]


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)
