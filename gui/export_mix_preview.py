"""步骤 4 混音成品预览宫格：悬停试听、双击莫兰迪红常驻循环。"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

from gui.tk_thread import bind_ui_root
from gui.ui_theme import LIGHT, UiTheme, grid_theme, paint_widget_bg

_HOVER_DELAY_MS = 400
_BORDER_THICKNESS = 2


class ExportMixPreviewGrid(ttk.Frame):
    """紧凑混音状态格：悬停循环试听；双击后莫兰迪红常驻，仅再次双击可解除。"""

    def __init__(self, parent: tk.Widget, *, log_fn: Callable[[str], None] | None = None):
        super().__init__(parent)
        self._log = log_fn or (lambda _m: None)
        self._wav_path: Path | None = None
        self._playable = False
        self._hover = False
        self._pinned = False
        self._play_after_id: str | None = None
        self._hover_proc = None
        self._pinned_proc = None
        self._grid_theme = grid_theme(LIGHT)
        self._build_ui()
        bind_ui_root(self)

    def _build_ui(self) -> None:
        colors = self._grid_theme
        self._border = tk.Frame(
            self,
            bg=colors.cell_bg,
            highlightthickness=_BORDER_THICKNESS,
            highlightbackground=colors.border_default,
            highlightcolor=colors.border_hover,
        )
        self._border.pack()
        self._inner = tk.Frame(self._border, padx=6, pady=4, bg=colors.cell_bg)
        self._inner.pack()
        self._lbl = tk.Label(
            self._inner,
            text="待开始",
            fg=colors.fg_muted,
            bg=colors.cell_bg,
            font=("", 9),
            anchor=tk.W,
        )
        self._lbl.pack()
        for widget in (self._border, self._inner, self._lbl):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<Double-Button-1>", self._on_double_click)

    def set_status(
        self,
        text: str,
        *,
        wav_path: Path | None = None,
        running: bool = False,
    ) -> None:
        self._playable = bool(wav_path and wav_path.is_file() and not running)
        new_path = wav_path.resolve() if self._playable else None
        if new_path != self._wav_path or running:
            self._unpin()
        self._wav_path = new_path
        if running:
            self._stop_hover_audio()
        display = text or "待开始"
        self._lbl.configure(text=display)
        cursor = "hand2" if self._playable else ""
        for widget in (self._border, self._inner, self._lbl):
            widget.configure(cursor=cursor)
        self._refresh_border()

    def apply_theme(self, theme: UiTheme) -> None:
        self._grid_theme = grid_theme(theme)
        paint_widget_bg(self._grid_theme.cell_bg, self._border, self._inner, self._lbl)
        self._refresh_border()

    def _refresh_border(self) -> None:
        colors = self._grid_theme
        if self._pinned:
            color = colors.border_pinned
            fg = colors.fg_pinned
            font = ("", 9, "bold")
        elif self._hover and self._playable:
            color = colors.border_hover
            fg = colors.fg_hover
            font = ("", 9, "bold")
        elif self._playable:
            color = colors.border_default
            fg = colors.fg_default
            font = ("", 9)
        else:
            color = colors.border_default
            fg = colors.fg_muted if self._lbl.cget("text") == "待开始" else colors.fg_default
            font = ("", 9)
        self._border.configure(
            highlightbackground=color,
            highlightcolor=color,
        )
        self._lbl.configure(fg=fg, font=font, bg=colors.cell_bg)

    def _pointer_inside(self) -> bool:
        px, py = self._border.winfo_pointerxy()
        rx = self._border.winfo_rootx()
        ry = self._border.winfo_rooty()
        rw = max(self._border.winfo_width(), 1)
        rh = max(self._border.winfo_height(), 1)
        return rx <= px <= rx + rw and ry <= py <= ry + rh

    def _on_double_click(self, _event=None) -> None:
        if not self._playable or not self._wav_path:
            return
        if self._pinned:
            self._unpin(log_cancel=True)
            if self._pointer_inside():
                self._hover = True
                self._refresh_border()
                self._schedule_hover_playback()
            else:
                self._hover = False
                self._refresh_border()
            return
        self._stop_hover_audio()
        if self._play_after_id:
            self.after_cancel(self._play_after_id)
            self._play_after_id = None
        self._hover = False
        try:
            from gui.audio_playback import start_wav_loop

            self._pinned_proc = start_wav_loop(self._wav_path)
            self._pinned = True
            self._log(f"{self._wav_path.name} 常驻播放")
            self._refresh_border()
        except Exception as exc:
            self._log(f"混音常驻播放失败: {exc}")

    def _on_enter(self, _event=None) -> None:
        if not self._playable or self._pinned:
            return
        self._hover = True
        self._refresh_border()
        self._schedule_hover_playback()

    def _schedule_hover_playback(self) -> None:
        if self._pinned:
            return
        if self._play_after_id:
            self.after_cancel(self._play_after_id)
        self._play_after_id = self.after(_HOVER_DELAY_MS, self._start_hover_playback)

    def _on_leave(self, _event=None) -> None:
        if self._pinned:
            return
        if self._pointer_inside():
            return
        self._hover = False
        if self._play_after_id:
            self.after_cancel(self._play_after_id)
            self._play_after_id = None
        self._stop_hover_audio()
        self._refresh_border()

    def _start_hover_playback(self) -> None:
        self._play_after_id = None
        if not self._hover or not self._playable or not self._wav_path or self._pinned:
            return
        wav = self._wav_path
        self._stop_hover_audio()
        try:
            from gui.audio_playback import start_wav_preview_loop

            self._hover_proc = start_wav_preview_loop(wav)
        except Exception as exc:
            self._log(f"混音试听失败: {exc}")

    def _stop_hover_audio(self) -> None:
        if self._play_after_id:
            self.after_cancel(self._play_after_id)
            self._play_after_id = None
        if not self._hover_proc:
            return
        try:
            from gui.audio_playback import stop_wav_playback

            stop_wav_playback(self._hover_proc)
        except Exception:
            pass
        self._hover_proc = None

    def _unpin(self, *, log_cancel: bool = False) -> None:
        if not self._pinned:
            return
        wav_name = self._wav_path.name if self._wav_path else ""
        if self._pinned_proc:
            try:
                from gui.audio_playback import stop_wav_playback

                stop_wav_playback(self._pinned_proc)
            except Exception:
                pass
        self._pinned_proc = None
        self._pinned = False
        if log_cancel and wav_name:
            self._log(f"{wav_name} 取消常驻播放")
        self._refresh_border()

    def stop_playback(self) -> None:
        self._hover = False
        self._stop_hover_audio()
        self._unpin()
        self._refresh_border()
