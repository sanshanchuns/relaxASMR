"""即梦 Agent（type=agentic）Playwright 对话驱动。"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from shared.browser import (
    browser_context,
    cleanup_stage,
    dismiss_modals,
    log_line,
    save_debug,
    stage_media,
    upload_file,
)

from .client import DEBUG_DIR, PROFILE_DIR, JimengWebError, _profile_lock

LogFn = Callable[[str], None] | None

AGENTIC_URL = os.environ.get(
    "JIMENG_AGENTIC_URL",
    "https://jimeng.jianying.com/ai-tool/generate?type=agentic&workspace=18641405181708",
)

# 可见输入区（排除 prompt-editor-sizer 里 visibility:hidden 的影子编辑器）
_EDITOR_SEL = '[class*="prompt-editor-sgtsCG"] .tiptap.ProseMirror'
_EDITOR_FALLBACKS = (
    _EDITOR_SEL,
    '[class*="agentic-generator-prompt-editor"] .tiptap.ProseMirror',
    '.tiptap.ProseMirror[role="textbox"]',
)

_JSON_BLOCK = re.compile(r"\{[^{}]*\"subject\"[^{}]*\}", re.DOTALL)
_JSON_BLOCK_LOOSE = re.compile(
    r"\{(?:[^{}]|\{[^{}]*\})*\"subject\"(?:[^{}]|\{[^{}]*\})*\}",
    re.DOTALL,
)


def _neutralize_overlays(page: Any, *, log: LogFn = None) -> None:
    """高 z-index 全屏层会拦截点击（探测到 z=999999 空 class 遮罩）。"""
    n = page.evaluate(
        """() => {
          let n = 0;
          for (const el of [...document.querySelectorAll('div')]) {
            const st = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            const z = Number(st.zIndex);
            if (!(z >= 99999 && r.width > 400 && r.height > 400)) continue;
            el.style.pointerEvents = 'none';
            n += 1;
          }
          return n;
        }"""
    )
    if n:
        log_line(log, f"  … 已放开 {n} 个高 z-index 遮罩 pointer-events")


def _ensure_viewport(page: Any) -> None:
    if page.viewport_size is None:
        page.set_viewport_size({"width": 1440, "height": 1100})


def _locate_editor(page: Any) -> Any:
    for sel in _EDITOR_FALLBACKS:
        loc = page.locator(sel)
        try:
            n = loc.count()
        except Exception:  # noqa: BLE001
            continue
        for i in range(n):
            el = loc.nth(i)
            try:
                if not el.is_visible(timeout=400):
                    continue
                box = el.bounding_box()
                if not box or box["height"] < 40:
                    continue
                return el
            except Exception:  # noqa: BLE001
                continue
    return None


def _fill_chat_input(page: Any, text: str, *, log: LogFn = None) -> bool:
    editor = _locate_editor(page)
    if editor is None:
        return False
    try:
        editor.scroll_into_view_if_needed(timeout=5000)
    except Exception:  # noqa: BLE001
        pass
    try:
        editor.click(timeout=5000, force=True)
    except Exception:  # noqa: BLE001
        try:
            editor.evaluate("el => el.focus()")
        except Exception:  # noqa: BLE001
            return False
    page.keyboard.press("Control+A")
    page.wait_for_timeout(80)
    # TipTap 对 fill() 不稳定；insert_text 更稳
    page.keyboard.insert_text(text)
    page.wait_for_timeout(400)
    log_line(log, "  ✓ Agent TipTap 输入框已填写")
    return True


def _click_send(page: Any, *, log: LogFn = None) -> bool:
    """点 Agent 底栏圆形提交（可见、非 disabled；避开 hidden collapsed 视频钮）。"""
    for _ in range(25):
        clicked = page.evaluate(
            """() => {
              const editor = document.querySelector(
                '[class*="prompt-editor-sgtsCG"] .tiptap.ProseMirror'
              ) || document.querySelector('.tiptap.ProseMirror[role="textbox"]');
              if (!editor) return {ok: false, reason: 'no-editor'};
              const er = editor.getBoundingClientRect();
              const btns = [...document.querySelectorAll('button')].filter((b) => {
                const c = b.className || '';
                if (!c.includes('submit-button') && !c.includes('submit-butt')) return false;
                if (b.disabled || c.includes('lv-btn-disabled')) return false;
                const st = getComputedStyle(b);
                if (st.visibility === 'hidden' || st.display === 'none') return false;
                if (c.includes('collapsed-submit')) return false;
                const r = b.getBoundingClientRect();
                if (r.width < 28 || r.height < 28) return false;
                // 靠近底部编辑器
                return r.top >= er.top - 40;
              });
              if (!btns.length) return {ok: false, reason: 'no-btn'};
              btns.sort(
                (a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top
              );
              const b = btns[btns.length - 1];
              b.click();
              return {ok: true, top: Math.round(b.getBoundingClientRect().top)};
            }"""
        )
        if clicked and clicked.get("ok"):
            log_line(log, f"  ✓ 已点击 Agent 发送（top={clicked.get('top')}）")
            return True
        page.wait_for_timeout(200)
    # 兜底：Enter（部分会话可发）
    try:
        page.keyboard.press("Enter")
        log_line(log, "  … 发送钮未就绪，已按 Enter")
        return True
    except Exception:  # noqa: BLE001
        return False


def _editor_plain_text(page: Any) -> str:
    editor = _locate_editor(page)
    if editor is None:
        return ""
    try:
        return (editor.inner_text(timeout=1500) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


_BUSY_MARKERS = (
    "认真思考中",
    "生成中...",
    "生成中…",
    "思考中",
    "正在生成",
    "回答中",
    "创作中",
    "正在回答",
)


def _body_is_busy(body: str) -> bool:
    return any(m in (body or "") for m in _BUSY_MARKERS)


def _reply_fingerprint(page: Any) -> dict[str, Any]:
    body = ""
    try:
        body = page.inner_text("body") or ""
    except Exception:  # noqa: BLE001
        body = ""
    jsons = _extract_json_candidates(body)
    texts = _assistant_texts(page)
    return {
        "done": body.count("已完成"),
        "jsons": set(jsons),
        "text_heads": {t[:160] for t in texts if t},
        "body_len": len(body),
    }


def _ensure_message_sent(page: Any, prompt: str, *, log: LogFn = None) -> None:
    """确认发送已生效：输入框不再以本轮 prompt 开头；否则重试点击发送。"""
    head = (prompt or "").strip()[:50]
    for attempt in range(5):
        page.wait_for_timeout(500 if attempt == 0 else 700)
        dismiss_modals(page, rounds=1, log=None)
        _neutralize_overlays(page, log=None)
        et = _editor_plain_text(page)
        still_draft = bool(et) and bool(head) and (
            et.startswith(head) or head in et[: max(120, len(head) + 40)]
        )
        if not still_draft:
            log_line(log, "  ✓ 输入框已发出（不再保留本轮草稿）")
            return
        if attempt >= 4:
            break
        log_line(log, f"  … 输入框仍有草稿，重试发送（{attempt + 1}/4）")
        try:
            editor = _locate_editor(page)
            if editor is not None:
                editor.click(timeout=2000, force=True)
        except Exception:  # noqa: BLE001
            pass
        if not _click_send(page, log=log):
            try:
                page.keyboard.press("Enter")
            except Exception:  # noqa: BLE001
                pass
    log_line(log, "  … 警告：输入框可能仍有内容，继续等待回复")


def _click_expand_if_any(page: Any) -> None:
    try:
        for label in ("展开", "Expand"):
            btns = page.get_by_text(label, exact=True)
            n = min(btns.count(), 6)
            for i in range(n):
                b = btns.nth(i)
                try:
                    if b.is_visible(timeout=200):
                        b.click(timeout=1000, force=True)
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        pass


def _extract_json_candidates(text: str) -> list[str]:
    out: list[str] = []
    for rx in (_JSON_BLOCK_LOOSE, _JSON_BLOCK):
        for m in rx.finditer(text or ""):
            blob = m.group(0).strip()
            if blob and blob not in out:
                out.append(blob)
    return out


def _assistant_texts(page: Any) -> list[str]:
    texts: list[str] = []
    try:
        raw = page.evaluate(
            """() => {
              const sels = [
                '[class*="markdown"]',
                '[class*="message"]',
                '[class*="answer"]',
                '[class*="reply"]',
                '[class*="bubble"]',
                '[class*="assistant"]',
                'article',
              ];
              const nodes = [];
              for (const sel of sels) {
                nodes.push(...document.querySelectorAll(sel));
              }
              const out = [];
              const seen = new Set();
              for (const n of nodes) {
                const t = (n.innerText || '').trim();
                if (t.length < 40 || seen.has(t)) continue;
                seen.add(t);
                out.push(t);
              }
              return out;
            }"""
        )
        texts.extend(raw or [])
    except Exception:  # noqa: BLE001
        pass
    return texts


def _wait_new_reply(
    page: Any,
    *,
    prompt: str,
    timeout_s: float,
    log: LogFn = None,
    baseline: dict[str, Any] | None = None,
) -> str:
    """等本轮新回复：相对 baseline 出现新 JSON/文本，或忙碌结束后抽出结果。"""
    deadline = time.monotonic() + max(30.0, float(timeout_s))
    started = time.monotonic()
    last_json = ""
    last_json_stable = 0
    saw_busy = False
    prompt_head = (prompt or "").strip()[:80]
    base = baseline or _reply_fingerprint(page)
    base_jsons: set[str] = set(base.get("jsons") or ())
    base_done = int(base.get("done") or 0)
    base_heads: set[str] = set(base.get("text_heads") or ())
    last_beat = 0.0

    while time.monotonic() < deadline:
        elapsed = time.monotonic() - started
        if elapsed - last_beat >= 15.0:
            last_beat = elapsed
            log_line(
                log,
                f"  … 等待 Agent 回复（已等 {int(elapsed)}s / {int(timeout_s)}s"
                + (" · 生成中" if saw_busy else "")
                + "）",
            )

        _click_expand_if_any(page)
        body = ""
        try:
            body = page.inner_text("body")
        except Exception:  # noqa: BLE001
            pass

        busy = _body_is_busy(body)
        if busy:
            if not saw_busy:
                log_line(log, "  … 已开始生成/思考")
            saw_busy = True

        done_now = body.count("已完成")
        candidates = _extract_json_candidates(body)
        # 优先本轮新增 JSON；排除几乎等于用户原文的块
        fresh = [b for b in candidates if b not in base_jsons]
        scan = fresh or ([] if base_jsons else candidates)
        for blob in scan:
            if prompt_head and prompt_head[:40] in blob and len(blob) < len(prompt) + 40:
                continue
            if blob.count("[") > blob.count("]"):
                continue
            if '"subject"' not in blob or len(blob) <= 60:
                continue
            if blob != last_json:
                last_json = blob
                last_json_stable = 0
            else:
                last_json_stable += 1
            complete = '"constraints"' in blob and blob.rstrip().endswith("}")
            # 新 JSON 且已稳定两拍，或忙碌结束后收尾
            if complete and (
                (fresh and last_json_stable >= 1 and not busy)
                or (saw_busy and not busy)
                or (fresh and last_json_stable >= 2)
            ):
                if busy:
                    page.wait_for_timeout(800)
                    continue
                page.wait_for_timeout(900)
                body2 = page.inner_text("body")
                better = _extract_json_candidates(body2)
                for b in reversed(better):
                    if b in base_jsons and fresh:
                        continue
                    if '"subject"' in b and '"constraints"' in b and len(b) >= len(last_json):
                        log_line(log, f"  ✓ 收到 Agent JSON（{len(b)} 字）")
                        return b
                log_line(log, f"  ✓ 收到 Agent JSON（{len(last_json)} 字）")
                return last_json

        if saw_busy and not busy and last_json and last_json not in base_jsons:
            log_line(log, f"  ✓ 思考结束，返回 JSON（{len(last_json)} 字）")
            return last_json

        # 非 JSON：取相对 baseline 的新助手长文本
        if (saw_busy and not busy) or done_now > base_done:
            for t in _assistant_texts(page):
                head = t[:160]
                if head in base_heads:
                    continue
                if prompt_head and prompt_head[:50] in t and len(t) < len(prompt) + 100:
                    continue
                if len(t) > 120 and ("subject" in t or "主体" in t or "rain_mode" in t or "【" in t):
                    log_line(log, f"  ✓ 收到 Agent 文本（{len(t)} 字）")
                    return t

        page.wait_for_timeout(1000)

    if last_json and last_json not in base_jsons:
        log_line(log, f"  … 超时，返回本轮末次 JSON（{len(last_json)} 字）")
        return last_json
    try:
        body = page.inner_text("body")
        cands = [c for c in _extract_json_candidates(body) if c not in base_jsons]
        if not cands:
            cands = _extract_json_candidates(body)
        if cands:
            best = max(cands, key=len)
            log_line(log, f"  … 超时，回退最长 JSON（{len(best)} 字）")
            return best
    except Exception:  # noqa: BLE001
        pass
    raise JimengWebError(f"Agent 回复超时（{int(timeout_s)}s）")


def _try_new_chat(page: Any, *, log: LogFn = None) -> None:
    """侧栏「新对话」常不可见；能点则点，失败忽略。"""
    try:
        loc = page.locator(".new-conversation-text-oZHUxf, [class*='new-conversation']").first
        if loc.count() and loc.is_visible(timeout=400):
            loc.click(timeout=2000, force=True)
            page.wait_for_timeout(800)
            log_line(log, "  ✓ 已点「新对话」")
            return
    except Exception:  # noqa: BLE001
        pass
    for label in ("新对话", "新建对话"):
        try:
            btn = page.get_by_text(label, exact=True).first
            if btn.count() and btn.is_visible(timeout=300):
                btn.click(timeout=2000, force=True)
                page.wait_for_timeout(800)
                log_line(log, f"  ✓ 已点「{label}」")
                return
        except Exception:  # noqa: BLE001
            continue


def _upload_ref(page: Any, abs_path: str, *, log: LogFn = None) -> bool:
    """点 Agent 底栏参考图「+」(reference-upload) 上传；失败再直写 file input。"""

    def _has_ref_thumb() -> bool:
        try:
            return bool(
                page.evaluate(
                    """() => {
                      const imgs = [...document.querySelectorAll(
                        '[class*="reference"] img, [class*="references"] img'
                      )];
                      return imgs.some((img) => {
                        const src = img.src || '';
                        const r = img.getBoundingClientRect();
                        return (src.startsWith('blob:') || src.includes('byteimg') || src.includes('dreamina'))
                          && r.width >= 24 && r.height >= 24;
                      });
                    }"""
                )
            )
        except Exception:  # noqa: BLE001
            return False

    # 1) 点 reference-upload → file chooser（实机最稳）
    try:
        ref = page.locator('[class*="reference-upload"]').first
        if ref.count() > 0:
            with page.expect_file_chooser(timeout=10_000) as fc_info:
                ref.click(timeout=5000, force=True)
            fc_info.value.set_files(abs_path)
            page.wait_for_timeout(1200)
            if _has_ref_thumb():
                log_line(log, "  ✓ 已通过 reference-upload 上传参考图")
                return True
            log_line(log, "  … reference-upload 已选文件，等待缩略图…")
            page.wait_for_timeout(2000)
            if _has_ref_thumb():
                log_line(log, "  ✓ 参考图缩略图已出现")
                return True
    except Exception as exc:  # noqa: BLE001
        log_line(log, f"  … reference-upload 失败：{exc}")

    # 2) 直写隐藏 file input
    for sel in (
        "input.file-input-SleVHY",
        'input[type="file"][class*="file-input"]',
        'input[type="file"]',
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            loc.set_input_files(abs_path, timeout=10_000)
            page.wait_for_timeout(1500)
            log_line(log, f"  ✓ 已写入 file input（{sel}）")
            return True
        except Exception:  # noqa: BLE001
            continue

    # 3) 通用 upload_file 兜底
    if upload_file(page, abs_path, log=log):
        page.wait_for_timeout(1000)
        return True
    return False


def _load_i2v_skill_payload() -> dict[str, str]:
    """技能三字段；优先读仓库 instructions/jimeng_skills。"""
    try:
        import sys

        root = str(Path(__file__).resolve().parents[2])
        if root not in sys.path:
            sys.path.insert(0, root)
        from scripts.aigc_lab.agent_i2v_rules import load_jimeng_i2v_skill

        return load_jimeng_i2v_skill()
    except Exception:  # noqa: BLE001
        return {
            "name": "雨ASMR图生",
            "description": "雨ASMR图生六槽：全能参考·同系列异构",
            "content": "观察附图，只输出 rain_mode+六槽 JSON。",
        }


def _skill_already_active(page: Any, name: str) -> bool:
    try:
        body = page.inner_text("body") or ""
    except Exception:  # noqa: BLE001
        return False
    return bool(name) and name in body and ("使用技能" in body or "技能" in body)


def _click_text_button(page: Any, *labels: str, timeout_ms: int = 2500) -> bool:
    for label in labels:
        try:
            loc = page.get_by_text(label, exact=True).first
            if loc.count() and loc.is_visible(timeout=400):
                loc.click(timeout=timeout_ms, force=True)
                page.wait_for_timeout(400)
                return True
        except Exception:  # noqa: BLE001
            continue
        try:
            loc = page.locator(f'button:has-text("{label}")').first
            if loc.count() and loc.is_visible(timeout=400):
                loc.click(timeout=timeout_ms, force=True)
                page.wait_for_timeout(400)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _fill_by_placeholder(page: Any, placeholder_substr: str, value: str) -> bool:
    try:
        loc = page.locator(f'[placeholder*="{placeholder_substr}"]').first
        if loc.count() == 0:
            return False
        loc.click(timeout=2000, force=True)
        loc.fill(value, timeout=5000)
        page.wait_for_timeout(200)
        return True
    except Exception:  # noqa: BLE001
        return False


def _fill_skill_content_editor(page: Any, content: str) -> bool:
    """技能内容多为富文本；优先 placeholder，再试可见 contenteditable。"""
    if _fill_by_placeholder(page, "技能内容", content):
        return True
    if _fill_by_placeholder(page, "具体的技能内容", content):
        return True
    try:
        eds = page.locator('[contenteditable="true"]')
        n = eds.count()
        # 通常最后一个大编辑器是技能内容
        for i in range(n - 1, -1, -1):
            el = eds.nth(i)
            try:
                if not el.is_visible(timeout=300):
                    continue
                box = el.bounding_box()
                if not box or box["height"] < 80:
                    continue
                el.click(timeout=2000, force=True)
                page.keyboard.press("Control+A")
                page.keyboard.insert_text(content)
                page.wait_for_timeout(300)
                return True
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return False


def _click_go_use_skill(page: Any, *, log: LogFn = None, retries: int = 8) -> bool:
    """点详情页右上角「去使用」（新建后必点，否则技能未真正挂到对话）。"""
    for i in range(retries):
        # 优先白色主按钮
        try:
            btn = page.locator('button:has-text("去使用")').first
            if btn.count() and btn.is_visible(timeout=500):
                btn.click(timeout=3000, force=True)
                page.wait_for_timeout(700)
                log_line(log, "  ✓ 已点「去使用」")
                return True
        except Exception:  # noqa: BLE001
            pass
        if _click_text_button(page, "去使用", timeout_ms=3000):
            log_line(log, "  ✓ 已点「去使用」")
            return True
        page.wait_for_timeout(400 + i * 100)
    log_line(log, "  … 未点到「去使用」")
    return False


def _select_skill_in_panel(page: Any, name: str, *, log: LogFn = None) -> bool:
    """在技能管理/搜索面板中选中指定技能（侧栏「个人」列表）。"""
    try:
        # 优先点「个人」分组下的同名项
        hit = page.locator(f'text="{name}"').first
        if hit.count() and hit.is_visible(timeout=800):
            hit.click(timeout=2500, force=True)
            page.wait_for_timeout(500)
            log_line(log, f"  ✓ 已选中技能「{name}」")
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        hit = page.get_by_text(name, exact=True).first
        if hit.count() and hit.is_visible(timeout=800):
            hit.click(timeout=2500, force=True)
            page.wait_for_timeout(500)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _create_custom_skill(page: Any, skill: dict[str, str], *, log: LogFn = None) -> bool:
    name = skill.get("name") or "雨ASMR图生"
    desc = skill.get("description") or ""
    content = skill.get("content") or ""
    if not _click_text_button(page, "新建技能", "+ 新建技能", "+新建技能"):
        if not _click_text_button(page, "管理技能"):
            return False
        if not _click_text_button(page, "新建技能", "+ 新建技能", "+新建技能"):
            return False
    page.wait_for_timeout(600)
    ok_name = _fill_by_placeholder(page, "技能名称", name) or _fill_by_placeholder(
        page, "请输入技能名称", name
    )
    ok_desc = _fill_by_placeholder(page, "技能描述", desc) or _fill_by_placeholder(
        page, "清晰、明确的技能描述", desc
    )
    ok_body = _fill_skill_content_editor(page, content)
    if not (ok_name and ok_desc and ok_body):
        log_line(
            log,
            f"  … 新建技能表单未填全 name={ok_name} desc={ok_desc} body={ok_body}",
        )
        return False
    if not _click_text_button(page, "保存", "创建", "完成", "确认"):
        log_line(log, "  … 未找到保存按钮，继续找「去使用」")
    page.wait_for_timeout(1000)
    # 保存后进入详情页：必须点「去使用」才挂到对话
    if _click_go_use_skill(page, log=log):
        log_line(log, f"  ✓ 已新建并「去使用」技能「{name}」")
        return True
    # 若仍停在列表：再点一次该技能详情再去使用
    if _select_skill_in_panel(page, name, log=log) and _click_go_use_skill(page, log=log):
        log_line(log, f"  ✓ 已新建并「去使用」技能「{name}」")
        return True
    log_line(log, f"  … 新建技能「{name}」后未能点「去使用」")
    return False


def ensure_i2v_skill(page: Any, *, log: LogFn = None, force: bool = False) -> bool:
    """打开「使用技能」，选用或新建「雨ASMR图生」，并以「去使用」挂到对话。"""
    del force
    skill = _load_i2v_skill_payload()
    name = skill["name"]
    dismiss_modals(page, rounds=1, log=None)
    _neutralize_overlays(page, log=None)
    if not _click_text_button(page, "使用技能"):
        log_line(log, "  … 未找到「使用技能」按钮，跳过技能挂载")
        return False
    page.wait_for_timeout(500)

    # 搜索已有技能（个人）
    searched = _fill_by_placeholder(page, "搜索技能", name)
    if searched:
        page.wait_for_timeout(500)
    if _select_skill_in_panel(page, name, log=log):
        if _click_go_use_skill(page, log=log):
            log_line(log, f"  ✓ 已选用并「去使用」技能「{name}」")
            return True
        log_line(log, "  … 已选中技能但未点到「去使用」")

    log_line(log, f"  … 未找到技能「{name}」，尝试新建…")
    if _create_custom_skill(page, skill, log=log):
        return True
    try:
        page.keyboard.press("Escape")
    except Exception:  # noqa: BLE001
        pass
    log_line(log, "  … 技能挂载失败，将仅依赖短指令（无规则全文）")
    return False


def _run_agentic_turn(
    page: Any,
    prompt: str,
    *,
    images: Sequence[Path | str] | None = None,
    new_chat: bool = False,
    timeout_s: float = 180.0,
    log: LogFn = None,
    upload_images: bool = True,
    ensure_skill: bool = False,
) -> str:
    """在已打开的 Agent 页上发送一轮消息并等待回复。"""
    text = (prompt or "").strip()
    if not text:
        raise JimengWebError("Agent prompt 为空")

    staged: list[tuple[str, Path | None]] = []
    try:
        dismiss_modals(page, rounds=2, log=log)
        _neutralize_overlays(page, log=log)

        if new_chat:
            _try_new_chat(page, log=log)
            _neutralize_overlays(page, log=log)

        if ensure_skill:
            ensure_i2v_skill(page, log=log)
            dismiss_modals(page, rounds=1, log=None)
            _neutralize_overlays(page, log=None)

        if upload_images:
            for img in images or []:
                abs_path, tmp = stage_media(img, log=log, prefix="jimeng_agent_")
                staged.append((abs_path, tmp))
                if not _upload_ref(page, abs_path, log=log):
                    save_debug(page, DEBUG_DIR, "agentic_upload_fail")
                    raise JimengWebError(f"无法上传参考图: {img}")

        ready = False
        for _ in range(20):
            if _locate_editor(page) is not None:
                ready = True
                break
            page.wait_for_timeout(300)
        if not ready:
            save_debug(page, DEBUG_DIR, "agentic_no_editor")
            raise JimengWebError("找不到 Agent 输入框")

        if not _fill_chat_input(page, text, log=log):
            save_debug(page, DEBUG_DIR, "agentic_input_fail")
            raise JimengWebError("找不到 Agent 输入框")
        # 长 prompt 写入 TipTap 需要一点时间，确认已进框再发
        for _ in range(15):
            et = _editor_plain_text(page)
            if et and (text[:40] in et or len(et) >= min(80, len(text) // 2)):
                break
            page.wait_for_timeout(200)
        else:
            log_line(log, "  … 警告：输入框内容可能未写完，仍尝试发送")

        baseline = _reply_fingerprint(page)
        if not _click_send(page, log=log):
            save_debug(page, DEBUG_DIR, "agentic_send_fail")
            raise JimengWebError("无法发送 Agent 消息")
        _ensure_message_sent(page, text, log=log)

        return _wait_new_reply(
            page,
            prompt=text,
            timeout_s=timeout_s,
            log=log,
            baseline=baseline,
        )
    finally:
        for _, tmp in staged:
            cleanup_stage(tmp)


class JimengAgentSession:
    """复用同一 Chromium profile / Agent 页，避免三轮审核反复开关浏览器。"""

    def __init__(
        self,
        *,
        url: str | None = None,
        timeout_s: float = 180.0,
        log: LogFn = None,
    ) -> None:
        self._url = (url or AGENTIC_URL).strip()
        self._timeout_s = timeout_s
        self._log = log
        self._lock_cm: Any = None
        self._browser_cm: Any = None
        self._context: Any = None
        self._page: Any = None
        self._turn = 0
        self._images_uploaded = False
        self._skill_ready = False

    def __enter__(self) -> JimengAgentSession:
        self._lock_cm = _profile_lock(blocking=True)
        self._lock_cm.__enter__()
        try:
            self._browser_cm = browser_context(
                profile_dir=PROFILE_DIR, headless=None, env_key="JIMENG_HEADLESS"
            )
            self._context = self._browser_cm.__enter__()
            page = self._context.pages[0] if self._context.pages else self._context.new_page()
            _ensure_viewport(page)
            log_line(self._log, f"[Agent] 打开会话 {self._url}")
            page.goto(self._url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2500)
            dismiss_modals(page, rounds=4, log=self._log)
            _neutralize_overlays(page, log=self._log)
            page.wait_for_timeout(500)
            self._page = page
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        del exc_type, exc, tb
        self._page = None
        if self._browser_cm is not None:
            try:
                self._browser_cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._browser_cm = None
            self._context = None
        if self._lock_cm is not None:
            try:
                self._lock_cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._lock_cm = None
        log_line(self._log, "[Agent] 会话已关闭")

    def chat(
        self,
        prompt: str,
        images: Sequence[Path | str] | None = None,
        *,
        new_chat: bool | None = None,
    ) -> str:
        if self._page is None:
            raise JimengWebError("Agent 会话未打开")
        first = self._turn == 0
        do_new = first if new_chat is None else bool(new_chat)
        imgs = list(images) if images else None
        need_upload = bool(imgs) and (do_new or not self._images_uploaded)
        need_skill = do_new or not self._skill_ready
        log_line(
            self._log,
            f"[Agent] 第 {self._turn + 1} 次对话"
            + (" · 新对话" if do_new else " · 复用当前页")
            + (" · 附图" if need_upload else "")
            + (" · 挂载技能" if need_skill else ""),
        )
        try:
            text = _run_agentic_turn(
                self._page,
                prompt,
                images=imgs,
                new_chat=do_new,
                timeout_s=self._timeout_s,
                log=self._log,
                upload_images=need_upload,
                ensure_skill=need_skill,
            )
        except JimengWebError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise JimengWebError(f"Agent 对话失败: {exc}") from exc
        if need_upload:
            self._images_uploaded = True
        if need_skill:
            self._skill_ready = True
        self._turn += 1
        return text


def agentic_chat(
    prompt: str,
    *,
    images: Sequence[Path | str] | None = None,
    url: str | None = None,
    timeout_s: float = 180.0,
    new_chat: bool = True,
    log: LogFn = None,
) -> str:
    """打开即梦 Agent 页，发送一轮 prompt（可选附图），返回助手文本。"""
    with JimengAgentSession(url=url, timeout_s=timeout_s, log=log) as session:
        return session.chat(prompt, images=images, new_chat=new_chat)
