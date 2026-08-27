"""即梦（Jimeng / Dreamina）视频额度条，供 AIGC 实验台使用。"""

from __future__ import annotations

import json
import subprocess
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from scripts.config.paths import find_executable

try:
    from gui.tk_thread import bind_ui_root, schedule_on_main
except ImportError:  # pragma: no cover — 单测 / 脚本直引
    def bind_ui_root(_widget) -> None:  # type: ignore[misc]
        pass

    def schedule_on_main(widget, callback, /, *args, **kwargs):  # type: ignore[misc]
        widget.after(0, lambda: callback(*args, **kwargs))

#: 720P · 5s · Seedance 2.0 Fast VIP 估算（页面读不到消耗积分时的回退）
I2V_720P_5S_CREDIT_ESTIMATE = 40


def estimate_jimeng_video_credits(
    *,
    duration_sec: int = 5,
    resolution: str = "720P",
    model: str = "Seedance 2.0 Fast VIP",
) -> int:
    """按分辨率/时长估算单次视频生成消耗积分。"""
    res = resolution.upper().strip()
    sec = max(1, int(duration_sec))
    per_sec = {"480P": 4, "720P": 8, "1080P": 12}.get(res, 8)
    if "Fast" in (model or ""):
        per_sec = max(4, per_sec - 2)
    return per_sec * sec


#: 即梦 VIP 每月刷新总额（dreamina user_credit 返回的是剩余积分）
JIMENG_MONTHLY_CREDITS = 6160


def fetch_jimeng_credit() -> tuple[int, int]:
    """返回 (剩余, 总额)。未登录或 CLI 不可用时抛异常。"""
    dreamina = find_executable("dreamina")
    if dreamina is None:
        raise RuntimeError("未找到 dreamina CLI（curl -fsSL https://jimeng.jianying.com/cli | bash）")
    proc = subprocess.run(
        [str(dreamina), "user_credit"],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "dreamina user_credit 失败").strip())
    data = json.loads(proc.stdout)
    remaining = int(data.get("total_credit") or 0)
    return remaining, JIMENG_MONTHLY_CREDITS


def _set_bar(bar: ttk.Progressbar, var: tk.StringVar, frac: float | None) -> None:
    if frac is None:
        bar["value"] = 0
        var.set("—")
        return
    clamped = max(0.0, min(1.0, float(frac)))
    bar["value"] = int(round(clamped * 1000))
    var.set(f"{clamped * 100.0:.1f}%")


def _schedule_ui(widget: tk.Widget, fn: Callable[[], None]) -> None:
    schedule_on_main(widget, fn)


class JimengQuotaPanel(ttk.Frame):
    """单行 jimeng_web 额度条。"""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        bind_ui_root(self)
        self._log = log_fn or (lambda _m: None)
        self._token = 0
        self._pct_var = tk.StringVar(value="—")

        row = ttk.Frame(self)
        row.pack(anchor=tk.W, fill=tk.X)
        ttk.Label(row, text="jimeng_web", width=16, anchor=tk.W).pack(side=tk.LEFT)
        self._bar = ttk.Progressbar(
            row, orient=tk.HORIZONTAL, mode="determinate", maximum=1000, value=0
        )
        self._bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        ttk.Label(
            row,
            textvariable=self._pct_var,
            width=7,
            anchor=tk.E,
            font=("Consolas", 9),
        ).pack(side=tk.RIGHT)

        for widget in (self, row, self._bar):
            try:
                widget.configure(cursor="hand2")
            except tk.TclError:
                pass
            widget.bind("<Button-1>", self._on_click_refresh, add="+")

    def _on_click_refresh(self, _event: tk.Event | None = None) -> None:
        self._log("[jimeng-quota] 刷新 jimeng_web 额度")
        self.reload(force=True)

    def reload(self, *, force: bool = False) -> None:
        del force
        self._token += 1
        token = self._token

        def worker() -> None:
            fraction: float | None = None
            error: str | None = None
            try:
                remaining, total = fetch_jimeng_credit()
                fraction = remaining / total if total > 0 else 0.0
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

            def apply() -> None:
                if token != self._token:
                    return
                if error:
                    self._log(f"[jimeng-quota] {error}")
                _set_bar(self._bar, self._pct_var, fraction)

            _schedule_ui(self, apply)

        threading.Thread(target=worker, daemon=True).start()


class JimengCreditBarCompact(ttk.Frame):
    """即梦额度：框内按比例填充，百分比叠在右侧。"""

    _BOX_WIDTH = 148
    _BOX_HEIGHT = 22

    def __init__(
        self,
        parent: tk.Widget,
        *,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        bind_ui_root(self)
        self._log = log_fn or (lambda _m: None)
        self._token = 0
        self._frac: float | None = None
        self._pct_text = "…"
        self._trough = "#3a3a3a"
        self._fill = "#0078d4"
        self._fg = "#e8e8e8"

        self._canvas = tk.Canvas(
            self,
            width=self._BOX_WIDTH,
            height=self._BOX_HEIGHT,
            bd=1,
            relief="sunken",
            highlightthickness=0,
            cursor="hand2",
        )
        self._canvas.pack()
        self._canvas.bind("<Button-1>", self._on_click_refresh)
        self._canvas.bind("<Configure>", lambda _e: self._redraw())
        self._redraw()

    def apply_theme(self, theme) -> None:
        self._trough = theme.trough
        self._fg = theme.fg
        self._fill = "#4a90d9" if theme.name == "dark" else "#0078d4"
        self._redraw()

    def _set_fraction(self, frac: float | None) -> None:
        if frac is None:
            self._frac = None
            self._pct_text = "—"
        else:
            clamped = max(0.0, min(1.0, float(frac)))
            self._frac = clamped
            self._pct_text = f"{clamped * 100.0:.1f}%"
        self._redraw()

    def _redraw(self) -> None:
        c = self._canvas
        try:
            w = max(int(c.winfo_width()), self._BOX_WIDTH)
            h = max(int(c.winfo_height()), self._BOX_HEIGHT)
        except tk.TclError:
            return
        c.delete("all")
        c.configure(bg=self._trough, highlightbackground=self._trough)
        if self._frac is not None and self._frac > 0:
            fill_w = max(2, int(round(w * self._frac)))
            c.create_rectangle(0, 0, fill_w, h, fill=self._fill, outline="")
        c.create_text(
            w - 6,
            h // 2,
            text=self._pct_text,
            anchor="e",
            fill=self._fg,
            font=("Consolas", 9),
        )

    def _on_click_refresh(self, _event: tk.Event | None = None) -> None:
        self.reload(force=True)

    def reload(self, *, force: bool = False) -> None:
        del force
        self._token += 1
        token = self._token

        def worker() -> None:
            fraction: float | None = None
            error: str | None = None
            try:
                remaining, total = fetch_jimeng_credit()
                fraction = remaining / total if total > 0 else 0.0
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

            def apply() -> None:
                if token != self._token:
                    return
                if error:
                    self._log(f"[即梦额度] {error}")
                self._set_fraction(fraction)

            _schedule_ui(self, apply)

        threading.Thread(target=worker, daemon=True).start()


__all__ = [
    "I2V_720P_5S_CREDIT_ESTIMATE",
    "JIMENG_MONTHLY_CREDITS",
    "JimengCreditBarCompact",
    "JimengQuotaPanel",
    "estimate_jimeng_video_credits",
    "fetch_jimeng_credit",
]
