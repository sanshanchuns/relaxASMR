"""系列视频 · 生视频模型额度条（Jimeng / Dreamina + ElevenLabs HTTP）。"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

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


class VideoQuotaPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        *,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._log = log_fn or (lambda _m: None)
        self._token = 0

        self._jm_pct_var = tk.StringVar(value="—")
        self._el_pct_var = tk.StringVar(value="—")

        quota = ttk.Frame(self)
        quota.pack(anchor=tk.W, fill=tk.X)

        jm_row = ttk.Frame(quota)
        jm_row.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(jm_row, text="jimeng_web", width=16, anchor=tk.W).pack(side=tk.LEFT)
        self._jm_bar = ttk.Progressbar(
            jm_row, orient=tk.HORIZONTAL, mode="determinate", maximum=1000, value=0
        )
        self._jm_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        ttk.Label(
            jm_row,
            textvariable=self._jm_pct_var,
            width=7,
            anchor=tk.E,
            font=("Consolas", 9),
        ).pack(side=tk.RIGHT)

        el_row = ttk.Frame(quota)
        el_row.pack(fill=tk.X)
        ttk.Label(el_row, text="elevenLabs_web", width=16, anchor=tk.W).pack(side=tk.LEFT)
        self._el_bar = ttk.Progressbar(
            el_row, orient=tk.HORIZONTAL, mode="determinate", maximum=1000, value=0
        )
        self._el_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        ttk.Label(
            el_row,
            textvariable=self._el_pct_var,
            width=7,
            anchor=tk.E,
            font=("Consolas", 9),
        ).pack(side=tk.RIGHT)

        for w in (quota, jm_row, el_row, self._jm_bar, self._el_bar):
            self._bind_refresh(w)

        # Jimeng/ElevenLabs 额度由 SeriesVideoTab.on_tab_selected 按需刷新；
        # 构造时不触发 dreamina CLI / Playwright，避免未进入该 Tab 就报错刷日志。

    def _bind_refresh(self, widget: tk.Misc) -> None:
        try:
            widget.configure(cursor="hand2")
        except tk.TclError:
            pass
        widget.bind("<Button-1>", self._on_click_refresh, add="+")

    def _on_click_refresh(self, _event: tk.Event | None = None) -> None:
        self._log("[video-quota] 刷新 Jimeng / ElevenLabs 额度")
        self.reload(force=True)

    @staticmethod
    def _set_bar(bar: ttk.Progressbar, var: tk.StringVar, frac: float | None) -> None:
        if frac is None:
            bar["value"] = 0
            var.set("—")
            return
        clamped = max(0.0, min(1.0, float(frac)))
        bar["value"] = int(round(clamped * 1000))
        var.set(f"{clamped * 100.0:.1f}%")

    def reload(self, *, force: bool = False) -> None:
        del force
        self._token += 1
        token = self._token

        def worker() -> None:
            jm_frac: float | None = None
            el_frac: float | None = None
            jm_err: str | None = None
            el_err: str | None = None

            try:
                remaining, total = fetch_jimeng_credit()
                jm_frac = remaining / total if total > 0 else 0.0
            except Exception as exc:  # noqa: BLE001
                jm_err = str(exc)

            try:
                from scripts.config.paths import ensure_cli_path

                ensure_cli_path()
                from elevenlabs_http.web_client import ElevenLabsWebClient

                usage = ElevenLabsWebClient().fetch_usage()
                if usage.character_limit > 0:
                    el_frac = usage.remaining / usage.character_limit
            except Exception as exc:  # noqa: BLE001
                el_err = str(exc)

            def apply() -> None:
                if token != self._token:
                    return
                if jm_err:
                    self._log(f"[video-quota] jimeng_web：{jm_err}")
                if el_err:
                    self._log(f"[video-quota] elevenLabs_web：{el_err}")
                self._set_bar(self._jm_bar, self._jm_pct_var, jm_frac)
                self._set_bar(self._el_bar, self._el_pct_var, el_frac)

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()


__all__ = ["VideoQuotaPanel", "fetch_jimeng_credit", "JIMENG_MONTHLY_CREDITS"]
