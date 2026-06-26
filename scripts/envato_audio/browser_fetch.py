"""用 CloakBrowser 绕过 Cloudflare，抓取 Envato Elements 页面/API。

https://github.com/CloakHQ/cloakbrowser
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROFILE_DIR = SCRIPT_DIR / ".envato_browser_profile"

CF_MARKERS = ("Just a moment...", "cf-chl")


def detect_system_proxy() -> str | None:
    for key in (
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return None


def parse_cookie_header(cookie_str: str) -> list[dict[str, str]]:
    cookies: list[dict[str, str]] = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies.append(
            {
                "name": name.strip(),
                "value": unquote(value.strip()),
                "domain": ".elements.envato.com",
                "path": "/",
            }
        )
    return cookies


class BrowserFetcher:
    """持久化 profile + CloakBrowser，自动过 Cloudflare Turnstile。"""

    def __init__(
        self,
        creds: dict,
        *,
        profile_dir: Path | None = None,
        headless: bool = True,
        proxy: str | None = None,
        humanize: bool = True,
    ) -> None:
        self.creds = creds
        self.profile_dir = profile_dir or DEFAULT_PROFILE_DIR
        self.headless = headless
        self.proxy = proxy if proxy is not None else detect_system_proxy()
        self.humanize = humanize
        self._ctx: Any = None
        self._cookies_injected = False
        self._warmed = False

    def _ensure_context(self) -> Any:
        if self._ctx is not None:
            return self._ctx

        from cloakbrowser import launch_persistent_context

        kwargs: dict[str, Any] = {
            "headless": self.headless,
            "humanize": self.humanize,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy

        self._ctx = launch_persistent_context(str(self.profile_dir), **kwargs)
        self._maybe_inject_cookies()
        self._warm_up()
        return self._ctx

    def _maybe_inject_cookies(self) -> None:
        if self._cookies_injected or self._ctx is None:
            return
        cookie = (self.creds.get("cookie") or "").strip()
        if len(cookie) < 50:
            return
        parsed = parse_cookie_header(cookie)
        if parsed:
            self._ctx.add_cookies(parsed)
            self._cookies_injected = True

    def _warm_up(self) -> None:
        if self._warmed or self._ctx is None:
            return
        page = self._ctx.new_page()
        try:
            page.goto(
                "https://elements.envato.com/",
                wait_until="domcontentloaded",
                timeout=120000,
            )
            self._wait_for_content(page, wait_for="envato", timeout=90)
        except Exception:
            pass
        finally:
            page.close()
        self._warmed = True

    def _wait_for_content(self, page: Any, *, wait_for: str, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        last = ""
        while time.monotonic() < deadline:
            last = page.content()
            if wait_for in last and not any(m in last for m in CF_MARKERS):
                return last
            time.sleep(1.5)
        return last

    def _fetch_once(self, url: str, *, timeout: float, wait_for: str) -> str:
        ctx = self._ensure_context()
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            try:
                if page.locator("pre").count() > 0:
                    text = page.locator("pre").first.inner_text(timeout=5000)
                    if text.strip():
                        return text
            except Exception:
                pass
            return self._wait_for_content(page, wait_for=wait_for, timeout=timeout)
        finally:
            page.close()

    def fetch_html(self, url: str, *, timeout: float = 120) -> str:
        body = ""
        for attempt in range(2):
            body = self._fetch_once(url, timeout=timeout, wait_for="preview.m4a")
            if "preview.m4a" in body and not any(m in body for m in CF_MARKERS):
                return body
            if attempt == 0:
                time.sleep(3)
        return body

    def fetch_body(self, url: str, *, timeout: float = 120) -> str:
        body = ""
        for attempt in range(2):
            body = self._fetch_once(url, timeout=timeout, wait_for="preview.m4a")
            if body.strip().startswith("{") or "preview.m4a" in body:
                if not any(m in body for m in CF_MARKERS):
                    return body
            if attempt == 0:
                time.sleep(3)
        return body

    def close(self) -> None:
        if self._ctx is not None:
            self._ctx.close()
            self._ctx = None
