"""即梦首页 Playwright：persistent profile + 图生视频。"""

from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from shared.browser import (
    BrowserError,
    browser_context,
    cleanup_stage,
    click_generate,
    dismiss_modals,
    fill_prompt_text,
    log_line,
    save_debug,
    stage_media,
    upload_file,
)

PKG_DIR = Path(__file__).resolve().parent
PROFILE_DIR = PKG_DIR / ".profile"
DEBUG_DIR = PKG_DIR / "debug"
PROFILE_LOCK = PKG_DIR / ".profile.lock"
LOGIN_MARK = PKG_DIR / ".logged_in"

# 视频生成实际在首页 composer，不是旧 assets-canvas
CANVAS_URL = os.environ.get(
    "JIMENG_CANVAS_URL",
    "https://jimeng.jianying.com/ai-tool/home?type=video&workspace=undefined",
)
DEFAULT_VIDEO_MODEL = os.environ.get("JIMENG_VIDEO_MODEL", "Seedance 2.0 VIP")
DEFAULT_REF_MODE = os.environ.get("JIMENG_REF_MODE", "首尾帧")
DEFAULT_DURATION_SEC = int(os.environ.get("JIMENG_DURATION_SEC", "5"))
DEFAULT_ASPECT = os.environ.get("JIMENG_ASPECT_RATIO", "16:9")
DEFAULT_RESOLUTION = os.environ.get("JIMENG_RESOLUTION", "720P")

LogFn = Callable[[str], None] | None
ProgressFn = Callable[[int], None] | None


class JimengWebError(BrowserError):
    pass


@dataclass
class LoginStatus:
    is_logged_in: bool
    detail: str = ""


@contextmanager
def _profile_lock(*, blocking: bool = True) -> Iterator[bool]:
    """跨进程锁，避免额度面板 / status 与 generate 抢同一 Chromium profile。"""
    PROFILE_LOCK.parent.mkdir(parents=True, exist_ok=True)
    fh = PROFILE_LOCK.open("a+", encoding="utf-8")
    acquired = False
    try:
        flags = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fcntl.flock(fh.fileno(), flags)
            acquired = True
        except BlockingIOError:
            acquired = False
            if blocking:
                raise
        yield acquired
    finally:
        if acquired:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        fh.close()


def _mark_logged_in(ok: bool) -> None:
    try:
        if ok:
            LOGIN_MARK.write_text(str(int(time.time())), encoding="utf-8")
        else:
            LOGIN_MARK.unlink(missing_ok=True)
    except OSError:
        pass


def _looks_logged_in(url: str, body: str) -> bool:
    """基于页面正文的粗检（interactive_login 轮询用）。"""
    del url
    if "同意协议后前往登录" in body:
        return False
    if "请登录" in body or "立即登录" in body:
        return False
    if "灵感" in body and "画布" in body and "登录" in body:
        compact = "".join(body.split())
        if "灵感生成资产画布登录" in compact:
            return False
    return any(p in body for p in ("退出", "登出", "账号", "个人中心", "我的资产"))


def _dom_logged_in(page) -> bool:
    """侧栏无「登录」菜单项才算已登录；侧栏未出现则视为未就绪/未登录。"""
    try:
        return bool(
            page.evaluate(
                """() => {
                  const side = document.querySelector(
                    '.dreamina-side-menu-container, [class*="sideMenu"]'
                  );
                  if (!side) return false;
                  const items = [...side.querySelectorAll(
                    '.lv-menu-item, [class*="menu-item"], a, button, div'
                  )];
                  return !items.some((el) => (el.innerText || '').trim() === '登录');
                }"""
            )
        )
    except Exception:  # noqa: BLE001
        return False


def _ensure_video_mode(page, *, log: LogFn = None) -> None:
    for label in ("视频生成", "视频"):
        try:
            opt = page.locator(
                ".home-type-select-option-_Iokeb, [class*='home-type-select']"
            ).filter(has_text=label).first
            if opt.count() == 0:
                opt = page.get_by_text(label, exact=True).first
            if opt.count() > 0 and opt.is_visible(timeout=800):
                cls = opt.get_attribute("class") or ""
                if "active" not in cls:
                    opt.click(timeout=3000)
                    page.wait_for_timeout(600)
                    log_line(log, f"  … 已切换到「{label}」")
                return
        except Exception:  # noqa: BLE001
            continue


def _normalize_model_label(text: str) -> str:
    return " ".join((text or "").replace("即梦", "").split()).lower()


def _model_selected(current: str, target: str) -> bool:
    """精确匹配目标模型；VIP 不含 Fast VIP / mini / 2.5。"""
    cur = _normalize_model_label(current)
    tgt = _normalize_model_label(target)
    if not cur:
        return False
    if "mini" in cur or "2.5" in cur:
        return False
    if "vip" in tgt and "fast" not in tgt and "fast" in cur:
        return False
    if tgt in cur:
        return True
    if "vip" in tgt:
        return "seedance" in cur and "2.0" in cur and "vip" in cur and "fast" not in cur
    return "seedance" in cur and "2.0" in cur and "vip" not in tgt


def _ensure_video_model(page, *, model: str = DEFAULT_VIDEO_MODEL, log: LogFn = None) -> None:
    """composer 工具栏模型下拉：默认 Seedance 2.0 VIP。"""
    try:
        selector = page.locator(
            ".lv-select[role='combobox'], .lv-select[class*='toolbar-select']"
        ).filter(has_text="Seedance").first
        if selector.count() == 0:
            selector = page.get_by_role("combobox").filter(has_text="Seedance").first
        if selector.count() == 0:
            log_line(log, "  … 未找到模型选择器，跳过")
            return

        cur_text = (selector.inner_text(timeout=2000) or "").replace("\n", " ").strip()
        if _model_selected(cur_text, model):
            log_line(log, f"  … 模型已是 {cur_text}")
            return

        log_line(log, f"  … 当前模型 {cur_text!r}，切换为 {model}")
        selector.click(timeout=3000)
        page.wait_for_timeout(700)

        # 优先点精确文案，避免误点 Fast VIP / mini
        labels = [
            f"即梦 {model}",
            model,
            "即梦 Seedance 2.0 VIP",
            "Seedance 2.0 VIP",
        ]
        for label in labels:
            try:
                opt = page.get_by_text(label, exact=True).first
                if opt.count() > 0 and opt.is_visible(timeout=500):
                    opt.click(timeout=3000)
                    page.wait_for_timeout(600)
                    dismiss_modals(page, rounds=2, log=log)
                    now = (
                        page.locator(".lv-select").filter(has_text="Seedance").first.inner_text(
                            timeout=2000
                        )
                        or ""
                    ).replace("\n", " ").strip()
                    if _model_selected(now, model):
                        log_line(log, f"  ✓ 已选模型「{now}」")
                        return
                    log_line(log, f"  … 点击「{label}」后仍是 {now!r}")
            except Exception:  # noqa: BLE001
                continue

        snap = save_debug(page, DEBUG_DIR, "model_select_fail")
        log_line(
            log,
            f"  … 未能切换到 {model}，继续用当前模型"
            + (f"（截图 {snap}）" if snap else ""),
        )
    except Exception as exc:  # noqa: BLE001
        log_line(log, f"  … 切换模型失败：{exc}")


def _ensure_ref_mode(page, *, mode: str = DEFAULT_REF_MODE, log: LogFn = None) -> None:
    """全能参考 / 首尾帧。"""
    try:
        selector = page.locator(".feature-select-glR6AZ .lv-select, .lv-select").filter(
            has_text=mode
        ).first
        if selector.count() == 0:
            selector = page.locator(".lv-select").filter(
                has_text="全能参考"
            ).or_(page.locator(".lv-select").filter(has_text="首尾帧")).first
        if selector.count() == 0:
            log_line(log, "  … 未找到参考模式选择器，跳过")
            return
        cur = (selector.inner_text(timeout=1500) or "").replace("\n", " ").strip()
        if mode in cur:
            log_line(log, f"  … 参考模式已是 {cur}")
            return
        log_line(log, f"  … 参考模式 {cur!r} → {mode}")
        selector.click(timeout=3000)
        page.wait_for_timeout(500)
        opt = page.get_by_text(mode, exact=True).first
        if opt.count() > 0 and opt.is_visible(timeout=800):
            opt.click(timeout=2000)
            page.wait_for_timeout(400)
            log_line(log, f"  ✓ 已选参考模式「{mode}」")
        else:
            log_line(log, f"  … 下拉中未找到「{mode}」")
            page.keyboard.press("Escape")
    except Exception as exc:  # noqa: BLE001
        log_line(log, f"  … 切换参考模式失败：{exc}")


def _ensure_duration(page, *, duration_sec: int, log: LogFn = None) -> None:
    """打开时长 popover，写入数字输入（VIP 支持 4s 等）。"""
    label = f"{duration_sec}s"
    try:
        btn = page.locator("button").filter(has_text=label).first
        if btn.count() > 0 and btn.is_visible(timeout=400):
            log_line(log, f"  … 时长已是 {label}")
            return

        opener = None
        for text in ("5s", "4s", "10s", "15s", "6s", "8s"):
            cand = page.locator("button").filter(has_text=text).first
            if cand.count() > 0 and cand.is_visible(timeout=300):
                opener = cand
                break
        if opener is None:
            log_line(log, "  … 未找到时长按钮，跳过")
            return

        opener.click(timeout=3000)
        page.wait_for_timeout(700)

        inp = page.locator(
            ".duration-panel-b5w4r5 input, [class*='duration-panel'] input, "
            "[class*='input-number'] input"
        ).first
        if inp.count() > 0 and inp.is_visible(timeout=800):
            inp.click(timeout=2000)
            inp.fill("")
            inp.type(str(duration_sec), delay=40)
            page.keyboard.press("Enter")
            page.wait_for_timeout(400)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            if page.locator("button").filter(has_text=label).count() > 0:
                log_line(log, f"  ✓ 已设置时长 {label}")
                return
            log_line(log, f"  … 写入 {duration_sec} 后工具栏未显示 {label}")
            return

        page.keyboard.press("Escape")
        log_line(log, f"  … 未能设置时长 {label}")
    except Exception as exc:  # noqa: BLE001
        log_line(log, f"  … 设置时长失败：{exc}")


def _ensure_aspect_resolution(
    page,
    *,
    aspect_ratio: str = DEFAULT_ASPECT,
    resolution: str = DEFAULT_RESOLUTION,
    log: LogFn = None,
) -> None:
    """确保 16:9 / 720P（首尾帧后可能变成「自动匹配」）。"""
    res = resolution.upper().replace("P", "") + "P"
    try:
        btn = page.locator("button").filter(has_text=aspect_ratio).first
        if btn.count() == 0:
            btn = page.locator("button").filter(has_text="自动匹配").first
        if btn.count() == 0:
            btn = page.locator("button").filter(has_text="720").first
        if btn.count() == 0:
            log_line(log, "  … 未找到比例/分辨率按钮，跳过")
            return

        text = (btn.inner_text(timeout=1000) or "").replace("\n", " ").strip()
        if aspect_ratio in text and res.replace("P", "") in text.upper():
            log_line(log, f"  … 比例/分辨率已是 {text}")
            return

        log_line(log, f"  … 当前 {text!r}，切换为 {aspect_ratio} {res}")
        btn.click(timeout=3000)
        page.wait_for_timeout(600)
        for label in (aspect_ratio, f"{aspect_ratio} {res}", res, "720P", "720p"):
            try:
                opt = page.get_by_text(label, exact=True).first
                if opt.count() > 0 and opt.is_visible(timeout=400):
                    opt.click(timeout=2000)
                    page.wait_for_timeout(400)
            except Exception:  # noqa: BLE001
                continue
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        now = page.locator("button").filter(has_text=aspect_ratio).first
        if now.count() > 0:
            shown = (now.inner_text(timeout=1000) or "").replace("\n", " ").strip()
            log_line(log, f"  ✓ 比例/分辨率 → {shown}")
        else:
            log_line(log, "  … 已尝试设置比例/分辨率")
    except Exception as exc:  # noqa: BLE001
        log_line(log, f"  … 检查比例失败：{exc}")


def _upload_loop_frames(page, abs_path: str, *, ref_mode: str, log: LogFn = None) -> bool:
    """首尾帧：同一张图写入前两个 file input；其它模式走通用 upload。"""
    if "首尾" not in ref_mode:
        return upload_file(page, abs_path, log=log, media_kind="image")

    inputs = page.locator('input[type="file"]')
    try:
        n = min(inputs.count(), 2)
    except Exception:  # noqa: BLE001
        n = 0
    if n >= 2:
        ok = 0
        for i in range(2):
            try:
                inputs.nth(i).set_input_files(abs_path, timeout=20_000)
                ok += 1
                page.wait_for_timeout(500)
            except Exception as exc:  # noqa: BLE001
                log_line(log, f"  … 首尾帧 input[{i}] 失败：{exc}")
        if ok >= 2:
            log_line(log, "  ✓ 已上传同一张图到首帧 + 尾帧")
            return True
        if ok == 1:
            log_line(log, "  … 仅写入 1 个槽位，再试通用上传")

    for label in ("首帧", "尾帧"):
        try:
            slot = page.get_by_text(label, exact=True).first
            if slot.count() == 0 or not slot.is_visible(timeout=500):
                continue
            with page.expect_file_chooser(timeout=8_000) as fc:
                slot.click(timeout=3000)
            fc.value.set_files(abs_path)
            log_line(log, f"  ✓ 已上传到「{label}」")
            page.wait_for_timeout(600)
        except Exception:  # noqa: BLE001
            continue

    return upload_file(page, abs_path, log=log, media_kind="image")


def _video_srcs(page) -> list[str]:
    try:
        return list(
            page.evaluate(
                """() => [...document.querySelectorAll('video')]
                  .map((v) => v.currentSrc || v.src || '')
                  .filter((s) => s.startsWith('http'))"""
            )
            or []
        )
    except Exception:  # noqa: BLE001
        return []


def _alive_page(context, page):
    """提交后可能跳转/关页；从 context 取仍可用的 page。"""
    try:
        _ = page.url
        return page
    except Exception:  # noqa: BLE001
        pass
    for p in list(context.pages):
        try:
            _ = p.url
            return p
        except Exception:  # noqa: BLE001
            continue
    return None


def _save_url(context, url: str, dest: Path, *, log: LogFn = None) -> bool:
    """用浏览器上下文拉视频直链（带 cookie / referer）。"""
    try:
        resp = context.request.get(url, timeout=180_000)
        if not resp.ok:
            log_line(log, f"  … 直链 HTTP {resp.status}")
            return False
        body = resp.body()
        if len(body) < 1024:
            return False
        dest.write_bytes(body)
        log_line(log, f"  ✓ 已从 video 直链保存（{len(body)} bytes）")
        return True
    except Exception as exc:  # noqa: BLE001
        log_line(log, f"  … 直链下载失败：{exc}")
        return False


def _read_dream_progress(page) -> int | None:
    """读取结果卡左上角「10%造梦中」进度；无则返回 None。"""
    try:
        return page.evaluate(
            """() => {
              const re = /(\\d{1,3})\\s*%\\s*造梦中/;
              const nodes = [...document.querySelectorAll('div,span,p,label')];
              let best = null;
              for (const el of nodes) {
                const t = (el.innerText || el.textContent || '').trim();
                if (!t || t.length > 24) continue;
                const m = t.match(re);
                if (!m) continue;
                const n = parseInt(m[1], 10);
                if (Number.isNaN(n) || n < 0 || n > 100) continue;
                const r = el.getBoundingClientRect();
                if (r.width < 2 || r.height < 2) continue;
                if (best === null || n > best) best = n;
              }
              // 正文兜底（避免 class 哈希变化）
              if (best === null) {
                const body = document.body ? document.body.innerText : '';
                const all = [...body.matchAll(/(\\d{1,3})\\s*%\\s*造梦中/g)];
                for (const m of all) {
                  const n = parseInt(m[1], 10);
                  if (!Number.isNaN(n)) best = best === null ? n : Math.max(best, n);
                }
              }
              return best;
            }"""
        )
    except Exception:  # noqa: BLE001
        return None


def _wait_result_and_download(
    page,
    context,
    dest: Path,
    *,
    timeout_s: float,
    ignore_srcs: set[str] | None = None,
    prompt_hint: str = "",
    expect_duration_sec: int | None = None,
    log: LogFn = None,
    progress: ProgressFn = None,
) -> None:
    """提交后轮询新结果 video 并落盘（避免误下历史成片）。"""
    ignore = set(ignore_srcs or ())
    deadline = time.monotonic() + timeout_s
    baseline_done = False
    appeared_at: float | None = None
    submit_at = time.monotonic()
    last_progress: int | None = None

    while time.monotonic() < deadline:
        page = _alive_page(context, page)
        if page is None:
            raise JimengWebError("浏览器已关闭（可能被额度检查抢占 profile）；请重试")
        try:
            dismiss_modals(page, rounds=1)

            pct = _read_dream_progress(page)
            if pct is not None and pct != last_progress:
                if progress:
                    try:
                        progress(pct)
                    except Exception:  # noqa: BLE001
                        pass
                last_progress = pct

            # 跳到结果页后，先把已有 video 全部加入忽略，再等新片
            if not baseline_done and (time.monotonic() - submit_at) >= 2.5:
                existing = set(_video_srcs(page))
                if existing:
                    ignore |= existing
                    log_line(log, f"  … 忽略页面已有 {len(existing)} 个历史 video")
                baseline_done = True

            srcs = [s for s in _video_srcs(page) if s not in ignore]
            ready_ui = False
            prompt_hit = False
            try:
                ready_ui = page.get_by_text("再次生成", exact=False).count() > 0
            except Exception:  # noqa: BLE001
                pass
            if prompt_hint:
                hint = prompt_hint.strip()[:40]
                try:
                    prompt_hit = hint and hint in (page.locator("body").inner_text(timeout=2000) or "")
                except Exception:  # noqa: BLE001
                    prompt_hit = False

            # 仍在生成中则继续等（含「N%造梦中」）
            busy = pct is not None and pct < 100
            if not busy:
                try:
                    body = page.locator("body").inner_text(timeout=1500) or ""
                    busy = any(
                        k in body
                        for k in ("造梦中", "生成中", "排队中", "正在生成", "预计等待")
                    )
                except Exception:  # noqa: BLE001
                    pass

            if srcs and not busy:
                if appeared_at is None:
                    appeared_at = time.monotonic()
                    log_line(log, "  … 检测到新结果 video，准备下载")
                stable = (time.monotonic() - appeared_at) >= 2.0
                ok_to_save = stable and (ready_ui or prompt_hit or not prompt_hint)
                if ok_to_save:
                    for src in sorted(srcs, key=len, reverse=True):
                        if _save_url(context, src, dest, log=log):
                            if expect_duration_sec and dest.is_file():
                                min_bytes = max(800_000, expect_duration_sec * 200_000)
                                if dest.stat().st_size < min_bytes:
                                    log_line(
                                        log,
                                        f"  … 文件偏小（{dest.stat().st_size} bytes），可能非目标结果，继续等",
                                    )
                                    ignore.add(src)
                                    dest.unlink(missing_ok=True)
                                    appeared_at = None
                                    continue
                            if progress:
                                try:
                                    progress(100)
                                except Exception:  # noqa: BLE001
                                    pass
                            return

            for label in ("下载", "Download", "导出"):
                try:
                    btn = page.get_by_role("button", name=label).first
                    if btn.count() == 0 or not btn.is_visible(timeout=300):
                        continue
                    with page.expect_download(timeout=60_000) as dl_info:
                        btn.click(timeout=5000)
                    dl_info.value.save_as(str(dest))
                    log_line(log, f"  ✓ 已通过「{label}」下载")
                    if progress:
                        try:
                            progress(100)
                        except Exception:  # noqa: BLE001
                            pass
                    return
                except Exception:  # noqa: BLE001
                    continue

            page.wait_for_timeout(2500)
        except JimengWebError:
            raise
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "has been closed" in msg or "Target page" in msg:
                page = _alive_page(context, page)
                if page is None:
                    raise JimengWebError(
                        "浏览器已关闭（额度面板/status 勿在生成时抢同一 profile）"
                    ) from exc
                continue
            raise

    snap = None
    try:
        page = _alive_page(context, page)
        if page is not None:
            snap = save_debug(page, DEBUG_DIR, "gen_timeout")
    except Exception:  # noqa: BLE001
        pass
    raise JimengWebError(
        f"生成超时（{int(timeout_s)}s）：页面上未拿到可下载视频"
        + (f"；截图 {snap}" if snap else "")
    )


class JimengWebClient:
    poll_timeout_sec = 900

    def available(self) -> tuple[bool, str]:
        if not PROFILE_DIR.is_dir():
            return False, "未登录；请运行 python -m jimeng_web login"

        # 生成中占用 profile：不要再开第二个 Chromium
        with _profile_lock(blocking=False) as got:
            if not got:
                if LOGIN_MARK.is_file():
                    return True, "jimeng profile 使用中（视为已登录）"
                return True, "jimeng profile 使用中"

            if LOGIN_MARK.is_file():
                # 轻量信任近期登录标记；避免频繁有头/无头打架
                try:
                    age = time.time() - LOGIN_MARK.stat().st_mtime
                    if age < 6 * 3600:
                        return True, "jimeng profile 已登录"
                except OSError:
                    pass

            try:
                with browser_context(profile_dir=PROFILE_DIR, headless=True) as context:
                    page = context.new_page()
                    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=60_000)
                    page.wait_for_timeout(1500)
                    dismiss_modals(page, rounds=3)
                    if _dom_logged_in(page):
                        _mark_logged_in(True)
                        return True, "jimeng profile 已登录"
                    _mark_logged_in(False)
                    return False, "即梦未登录或 session 失效；请 python -m jimeng_web login"
            except Exception as exc:  # noqa: BLE001
                if "ProcessSingleton" in str(exc) or "profile is already in use" in str(exc):
                    return True, "jimeng profile 使用中（视为已登录）"
                return False, f"检查登录失败：{exc}"

    def login_status(self, *, log: LogFn = None) -> LoginStatus:
        del log
        ok, msg = self.available()
        return LoginStatus(is_logged_in=ok, detail=msg)

    def interactive_login(self, *, log: LogFn = None, timeout_s: float = 300.0) -> LoginStatus:
        """有头打开首页，等侧栏「登录」消失（扫码/点登录请在弹出的浏览器完成）。"""
        log_line(log, f"[登录] 打开 {CANVAS_URL} …")
        try:
            with _profile_lock(blocking=True):
                with browser_context(profile_dir=PROFILE_DIR, headless=False) as context:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=60_000)
                    page.wait_for_timeout(1500)
                    dismiss_modals(page, log=log)
                    try:
                        login_item = page.locator(
                            ".dreamina-side-menu-container, [class*='sideMenu']"
                        ).get_by_text("登录", exact=True).first
                        if login_item.count() > 0 and login_item.is_visible(timeout=800):
                            login_item.click(timeout=3000)
                            page.wait_for_timeout(800)
                            dismiss_modals(page, log=log)
                    except Exception:  # noqa: BLE001
                        pass
                    deadline = time.monotonic() + timeout_s
                    while time.monotonic() < deadline:
                        dismiss_modals(page, rounds=1)
                        if _dom_logged_in(page):
                            _mark_logged_in(True)
                            log_line(log, "  ✓ 已检测到登录态（侧栏无「登录」）")
                            return LoginStatus(is_logged_in=True, detail="已登录")
                        page.wait_for_timeout(1500)
            raise JimengWebError(f"登录超时（{int(timeout_s)}s）")
        except JimengWebError:
            raise
        except BrowserError as exc:
            raise JimengWebError(str(exc)) from exc

    def generate_i2v(
        self,
        image_path: Path,
        prompt: str,
        out_path: Path,
        *,
        duration_sec: int | None = None,
        aspect_ratio: str = DEFAULT_ASPECT,
        model: str | None = None,
        ref_mode: str | None = None,
        resolution: str = DEFAULT_RESOLUTION,
        log: LogFn = None,
        progress: ProgressFn = None,
    ) -> Path:
        ok, reason = self.available()
        if not ok:
            raise JimengWebError(reason)

        video_model = (model or DEFAULT_VIDEO_MODEL).strip()
        reference = (ref_mode or DEFAULT_REF_MODE).strip()
        seconds = int(duration_sec if duration_sec is not None else DEFAULT_DURATION_SEC)

        staged, tmp = stage_media(image_path, log=log, prefix="jimeng_")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        part = out_path.with_suffix(out_path.suffix + ".part")

        try:
            with _profile_lock(blocking=True):
                with browser_context(
                    profile_dir=PROFILE_DIR, env_key="JIMENG_HEADLESS"
                ) as context:
                    page = context.new_page()
                    log_line(log, "[Jimeng] 打开视频生成页 …")
                    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=90_000)
                    page.wait_for_timeout(2000)
                    dismiss_modals(page, log=log)

                    if not _dom_logged_in(page):
                        snap = save_debug(page, DEBUG_DIR, "not_logged_in")
                        raise JimengWebError(
                            "即梦未登录；请先 python -m jimeng_web login"
                            + (f"（截图 {snap}）" if snap else "")
                        )
                    _mark_logged_in(True)

                    _ensure_video_mode(page, log=log)
                    dismiss_modals(page, rounds=2, log=log)
                    _ensure_video_model(page, model=video_model, log=log)
                    dismiss_modals(page, rounds=2, log=log)
                    _ensure_ref_mode(page, mode=reference, log=log)
                    _ensure_aspect_resolution(
                        page,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                        log=log,
                    )
                    _ensure_duration(page, duration_sec=seconds, log=log)
                    dismiss_modals(page, rounds=1, log=log)

                    log_line(log, f"[Jimeng] 上传参考图 {Path(staged).name}（{reference}）…")
                    if not _upload_loop_frames(
                        page, staged, ref_mode=reference, log=log
                    ):
                        snap = save_debug(page, DEBUG_DIR, "upload_fail")
                        raise JimengWebError(
                            "上传图片失败（未找到 file input / 上传按钮）"
                            + (f"；截图 {snap}" if snap else "")
                        )
                    page.wait_for_timeout(1500)
                    dismiss_modals(page, rounds=2, log=log)

                    if prompt.strip():
                        if not fill_prompt_text(page, prompt.strip(), log=log):
                            log_line(log, "  … 未找到 prompt 输入框，继续尝试生成")

                    before_srcs = set(_video_srcs(page))
                    log_line(
                        log,
                        f"[Jimeng] 提交生成（{video_model} / {reference} / "
                        f"{aspect_ratio} {resolution} / {seconds}s）…",
                    )
                    if not click_generate(page, log=log):
                        snap = save_debug(page, DEBUG_DIR, "no_generate_btn")
                        raise JimengWebError(
                            "未找到生成按钮"
                            + (f"；截图 {snap}" if snap else "")
                        )

                    log_line(log, "[Jimeng] 等待结果并下载 …")
                    _wait_result_and_download(
                        page,
                        context,
                        part,
                        timeout_s=float(self.poll_timeout_sec),
                        ignore_srcs=before_srcs,
                        prompt_hint=prompt.strip(),
                        expect_duration_sec=seconds,
                        log=log,
                        progress=progress,
                    )

                    if not part.is_file() or part.stat().st_size < 1024:
                        raise JimengWebError("下载结果为空")
                    os.replace(part, out_path)
                    log_line(
                        log,
                        f"[Jimeng] 已保存 {out_path.name}（{out_path.stat().st_size} bytes）",
                    )
                    return out_path
        except JimengWebError:
            part.unlink(missing_ok=True)
            raise
        except BrowserError as exc:
            part.unlink(missing_ok=True)
            raise JimengWebError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            part.unlink(missing_ok=True)
            raise JimengWebError(str(exc)) from exc
        finally:
            cleanup_stage(tmp)
