"""CloakBrowser 持久化会话：过 Cloudflare Turnstile，供各站点 API 填充脚本复用。

底层：https://github.com/CloakHQ/cloakbrowser （pip 包名同为 cloakbrowser）
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .challenge import is_cloudflare_challenge
from .cookies import parse_cookie_header
from .proxy import detect_system_proxy

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_PROFILES_ROOT = PACKAGE_DIR / ".profiles"


def default_profile_dir(name: str = "default") -> Path:
    root = Path(os.environ.get("CLOAK_BROWSER_PROFILES_DIR", DEFAULT_PROFILES_ROOT))
    return root / name


def _cookie_domain_from_url(url: str) -> str:
    host = urlparse(url).netloc
    if host.startswith("www."):
        return host[4:]
    return f".{host}"


class CloakBrowserSession:
    """持久化 profile + CloakBrowser，可预热、注入 Cookie、按标记等待页面就绪。"""

    def __init__(
        self,
        *,
        profile_name: str = "default",
        profile_dir: Path | None = None,
        headless: bool = True,
        proxy: str | None = None,
        humanize: bool = True,
        warm_up_url: str | None = None,
        warm_up_wait_for: str | None = None,
        cookies: str | None = None,
        cookie_domain: str | None = None,
    ) -> None:
        self.profile_dir = profile_dir or default_profile_dir(profile_name)
        self.headless = headless
        self.proxy = proxy if proxy is not None else detect_system_proxy()
        self.humanize = humanize
        self.warm_up_url = warm_up_url
        self.warm_up_wait_for = warm_up_wait_for
        self._cookie_str = (cookies or "").strip()
        self._cookie_domain = cookie_domain
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

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._ctx = launch_persistent_context(str(self.profile_dir), **kwargs)
        self._maybe_inject_cookies()
        self._warm_up()
        return self._ctx

    def _maybe_inject_cookies(self) -> None:
        if self._cookies_injected or self._ctx is None or len(self._cookie_str) < 20:
            return
        domain = self._cookie_domain
        if not domain:
            if self.warm_up_url:
                domain = _cookie_domain_from_url(self.warm_up_url)
            else:
                return
        parsed = parse_cookie_header(self._cookie_str, domain=domain)
        if parsed:
            self._ctx.add_cookies(parsed)
            self._cookies_injected = True

    def _warm_up(self) -> None:
        if self._warmed or self._ctx is None or not self.warm_up_url:
            return
        page = self._ctx.new_page()
        try:
            page.goto(
                self.warm_up_url,
                wait_until="domcontentloaded",
                timeout=120000,
            )
            marker = self.warm_up_wait_for or urlparse(self.warm_up_url).netloc
            self._wait_for_content(page, wait_for=marker, timeout=90)
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
            if wait_for in last and not is_cloudflare_challenge(last):
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

    def fetch(
        self,
        url: str,
        *,
        wait_for: str | None = None,
        success_check: Callable[[str], bool] | None = None,
        timeout: float = 120,
        retries: int = 2,
    ) -> str:
        """打开 URL 并返回页面正文（HTML 或 JSON）。"""
        marker = wait_for or urlparse(url).netloc or "html"
        body = ""
        for attempt in range(max(1, retries)):
            body = self._fetch_once(url, timeout=timeout, wait_for=marker)
            if is_cloudflare_challenge(body):
                if attempt < retries - 1:
                    time.sleep(3)
                continue
            if success_check is None or success_check(body):
                return body
            if attempt < retries - 1:
                time.sleep(3)
        return body

    def fetch_json_or_html(
        self,
        url: str,
        *,
        html_marker: str | None = None,
        timeout: float = 120,
    ) -> str:
        """适合 data-api：JSON 或内嵌 HTML 片段。"""

        def ok(text: str) -> bool:
            if text.strip().startswith("{") or text.strip().startswith("["):
                return True
            if html_marker and html_marker in text:
                return True
            return not is_cloudflare_challenge(text)

        return self.fetch(
            url,
            wait_for=html_marker or urlparse(url).netloc,
            success_check=ok,
            timeout=timeout,
        )

    def close(self) -> None:
        if self._ctx is not None:
            self._ctx.close()
            self._ctx = None

    def __enter__(self) -> CloakBrowserSession:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
