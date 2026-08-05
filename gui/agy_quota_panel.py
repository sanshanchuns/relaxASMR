"""agy 三账号切换 + Weekly / Five Hour 剩余额度进度条。

布局对齐 economist 的 LLM 区：邮箱 → japan/usa/main 复选框 → 两条进度条。
额度走实时 API（``agy.quota_limits.fetch_gemini_quota_limits``），点击面板可强制刷新。
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk


class AgyQuotaPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        *,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._log = log_fn or (lambda _m: None)
        self._account_checks: dict[str, tk.BooleanVar] = {}
        self._account_syncing = False
        self._quota_email = ""
        self._quota_token = 0

        self._email_var = tk.StringVar(value="—")
        self._weekly_pct_var = tk.StringVar(value="—")
        self._five_hour_pct_var = tk.StringVar(value="—")

        self._email_lbl = ttk.Label(
            self,
            textvariable=self._email_var,
            font=("Consolas", 9),
            anchor=tk.W,
        )
        self._email_lbl.pack(anchor=tk.W, fill=tk.X)

        account_row = ttk.Frame(self)
        account_row.pack(anchor=tk.W, fill=tk.X, pady=(2, 0))
        ttk.Label(account_row, text="账号:").pack(side=tk.LEFT, padx=(0, 6))
        self._build_account_checkboxes(account_row)

        quota = ttk.Frame(self)
        quota.pack(anchor=tk.W, fill=tk.X, pady=(2, 0))

        weekly_row = ttk.Frame(quota)
        weekly_row.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(weekly_row, text="Weekly Limit", width=16, anchor=tk.W).pack(side=tk.LEFT)
        self._weekly_bar = ttk.Progressbar(
            weekly_row, orient=tk.HORIZONTAL, mode="determinate", maximum=1000, value=0
        )
        self._weekly_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        ttk.Label(
            weekly_row,
            textvariable=self._weekly_pct_var,
            width=7,
            anchor=tk.E,
            font=("Consolas", 9),
        ).pack(side=tk.RIGHT)

        five_row = ttk.Frame(quota)
        five_row.pack(fill=tk.X)
        ttk.Label(five_row, text="Five Hour Limit", width=16, anchor=tk.W).pack(side=tk.LEFT)
        self._five_hour_bar = ttk.Progressbar(
            five_row, orient=tk.HORIZONTAL, mode="determinate", maximum=1000, value=0
        )
        self._five_hour_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        ttk.Label(
            five_row,
            textvariable=self._five_hour_pct_var,
            width=7,
            anchor=tk.E,
            font=("Consolas", 9),
        ).pack(side=tk.RIGHT)

        for w in (
            self._email_lbl,
            quota,
            weekly_row,
            five_row,
            self._weekly_bar,
            self._five_hour_bar,
        ):
            self._bind_refresh(w)

        # 额度查询走外部 API / dreamina CLI；由宿主 Tab 的 on_tab_selected 触发，
        # 不在构造时自动 reload，避免用户未打开「系列视频」就刷日志/调 CLI。

    # -------------------------------------------------------- 账号
    def _build_account_checkboxes(self, parent: ttk.Frame) -> None:
        from scripts.config.paths import ensure_cli_path

        ensure_cli_path()
        from agy.client import (
            AGY_ACCOUNT_LABELS,
            agy_email_for_label,
            agy_label_for_email,
            get_active_agy_email,
        )

        active = get_active_agy_email() or agy_email_for_label("japan") or ""
        try:
            active_label = agy_label_for_email(active) or "japan"
        except Exception:  # noqa: BLE001
            active_label = "japan"
        for label in AGY_ACCOUNT_LABELS:
            var = tk.BooleanVar(value=(label == active_label))
            self._account_checks[label] = var
            ttk.Checkbutton(
                parent,
                text=label,
                variable=var,
                command=lambda picked=label: self._on_account_checkbox(picked),
            ).pack(side=tk.LEFT, padx=(0, 10))

    def _sync_checks(self, label: str | None) -> None:
        if not label or label not in self._account_checks:
            return
        self._account_syncing = True
        try:
            for name, var in self._account_checks.items():
                var.set(name == label)
        finally:
            self._account_syncing = False

    def _on_account_checkbox(self, label: str) -> None:
        if self._account_syncing:
            return
        var = self._account_checks.get(label)
        if var is not None and not var.get():
            # 不允许全部取消：点掉当前项就弹回。
            self._sync_checks(label)
            return
        self._sync_checks(label)
        from agy.client import agy_email_for_label, set_active_agy_email

        email = agy_email_for_label(label)
        if not email:
            return
        try:
            set_active_agy_email(email)
        except Exception as exc:  # noqa: BLE001
            self._log(f"[agy] 切换账号失败：{exc}")
            return
        self._log(f"[agy] 默认账号 → {label} ({email})")
        self.refresh_async(email, force=True)

    def selected_email(self) -> str | None:
        from agy.client import agy_email_for_label

        for label, var in self._account_checks.items():
            if var.get():
                return agy_email_for_label(label)
        return None

    # -------------------------------------------------------- 额度
    def reload(self) -> None:
        from agy.client import agy_label_for_email, get_active_agy_email

        email = (get_active_agy_email() or self.selected_email() or "").strip()
        if email and "@" in email:
            try:
                self._sync_checks(agy_label_for_email(email))
            except Exception:  # noqa: BLE001
                pass
            self.refresh_async(email, force=True)
        else:
            self._email_var.set("未配置 agy 账号")
            self._set_bars(None, None)

    def _bind_refresh(self, widget: tk.Misc) -> None:
        try:
            widget.configure(cursor="hand2")
        except tk.TclError:
            pass
        widget.bind("<Button-1>", self._on_click_refresh, add="+")

    def _on_click_refresh(self, _event: tk.Event | None = None) -> None:
        email = (self.selected_email() or self._quota_email or "").strip()
        if not email or "@" not in email:
            self._log("[agy] 无可用账号，无法刷新额度")
            return
        self._log(f"[agy] 刷新额度 · {email}")
        self.refresh_async(email, force=True)

    def refresh_async(self, email: str, *, force: bool = False) -> None:
        if not email or "@" not in email:
            return
        self._email_var.set(email)
        if not force and email == self._quota_email:
            return
        self._quota_email = email
        self._quota_token += 1
        token = self._quota_token

        def worker() -> None:
            weekly: float | None = None
            five: float | None = None
            err: str | None = None
            try:
                from agy.quota_limits import fetch_gemini_quota_limits

                limits = fetch_gemini_quota_limits(email)
                weekly = limits.weekly_remaining
                five = limits.five_hour_remaining
            except Exception as exc:  # noqa: BLE001
                err = str(exc)

            def apply() -> None:
                if token != self._quota_token or self._quota_email != email:
                    return
                if err:
                    self._log(f"[agy] 额度查询失败：{err}")
                self._set_bars(weekly, five)

            self.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def _set_bars(
        self, weekly_remaining: float | None, five_hour_remaining: float | None
    ) -> None:
        def _apply(bar: ttk.Progressbar, var: tk.StringVar, frac: float | None) -> None:
            if frac is None:
                bar["value"] = 0
                var.set("—")
                return
            clamped = max(0.0, min(1.0, float(frac)))
            bar["value"] = int(round(clamped * 1000))
            var.set(f"{clamped * 100.0:.1f}%")

        _apply(self._weekly_bar, self._weekly_pct_var, weekly_remaining)
        _apply(self._five_hour_bar, self._five_hour_pct_var, five_hour_remaining)


__all__ = ["AgyQuotaPanel"]
