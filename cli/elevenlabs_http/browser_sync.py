"""用 Playwright 从 elevenlabs.io 会话导出 Firebase refresh / id token。

一次 ``python -m elevenlabs_http login``（有头浏览器登录）后，把
``refresh_token.md`` 落盘；之后靠 Firebase API 自动续 Bearer，不必再贴 curl。

也可 ``connect --cdp http://127.0.0.1:9222`` 挂到你已打开的 Chrome。
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .auth import (
    BEARER_PATH,
    COOKIE_PATH,
    DIR,
    REFRESH_PATH,
    refresh_firebase_id_token,
)

PROFILE_DIR = DIR / ".profile"
DEFAULT_APP_URL = "https://elevenlabs.io/app/image-video?modality=video"
_SINGLETON_NAMES = ("SingletonLock", "SingletonCookie", "SingletonSocket")

_PROXY_ENV_KEYS = (
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
)


def _proxy_server_from_env() -> str | None:
    """优先 HTTP(S)_PROXY。ALL_PROXY 常为 socks，WSL 下端口未开时会 ERR_PROXY_CONNECTION_FAILED。"""
    override = (os.environ.get("ELEVENLABS_BROWSER_PROXY") or "").strip()
    if override.lower() in {"0", "none", "off", "direct"}:
        return None
    if override:
        return override
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    for key in ("ALL_PROXY", "all_proxy"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return None


def resolve_browser_proxy(
    *,
    proxy: str | None = None,
    no_proxy: bool = False,
) -> dict[str, str] | None:
    """返回 Playwright ``proxy=`` 参数；``None`` 表示直连（调用方需清掉环境代理）。"""
    if no_proxy:
        return None
    if proxy is not None:
        p = proxy.strip()
        if not p or p.lower() in {"0", "none", "off", "direct"}:
            return None
        return {"server": p}
    server = _proxy_server_from_env()
    return {"server": server} if server else None


@contextmanager
def _without_proxy_env() -> Iterator[None]:
    saved = {k: os.environ.pop(k) for k in _PROXY_ENV_KEYS if k in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def _goto_app(page: Any, app_url: str) -> None:
    try:
        page.goto(app_url, wait_until="domcontentloaded", timeout=120_000)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "ERR_PROXY_CONNECTION_FAILED" in msg or "PROXY" in msg.upper():
            raise BrowserSyncError(
                f"打开页面失败（代理不可用）：{msg}\n"
                "可试：\n"
                "  • PYTHONPATH=cli:. python -m elevenlabs_http login --no-proxy\n"
                "  • 或 --proxy http://127.0.0.1:7890\n"
                "  • 或 export ELEVENLABS_BROWSER_PROXY=direct"
            ) from exc
        raise


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _singleton_lock_pid(profile: Path) -> int | None:
    """Chromium SingletonLock 常为 symlink，目标形如 ``hostname-12345``。"""
    lock = profile / "SingletonLock"
    if not lock.exists() and not lock.is_symlink():
        return None
    try:
        target = os.readlink(lock) if lock.is_symlink() else lock.read_text(encoding="utf-8")
    except OSError:
        return None
    name = Path(str(target).strip()).name
    if "-" not in name:
        return None
    tail = name.rsplit("-", 1)[-1]
    if not tail.isdigit():
        return None
    return int(tail)


def _clear_singleton_files(profile: Path) -> None:
    for name in _SINGLETON_NAMES:
        path = profile / name
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _profile_chrome_pids(profile: Path) -> list[int]:
    marker = f"--user-data-dir={profile}"
    try:
        out = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True)
    except (OSError, subprocess.CalledProcessError):
        return []
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or marker not in line:
            continue
        if "chrome" not in line.lower() and "chromium" not in line.lower():
            continue
        try:
            pids.append(int(line.split(None, 1)[0]))
        except ValueError:
            continue
    return pids


def prepare_profile_dir(profile: Path, *, force: bool = False) -> None:
    """清理失效 SingletonLock；``force`` 时结束仍占用该 profile 的 Chromium。"""
    profile.mkdir(parents=True, exist_ok=True)
    lock_pid = _singleton_lock_pid(profile)
    live_pids = _profile_chrome_pids(profile)

    if force and live_pids:
        for pid in live_pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.time() + 5
        while time.time() < deadline and _profile_chrome_pids(profile):
            time.sleep(0.2)
        for pid in _profile_chrome_pids(profile):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        live_pids = _profile_chrome_pids(profile)

    if live_pids:
        raise BrowserSyncError(
            "ElevenLabs 登录用的 Chromium 仍在运行（占用 .profile）。\n"
            "请关掉那个浏览器窗口，或运行：\n"
            "  PYTHONPATH=cli:. python -m elevenlabs_http login --force"
        )

    if lock_pid is not None and _pid_alive(lock_pid):
        # 锁指向活进程，但上面没扫到 chrome——仍可能冲突
        raise BrowserSyncError(
            f"profile 被进程 pid={lock_pid} 占用（SingletonLock）。\n"
            "关掉对应 Chromium，或：PYTHONPATH=cli:. python -m elevenlabs_http login --force"
        )

    # 进程已死但锁残留（上次 login 崩溃/连接断开时常见）
    if lock_pid is not None or any((profile / n).exists() or (profile / n).is_symlink() for n in _SINGLETON_NAMES):
        _clear_singleton_files(profile)


# IndexedDB（旧）+ localStorage firebase:authUser:*（ElevenLabs 当前实际落盘处）。
_EXTRACT_FIREBASE_JS = """
async () => {
  const rows = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith('firebase:authUser:')) {
        rows.push({ key: k, value: localStorage.getItem(k) });
      }
    }
  } catch (e) { /* ignore */ }

  const dbName = 'firebaseLocalStorageDb';
  const storeName = 'firebaseLocalStorage';
  const idbRows = await new Promise((resolve) => {
    let open;
    try {
      open = indexedDB.open(dbName);
    } catch (e) {
      resolve([]);
      return;
    }
    open.onerror = () => resolve([]);
    open.onsuccess = () => {
      const db = open.result;
      if (![...db.objectStoreNames].includes(storeName)) {
        resolve([]);
        return;
      }
      const tx = db.transaction(storeName, 'readonly');
      const store = tx.objectStore(storeName);
      const req = store.getAll();
      req.onerror = () => resolve([]);
      req.onsuccess = () => resolve(req.result || []);
    };
  });
  for (const row of idbRows || []) rows.push(row);
  return rows;
}
"""


@dataclass
class SyncedTokens:
    refresh_token: str
    id_token: str = ""
    email: str = ""
    source: str = ""  # playwright_profile | cdp


class BrowserSyncError(RuntimeError):
    pass


def _parse_firebase_rows(rows: list[Any]) -> tuple[str, str, str]:
    """返回 (refresh_token, id_token, email)。"""
    best_refresh = ""
    best_id = ""
    best_email = ""
    best_exp = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        value = row.get("value")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                continue
        if not isinstance(value, dict):
            continue
        sts = value.get("stsTokenManager") or {}
        if not isinstance(sts, dict):
            continue
        refresh = str(sts.get("refreshToken") or "").strip()
        access = str(
            sts.get("accessToken") or sts.get("idToken") or value.get("idToken") or ""
        ).strip()
        email = str(value.get("email") or "").strip()
        try:
            exp = int(sts.get("expirationTime") or 0)
        except (TypeError, ValueError):
            exp = 0
        # expirationTime 有时是毫秒
        if exp > 10_000_000_000:
            exp = exp // 1000
        if refresh and (exp >= best_exp or not best_refresh):
            best_refresh = refresh
            best_id = access
            best_email = email
            best_exp = exp
    return best_refresh, best_id, best_email


def _cookies_to_header(cookies: list[dict]) -> str:
    parts = []
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        if name and value is not None:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def _save_tokens(
    *,
    refresh_token: str,
    id_token: str = "",
    cookie_header: str = "",
) -> SyncedTokens:
    refresh_token = refresh_token.strip()
    if not refresh_token:
        raise BrowserSyncError("未拿到 Firebase refreshToken")
    REFRESH_PATH.write_text(refresh_token + "\n", encoding="utf-8")
    if not id_token:
        id_token = refresh_firebase_id_token(refresh_token)
    BEARER_PATH.write_text(id_token.strip() + "\n", encoding="utf-8")
    if cookie_header.strip():
        COOKIE_PATH.write_text(cookie_header.strip() + "\n", encoding="utf-8")
    email = ""
    try:
        from .auth import _jwt_claims

        email = str(_jwt_claims(id_token).get("email") or "")
    except Exception:  # noqa: BLE001
        pass
    return SyncedTokens(
        refresh_token=refresh_token,
        id_token=id_token.strip(),
        email=email,
    )


def extract_tokens_from_page(page: Any) -> tuple[str, str, str]:
    rows = page.evaluate(_EXTRACT_FIREBASE_JS)
    return _parse_firebase_rows(rows if isinstance(rows, list) else [])


def _wait_and_extract(
    page: Any,
    *,
    timeout_sec: float = 300,
    poll_sec: float = 2.0,
) -> tuple[str, str, str]:
    deadline = time.time() + timeout_sec
    last_err = ""
    while time.time() < deadline:
        try:
            refresh, id_token, email = extract_tokens_from_page(page)
            if refresh:
                return refresh, id_token, email
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
        time.sleep(poll_sec)
    raise BrowserSyncError(
        "等待登录超时：请在打开的浏览器里完成 Google 登录，"
        f"直到能打开 Image & Video。{(' 最后错误：' + last_err) if last_err else ''}"
    )


def sync_with_persistent_profile(
    *,
    headless: bool = False,
    profile_dir: Path | None = None,
    app_url: str = DEFAULT_APP_URL,
    timeout_sec: float = 300,
    proxy: str | None = None,
    no_proxy: bool = False,
    force: bool = False,
) -> SyncedTokens:
    """有头登录（或复用已有 profile）并导出 refresh_token。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserSyncError(
            "未安装 playwright：pip install playwright && playwright install chromium"
        ) from exc

    profile = Path(profile_dir or PROFILE_DIR)
    prepare_profile_dir(profile, force=force)
    proxy_opt = resolve_browser_proxy(proxy=proxy, no_proxy=no_proxy)
    launch_kwargs: dict[str, Any] = {
        "user_data_dir": str(profile),
        "headless": headless,
        "viewport": {"width": 1280, "height": 900},
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if proxy_opt:
        launch_kwargs["proxy"] = proxy_opt

    # 直连时必须清掉环境变量，否则 Playwright 仍会吃坏掉的 ALL_PROXY(socks)。
    env_cm = _without_proxy_env() if not proxy_opt else nullcontext()
    with env_cm, sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "ProcessSingleton" in msg or "SingletonLock" in msg or "profile is already in use" in msg:
                raise BrowserSyncError(
                    "profile 目录仍被占用（ProcessSingleton）。\n"
                    "关掉上次 login 打开的 Chromium，或：\n"
                    "  PYTHONPATH=cli:. python -m elevenlabs_http login --force"
                ) from exc
            raise
        try:
            page = context.pages[0] if context.pages else context.new_page()
            _goto_app(page, app_url)
            refresh, id_token, email = _wait_and_extract(page, timeout_sec=timeout_sec)
            cookie_header = _cookies_to_header(context.cookies())
            synced = _save_tokens(
                refresh_token=refresh,
                id_token=id_token,
                cookie_header=cookie_header,
            )
            synced.email = synced.email or email
            synced.source = "playwright_profile"
            return synced
        finally:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass
            _clear_singleton_files(profile)


def sync_via_cdp(
    cdp_url: str = "http://127.0.0.1:9222",
    *,
    app_url: str = DEFAULT_APP_URL,
    timeout_sec: float = 120,
) -> SyncedTokens:
    """挂到已开远程调试的 Chrome，从当前标签页读 IndexedDB。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserSyncError(
            "未安装 playwright：pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        # 不要 browser.close()——会关掉用户的 Chrome；退出 with 块即断开 CDP。
        browser = p.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            raise BrowserSyncError(f"CDP {cdp_url} 没有 browser context")
        context = browser.contexts[0]
        page = None
        for candidate in context.pages:
            if "elevenlabs.io" in (candidate.url or ""):
                page = candidate
                break
        if page is None:
            page = context.new_page()
            _goto_app(page, app_url)
        refresh, id_token, email = _wait_and_extract(page, timeout_sec=timeout_sec)
        cookie_header = _cookies_to_header(context.cookies())
        synced = _save_tokens(
            refresh_token=refresh,
            id_token=id_token,
            cookie_header=cookie_header,
        )
        synced.email = synced.email or email
        synced.source = "cdp"
        return synced
