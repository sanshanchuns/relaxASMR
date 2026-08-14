"""Playwright 基座：供 ``jimeng_web`` / ``elevenlabs_web`` 共用。"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

LogFn = Callable[[str], None] | None

_PROXY_ENV_KEYS = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "all_proxy",
    "ALL_PROXY",
)


class BrowserError(RuntimeError):
    pass


def log_line(log: LogFn, msg: str) -> None:
    if log:
        log(msg)


@contextmanager
def cleared_proxy_env() -> Iterator[None]:
    saved = {k: os.environ.pop(k) for k in _PROXY_ENV_KEYS if k in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def stage_media(
    path: Path | str,
    *,
    log: LogFn = None,
    prefix: str = "pw_",
) -> tuple[str, Path | None]:
    src = Path(path).expanduser()
    if not src.is_file():
        raise BrowserError(f"媒体文件不存在: {src}")
    resolved = src.resolve()
    text = str(resolved)
    if not text.startswith("/mnt/"):
        return text, None
    suffix = resolved.suffix or ".bin"
    fd, tmp_name = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    tmp = Path(tmp_name)
    shutil.copy2(resolved, tmp)
    log_line(log, f"  … 已复制到本地: {tmp.name}")
    return str(tmp), tmp


def cleanup_stage(tmp: Path | None) -> None:
    if tmp is None:
        return
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass


def headless_default(env_key: str, *, default: bool = False) -> bool:
    env = os.environ.get(env_key, "").strip().lower()
    if env in {"1", "true", "yes"}:
        return True
    if env in {"0", "false", "no"}:
        return False
    return default


@contextmanager
def browser_context(
    *,
    profile_dir: Path,
    headless: bool | None = None,
    env_key: str = "PW_HEADLESS",
    locale: str = "zh-CN",
):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserError(
            "请先安装 playwright：pip install playwright && playwright install chromium"
        ) from exc

    profile_dir.mkdir(parents=True, exist_ok=True)
    headed = headless_default(env_key) if headless is None else headless
    launch_kwargs: dict[str, Any] = {
        "user_data_dir": str(profile_dir),
        "headless": headed,
        "locale": locale,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
        "accept_downloads": True,
    }
    if headed:
        launch_kwargs["no_viewport"] = True
    else:
        launch_kwargs["viewport"] = {"width": 1440, "height": 1100}

    with cleared_proxy_env(), sync_playwright() as p:
        context = p.chromium.launch_persistent_context(**launch_kwargs)
        try:
            yield context
        finally:
            context.close()


def save_debug(page: Any, debug_dir: Path, name: str) -> Path | None:
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = debug_dir / f"{name}_{stamp}.png"
        page.screenshot(path=str(path), full_page=True)
        return path
    except Exception:  # noqa: BLE001
        return None


def dismiss_modals(page: Any, *, rounds: int = 4, log: LogFn = None) -> None:
    """Close promo / privacy / paywall overlays that block the main UI.

    Prefer dismiss / close; never click purchase CTAs like「收下福利」「立即开通」.
    """
    dismiss_labels = ("再想想", "我知道了", "暂不", "以后再说", "关闭", "同意", "取消")
    for _ in range(rounds):
        clicked = False
        for label in dismiss_labels:
            try:
                btn = page.get_by_role("button", name=label).first
                if btn.count() == 0:
                    btn = page.get_by_text(label, exact=True).first
                if btn.count() > 0 and btn.is_visible(timeout=300):
                    btn.click(timeout=2000)
                    log_line(log, f"  … 已点「{label}」关弹窗")
                    page.wait_for_timeout(500)
                    clicked = True
                    break
            except Exception:  # noqa: BLE001
                continue
        if clicked:
            continue
        closed = False
        for sel in (
            ".lv-modal-close-icon",
            ".lv-modal-close-btn",
            "button.lv-modal-close",
            ".lv-modal-close",
            '[aria-label="Close"]',
            '[aria-label="关闭"]',
            '[class*="close-icon"]',
            '[class*="CloseBtn"]',
            '[class*="close-btn"]',
        ):
            try:
                loc = page.locator(sel)
                for i in range(min(loc.count(), 3)):
                    btn = loc.nth(i)
                    if btn.is_visible(timeout=200):
                        btn.click(timeout=1000, force=True)
                        closed = True
            except Exception:  # noqa: BLE001
                continue
        try:
            page.keyboard.press("Escape")
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(350)
        if not closed:
            try:
                dialogs = page.locator(".lv-modal, [role='dialog']")
                any_visible = False
                for i in range(min(dialogs.count(), 6)):
                    if dialogs.nth(i).is_visible(timeout=150):
                        any_visible = True
                        break
                if not any_visible:
                    break
            except Exception:  # noqa: BLE001
                break


def upload_file(
    page: Any,
    abs_path: str,
    *,
    log: LogFn = None,
    media_kind: str = "image",
) -> bool:
    """Upload via file chooser first, then hidden input fallback."""
    labels = ("上传图片", "上传", "Upload image", "Upload", "选择文件", "Add image")
    if media_kind == "video":
        labels = ("上传视频", "Upload video", "Upload", "选择文件") + labels

    for label in labels:
        try:
            btn = page.get_by_role("button", name=label).first
            if btn.count() == 0:
                btn = page.get_by_text(label, exact=False).first
            if btn.count() == 0:
                continue
            with page.expect_file_chooser(timeout=15_000) as fc_info:
                btn.click(timeout=5000)
            fc_info.value.set_files(abs_path)
            log_line(log, f"  ✓ 通过按钮「{label}」上传")
            page.wait_for_timeout(800)
            return True
        except Exception:  # noqa: BLE001
            continue

    selectors = [
        'input[type="file"][accept*="image"]',
        'input[type="file"][accept*="video"]',
        "input.upload-input",
        'input[type="file"]',
    ]
    if media_kind == "video":
        selectors = selectors[1:] + selectors[:1]

    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if page.locator('input[type="file"]').count() > 0:
            break
        page.wait_for_timeout(300)
    else:
        log_line(log, "  … 20s 内未出现 input[type=file]")
        return False

    for sel in selectors:
        loc = page.locator(sel)
        try:
            count = loc.count()
        except Exception:  # noqa: BLE001
            continue
        for i in range(count):
            target = loc.nth(i)
            try:
                target.set_input_files(abs_path, timeout=20_000)
                log_line(log, f"  ✓ 通过 {sel} 上传")
                page.wait_for_timeout(800)
                return True
            except Exception:  # noqa: BLE001
                continue
    return False


def fill_prompt_text(page: Any, prompt: str, *, log: LogFn = None) -> bool:
    selectors = [
        'textarea[placeholder*="prompt" i]',
        'textarea[placeholder*="描述" i]',
        'textarea[placeholder*="提示" i]',
        ".tiptap.ProseMirror",
        '[contenteditable="true"]',
        "textarea",
    ]
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.count() == 0 or not loc.is_visible(timeout=500):
                continue
            loc.click(timeout=3000)
            loc.fill(prompt, timeout=5000)
            log_line(log, f"  ✓ 已填写 prompt（{sel}）")
            return True
        except Exception:  # noqa: BLE001
            try:
                loc.click(timeout=3000)
                page.keyboard.press("Control+A")
                page.keyboard.type(prompt, delay=10)
                log_line(log, f"  ✓ 已键入 prompt（{sel}）")
                return True
            except Exception:  # noqa: BLE001
                continue
    return False


def click_generate(page: Any, *, log: LogFn = None) -> bool:
    # 先点 composer 圆形提交（即梦无「生成」文案；避免误点侧栏菜单「生成」）
    icon_selectors = (
        "[class*='collapsed-submit'] button.lv-btn-primary:not([disabled])",
        "[class*='submit-button'] button.lv-btn-primary:not([disabled])",
        "button.lv-btn-primary.lv-btn-shape-circle.lv-btn-icon-only:not([disabled])",
    )
    for sel in icon_selectors:
        try:
            btns = page.locator(sel)
            # 选可见且尺寸正常的（排除 16px 占位禁用钮）
            for i in range(min(btns.count(), 6)):
                btn = btns.nth(i)
                if not btn.is_visible(timeout=400):
                    continue
                box = btn.bounding_box()
                if not box or box["width"] < 24 or box["height"] < 24:
                    continue
                btn.click(timeout=8000)
                log_line(log, f"  ✓ 已点击提交按钮（{sel}）")
                return True
        except Exception:  # noqa: BLE001
            continue

    # 文案按钮：只用 role=button 精确名，禁止 get_by_text（会点到侧栏「生成」）
    labels = ("开始生成", "Create video", "Generate", "Create")
    for label in labels:
        try:
            btn = page.get_by_role("button", name=label, exact=True).first
            if btn.count() == 0 or not btn.is_visible(timeout=500):
                continue
            btn.click(timeout=8000)
            log_line(log, f"  ✓ 已点击「{label}」")
            return True
        except Exception:  # noqa: BLE001
            continue
    return False


def wait_and_save_download(
    page: Any,
    out_path: Path,
    *,
    timeout_s: float = 900.0,
    log: LogFn = None,
) -> Path:
    """Wait for a download event and save to out_path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with page.expect_download(timeout=int(timeout_s * 1000)) as dl_info:
            pass
        download = dl_info.value
        download.save_as(str(out_path))
        log_line(log, f"  ✓ 已下载 {out_path.name}")
        return out_path
    except Exception:  # noqa: BLE001
        pass

    # Fallback: look for video src / download link
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for sel in ("video source", "video", 'a[download]', 'a[href*=".mp4"]'):
            loc = page.locator(sel).first
            try:
                if loc.count() == 0:
                    continue
                href = loc.get_attribute("src") or loc.get_attribute("href")
                if href and (".mp4" in href or href.startswith("http")):
                    import requests

                    r = requests.get(href, timeout=120)
                    r.raise_for_status()
                    out_path.write_bytes(r.content)
                    log_line(log, f"  ✓ 已从 URL 保存 {out_path.name}")
                    return out_path
            except Exception:  # noqa: BLE001
                continue
        page.wait_for_timeout(2000)
    raise BrowserError(f"等待下载超时（{int(timeout_s)}s）")


def interactive_login(
    *,
    profile_dir: Path,
    login_url: str,
    looks_logged_in: Callable[[str, str], bool],
    timeout_s: float = 300.0,
    log: LogFn = None,
) -> bool:
    log_line(log, f"[登录] 打开 {login_url} …")
    with browser_context(profile_dir=profile_dir, headless=False) as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1500)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                url = page.url
                body = page.locator("body").inner_text(timeout=2000)
            except Exception:  # noqa: BLE001
                page.wait_for_timeout(1000)
                continue
            if looks_logged_in(url, body):
                log_line(log, "  ✓ 已检测到登录态")
                return True
            page.wait_for_timeout(1500)
    raise BrowserError(f"登录超时（{int(timeout_s)}s）")


def check_logged_in(
    *,
    profile_dir: Path,
    login_url: str,
    looks_logged_in: Callable[[str, str], bool],
    log: LogFn = None,
) -> bool:
    try:
        with browser_context(profile_dir=profile_dir, headless=True) as context:
            page = context.new_page()
            page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(1200)
            return looks_logged_in(page.url, page.locator("body").inner_text(timeout=3000))
    except Exception as exc:  # noqa: BLE001
        log_line(log, f"  … 检查登录失败：{exc}")
        return False
