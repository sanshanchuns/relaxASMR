"""即梦（Jimeng / Dreamina）视频额度条，供 AIGC 实验台使用。"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

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
    dreamina = shutil.which("dreamina")
    if not dreamina:
        raise RuntimeError("未找到 dreamina CLI（curl -fsSL https://jimeng.jianying.com/cli | bash）")
    proc = subprocess.run(
        [dreamina, "user_credit"],
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


class JimengQuotaPanel(ttk.Frame):
    """单行 jimeng_web 额度条。"""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
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

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()


class JimengCreditBarCompact(ttk.Frame):
    """即梦额度：仅进度条 + 百分比（无 provider 文案）。"""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._log = log_fn or (lambda _m: None)
        self._token = 0
        self._pct_var = tk.StringVar(value="—")

        self._bar = ttk.Progressbar(
            self, orient=tk.HORIZONTAL, mode="determinate", maximum=1000, value=0
        )
        self._bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Label(
            self,
            textvariable=self._pct_var,
            width=7,
            anchor=tk.E,
            font=("Consolas", 9),
        ).pack(side=tk.RIGHT)

        for widget in (self, self._bar):
            try:
                widget.configure(cursor="hand2")
            except tk.TclError:
                pass
            widget.bind("<Button-1>", self._on_click_refresh, add="+")

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
                _set_bar(self._bar, self._pct_var, fraction)

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()


__all__ = [
    "I2V_720P_5S_CREDIT_ESTIMATE",
    "JIMENG_MONTHLY_CREDITS",
    "JimengCreditBarCompact",
    "JimengQuotaPanel",
    "estimate_jimeng_video_credits",
    "fetch_jimeng_credit",
]
