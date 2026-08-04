"""ElevenLabs Image & Video 页 Playwright 自动化。"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from shared.browser import (
    BrowserError,
    browser_context,
    check_logged_in,
    cleanup_stage,
    click_generate,
    fill_prompt_text,
    interactive_login,
    log_line,
    save_debug,
    stage_media,
    upload_file,
)

PKG_DIR = Path(__file__).resolve().parent
PROFILE_DIR = PKG_DIR / ".profile"
DEBUG_DIR = PKG_DIR / "debug"

STUDIO_URL = os.environ.get(
    "ELEVENLABS_STUDIO_URL",
    "https://elevenlabs.io/app/image-video?modality=video",
)

LogFn = Callable[[str], None] | None


class ElevenLabsWebUiError(BrowserError):
    pass


@dataclass
class LoginStatus:
    is_logged_in: bool
    detail: str = ""


def _looks_logged_in(url: str, body: str) -> bool:
    low = (body or "").lower()
    if "sign in" in low or "log in" in low:
        if "sign out" not in low and "log out" not in low:
            return False
    if "elevenlabs.io/app" in url and ("image" in url or "video" in url or "image-video" in url):
        return True
    positives = ("Image & Video", "Generate", "Seedance", "Credits", "Workspace")
    return any(p in body for p in positives)


class ElevenLabsWebUiClient:
    poll_timeout_sec = 900

    def available(self) -> tuple[bool, str]:
        if not PROFILE_DIR.is_dir():
            return False, "未登录；请运行 python -m elevenlabs_web login"
        ok = check_logged_in(
            profile_dir=PROFILE_DIR,
            login_url=STUDIO_URL,
            looks_logged_in=_looks_logged_in,
        )
        if ok:
            return True, "elevenlabs web profile 已登录"
        return False, "ElevenLabs 未登录；请 python -m elevenlabs_web login"

    def login_status(self, *, log: LogFn = None) -> LoginStatus:
        ok, msg = self.available()
        return LoginStatus(is_logged_in=ok, detail=msg)

    def interactive_login(self, *, log: LogFn = None, timeout_s: float = 300.0) -> LoginStatus:
        try:
            interactive_login(
                profile_dir=PROFILE_DIR,
                login_url="https://elevenlabs.io/app/sign-in",
                looks_logged_in=lambda u, b: "elevenlabs.io/app" in u
                and "sign-in" not in u
                and "sign in" not in b.lower(),
                timeout_s=timeout_s,
                log=log,
            )
            return LoginStatus(is_logged_in=True, detail="已登录")
        except BrowserError as exc:
            raise ElevenLabsWebUiError(str(exc)) from exc

    def generate_i2v(
        self,
        image_path: Path,
        prompt: str,
        out_path: Path,
        *,
        duration_sec: int = 5,
        resolution: str = "480p",
        log: LogFn = None,
    ) -> Path:
        ok, reason = self.available()
        if not ok:
            raise ElevenLabsWebUiError(reason)

        staged, tmp = stage_media(image_path, log=log, prefix="elweb_")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        part = out_path.with_suffix(out_path.suffix + ".part")

        try:
            with browser_context(profile_dir=PROFILE_DIR, env_key="ELWEB_HEADLESS", locale="en-US") as context:
                page = context.new_page()
                log_line(log, f"[ElevenLabs-Web] 打开 Image & Video …")
                page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=90_000)
                page.wait_for_timeout(2500)

                if not _looks_logged_in(page.url, page.locator("body").inner_text(timeout=5000)):
                    snap = save_debug(page, DEBUG_DIR, "not_logged_in")
                    raise ElevenLabsWebUiError(
                        "ElevenLabs 未登录；请先 python -m elevenlabs_web login"
                        + (f"（截图 {snap}）" if snap else "")
                    )

                log_line(log, f"[ElevenLabs-Web] 上传首帧 …")
                if not upload_file(page, staged, log=log, media_kind="image"):
                    snap = save_debug(page, DEBUG_DIR, "upload_fail")
                    raise ElevenLabsWebUiError(
                        "上传图片失败"
                        + (f"；截图 {snap}" if snap else "")
                    )
                page.wait_for_timeout(1500)

                if prompt.strip():
                    if not fill_prompt_text(page, prompt.strip(), log=log):
                        log_line(log, "  … 未找到 prompt 框，继续")

                for text in (resolution, f"{duration_sec}s", f"{duration_sec} sec"):
                    try:
                        opt = page.get_by_text(text, exact=False).first
                        if opt.count() > 0 and opt.is_visible(timeout=500):
                            opt.click(timeout=2000)
                    except Exception:  # noqa: BLE001
                        pass

                log_line(log, "[ElevenLabs-Web] 生成并下载 …")
                try:
                    with page.expect_download(timeout=self.poll_timeout_sec * 1000) as dl_info:
                        if not click_generate(page, log=log):
                            snap = save_debug(page, DEBUG_DIR, "no_generate_btn")
                            raise ElevenLabsWebUiError(
                                "未找到 Generate 按钮"
                                + (f"；截图 {snap}" if snap else "")
                            )
                    download = dl_info.value
                    download.save_as(str(part))
                except ElevenLabsWebUiError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    deadline = time.monotonic() + self.poll_timeout_sec
                    saved = False
                    while time.monotonic() < deadline:
                        for sel in ("video", 'a[href*=".mp4"]'):
                            loc = page.locator(sel).first
                            try:
                                if loc.count() == 0:
                                    continue
                                src = loc.get_attribute("src") or loc.get_attribute("href")
                                if src and src.startswith("http"):
                                    import requests

                                    r = requests.get(src, timeout=120)
                                    r.raise_for_status()
                                    part.write_bytes(r.content)
                                    saved = True
                                    break
                            except Exception:  # noqa: BLE001
                                continue
                        if saved:
                            break
                        page.wait_for_timeout(3000)
                    if not saved:
                        snap = save_debug(page, DEBUG_DIR, "gen_timeout")
                        raise ElevenLabsWebUiError(
                            f"生成超时（{self.poll_timeout_sec}s）"
                            + (f"；截图 {snap}" if snap else "")
                        ) from exc

                if not part.is_file() or part.stat().st_size < 1024:
                    raise ElevenLabsWebUiError("下载结果为空")
                os.replace(part, out_path)
                log_line(log, f"[ElevenLabs-Web] 已保存 {out_path.name}")
                return out_path
        except ElevenLabsWebUiError:
            part.unlink(missing_ok=True)
            raise
        except BrowserError as exc:
            part.unlink(missing_ok=True)
            raise ElevenLabsWebUiError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            part.unlink(missing_ok=True)
            raise ElevenLabsWebUiError(str(exc)) from exc
        finally:
            cleanup_stage(tmp)
