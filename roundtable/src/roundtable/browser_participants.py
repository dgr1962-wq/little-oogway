from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BrowserSite:
    service: str
    url: str
    host_fragment: str
    prompt_selectors: tuple[str, ...]
    response_selectors: tuple[str, ...]
    stop_selectors: tuple[str, ...]
    login_gate_text: tuple[str, ...] = ()


CHATGPT = BrowserSite(
    service="chatgpt",
    url="https://chatgpt.com/",
    host_fragment="chatgpt.com",
    prompt_selectors=(
        '[contenteditable="true"][role="textbox"][aria-label*="ChatGPT"]',
        '#prompt-textarea',
        'textarea[placeholder*="Message"]',
    ),
    response_selectors=(
        '[data-dil-message-id]',
        '[data-message-author-role="assistant"]',
        'article[data-turn="assistant"]',
    ),
    stop_selectors=(
        'button[data-testid="stop-button"]',
        'button[aria-label*="Stop"]',
    ),
    login_gate_text=("Log in to use",),
)


CLAUDE = BrowserSite(
    service="claude",
    url="https://claude.ai/new",
    host_fragment="claude.ai",
    prompt_selectors=(
        '.ProseMirror[contenteditable="true"]',
        '[contenteditable="true"][role="textbox"]',
        'textarea[placeholder*="Claude"]',
    ),
    response_selectors=(
        '[data-testid="assistant-message"] .prose',
        '[data-is-streaming] .font-claude-response',
        '.font-claude-response',
        '[data-testid="assistant-message"]',
    ),
    stop_selectors=(
        'button[aria-label*="Stop"]',
        'button[data-testid*="stop"]',
    ),
    login_gate_text=("Log in", "Sign in"),
)


@dataclass
class VisibleBrowserParticipant:
    """A visible, persistent browser participant controlled through local CDP.

    Chrome owns the profile and window. Playwright attaches only for the duration
    of a response, so closing an adapter cannot erase or replace login state.
    """

    name: str
    site: BrowserSite
    profile_directory: Path
    debug_port: int
    chrome_path: str = "/opt/google/chrome/chrome"
    timeout_seconds: float = 240.0
    window_size: str = "900,900"
    _process: subprocess.Popen[bytes] | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @property
    def cdp_url(self) -> str:
        return f"http://127.0.0.1:{self.debug_port}"

    def _endpoint_ready(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.cdp_url}/json/version", timeout=0.5) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError):
            return False

    def ensure_browser(self) -> None:
        if self._endpoint_ready():
            return
        self.profile_directory.mkdir(parents=True, exist_ok=True)
        log_path = self.profile_directory / "roundtable-browser.log"
        log = log_path.open("ab")
        self._process = subprocess.Popen(
            [
                self.chrome_path,
                f"--user-data-dir={self.profile_directory}",
                "--profile-directory=Default",
                "--new-window",
                "--no-first-run",
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={self.debug_port}",
                f"--window-size={self.window_size}",
                self.site.url,
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self._endpoint_ready():
                return
            if self._process.poll() is not None:
                raise RuntimeError(
                    f"{self.name} browser exited during startup; see {log_path}"
                )
            time.sleep(0.2)
        raise RuntimeError(f"{self.name} browser did not expose CDP on port {self.debug_port}")

    @staticmethod
    def _first_visible(page: Any, selectors: tuple[str, ...]) -> Any | None:
        for selector in selectors:
            locator = page.locator(selector)
            for index in range(locator.count()):
                item = locator.nth(index)
                if item.is_visible():
                    return item
        return None

    def _wait_for_prompt(self, page: Any, timeout_seconds: float = 20.0) -> Any | None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            prompt = self._first_visible(page, self.site.prompt_selectors)
            if prompt is not None:
                return prompt
            page.wait_for_timeout(250)
        return None

    def _site_page(self, browser: Any) -> Any:
        contexts = browser.contexts
        if not contexts:
            raise RuntimeError(f"{self.name} browser has no context")
        context = contexts[0]
        for page in context.pages:
            if self.site.host_fragment in page.url:
                return page
        page = context.new_page()
        page.goto(self.site.url, wait_until="domcontentloaded", timeout=60_000)
        return page

    def _wait_for_answer(self, page: Any, selector: str, previous_count: int) -> str:
        deadline = time.monotonic() + self.timeout_seconds
        stable_since: float | None = None
        last_text = ""
        while time.monotonic() < deadline:
            responses = page.locator(selector)
            if responses.count() > previous_count:
                text = responses.last.inner_text().strip()
                stop_visible = self._first_visible(page, self.site.stop_selectors) is not None
                if text and text == last_text and not stop_visible:
                    stable_since = stable_since or time.monotonic()
                    if time.monotonic() - stable_since >= 2.0:
                        return text
                else:
                    stable_since = None
                    last_text = text
            page.wait_for_timeout(400)
        raise TimeoutError(f"{self.name} did not finish within {self.timeout_seconds:g} seconds")

    def probe(self) -> dict[str, Any]:
        self.ensure_browser()
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        browser = playwright.chromium.connect_over_cdp(self.cdp_url)
        try:
            page = self._site_page(browser)
            prompt = self._first_visible(page, self.site.prompt_selectors)
            body = page.locator("body").inner_text(timeout=10_000)
            gated = any(text in body for text in self.site.login_gate_text)
            return {
                "service": self.site.service,
                "url": page.url,
                "prompt_ready": prompt is not None,
                "login_gate_visible": gated,
                "debug_port": self.debug_port,
            }
        finally:
            browser.close()
            playwright.stop()

    def respond(self, prompt: str) -> tuple[str, dict[str, Any]]:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Browser participant prompt cannot be empty")
        with self._lock:
            self.ensure_browser()
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            browser = playwright.chromium.connect_over_cdp(self.cdp_url)
            try:
                page = self._site_page(browser)
                if page.url.rstrip("/") != self.site.url.rstrip("/"):
                    page.goto(self.site.url, wait_until="domcontentloaded", timeout=60_000)
                prompt_box = self._wait_for_prompt(page)
                if prompt_box is None:
                    raise RuntimeError(
                        f"{self.name} prompt is unavailable; the saved session may require login"
                    )
                response_selector = self.site.response_selectors[0]
                previous_count = page.locator(response_selector).count()
                prompt_box.fill(prompt)
                prompt_box.press("Enter")
                content = self._wait_for_answer(page, response_selector, previous_count)
                return content, {
                    "kind": "visible-browser",
                    "service": self.site.service,
                    "url": page.url,
                    "debug_port": self.debug_port,
                }
            finally:
                browser.close()
                playwright.stop()


def participant_from_json(value: str) -> VisibleBrowserParticipant:
    data = json.loads(value)
    sites = {"chatgpt": CHATGPT, "claude": CLAUDE}
    return VisibleBrowserParticipant(
        name=data["name"],
        site=sites[data["service"]],
        profile_directory=Path(data["profile_directory"]),
        debug_port=int(data["debug_port"]),
    )
