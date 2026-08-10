"""AIGC 父 Tab：内嵌「图生视频 / 文生视频 / 旧」三个子 Tab。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import tkinter as tk
from tkinter import ttk

from gui.aigc_tab import AigcTab
from gui.agent_i2v_tab import AgentI2vTab
from gui.agent_t2v_tab import AgentT2vTab
from gui.tk_thread import bind_ui_root
from gui.ui_theme import UiTheme
from scripts.aigc_lab.shell_session import load_shell_session, save_shell_session


class AigcShell(ttk.Frame):
    """左侧 Notebook 上的 AIGC 父页；业务在三个子 Tab。"""

    def __init__(
        self,
        master,
        *,
        log_fn: Callable[[str], None],
        on_preview_run: Callable[..., None] | None = None,
        on_subtab_changed: Callable[[Any], None] | None = None,
    ) -> None:
        super().__init__(master)
        bind_ui_root(self)
        self._log = log_fn
        self._on_preview_run = on_preview_run
        self._on_subtab_changed = on_subtab_changed
        self._shell_restored = False

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.i2v_tab = AgentI2vTab(
            self.notebook,
            log_fn=log_fn,
            on_preview_run=on_preview_run,
        )
        self.notebook.add(self.i2v_tab, text="图生视频")

        self.t2v_tab = AgentT2vTab(
            self.notebook,
            log_fn=log_fn,
            on_preview_run=on_preview_run,
        )
        self.notebook.add(self.t2v_tab, text="文生视频")

        self.old_tab = AigcTab(
            self.notebook,
            log_fn=log_fn,
            on_preview_run=on_preview_run,
        )
        self.notebook.add(self.old_tab, text="旧")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_subtab_changed_event)
        self.after_idle(self._restore_shell_session_once)

    def _subtab_key(self, sub: Any) -> str:
        if sub is self.i2v_tab:
            return "i2v"
        if sub is self.t2v_tab:
            return "t2v"
        return "old"

    def _restore_shell_session_once(self) -> None:
        if self._shell_restored:
            return
        self._shell_restored = True
        data = load_shell_session()
        if not data:
            return
        tab_map = {
            "i2v": self.i2v_tab,
            "t2v": self.t2v_tab,
            "old": self.old_tab,
        }
        sub = tab_map.get(str(data.get("selected_subtab") or "i2v"), self.i2v_tab)
        try:
            self.notebook.select(sub)
        except tk.TclError:
            pass

    def _current_sub(self) -> Any:
        try:
            return self.notebook.nametowidget(self.notebook.select())
        except tk.TclError:
            return self.i2v_tab

    @staticmethod
    def preview_kind_for(sub: Any) -> str:
        if isinstance(sub, AgentI2vTab):
            return "i2v"
        return "t2v"

    def _activate_sub(self, sub: Any) -> None:
        if hasattr(sub, "on_tab_selected"):
            self.after_idle(sub.on_tab_selected)
        if self._on_subtab_changed:
            self.after_idle(lambda s=sub: self._on_subtab_changed(s))
        try:
            save_shell_session(selected_subtab=self._subtab_key(sub))
        except OSError:
            pass

    def _on_subtab_changed_event(self, _event=None) -> None:
        self._activate_sub(self._current_sub())

    def on_tab_selected(self) -> None:
        self.after_idle(lambda: self._activate_sub(self._current_sub()))

    def save_session_now(self) -> None:
        try:
            save_shell_session(selected_subtab=self._subtab_key(self._current_sub()))
        except OSError:
            pass
        for sub in (self.i2v_tab, self.t2v_tab, self.old_tab):
            if hasattr(sub, "save_session_now"):
                try:
                    sub.save_session_now()
                except Exception:
                    pass

    def apply_theme(self, theme: UiTheme) -> None:
        for sub in (self.i2v_tab, self.t2v_tab, self.old_tab):
            if hasattr(sub, "apply_theme"):
                try:
                    sub.apply_theme(theme)
                except Exception:
                    pass
