"""步骤 4 混音成品预览宫格（悬停试听）。"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

_HOVER_DELAY_MS = 400
_PREVIEW_CLIP_SEC = 30.0
_BORDER_THICKNESS = 2
_COLOR_BORDER_DEFAULT = "#c8c8c8"
_COLOR_BORDER_HOVER = "#4a90d9"
_COLOR_TEXT_DEFAULT = "#222222"
_COLOR_TEXT_MUTED = "#666666"
_COLOR_TEXT_HOVER = "#1a5fb4"


class ExportMixPreviewGrid(ttk.Frame):
    """紧凑混音状态格：完成且有效 WAV 时悬停循环试听开头片段。"""

    def __init__(self, parent: tk.Widget, *, log_fn: Callable[[str], None] | None = None):
        super().__init__(parent)
        self._log = log_fn or (lambda _m: None)
        self._wav_path: Path | None = None
        self._playable = False
        self._hover = False
        self._play_after_id: str | None = None
        self._audio_proc = None
        self._play_thread: threading.Thread | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self._border = tk.Frame(
            self,
            highlightthickness=_BORDER_THICKNESS,
            highlightbackground=_COLOR_BORDER_DEFAULT,
            highlightcolor=_COLOR_BORDER_HOVER,
        )
        self._border.pack()
        self._inner = tk.Frame(self._border, padx=6, pady=4)
        self._inner.pack()
        self._lbl = tk.Label(
            self._inner,
            text="待开始",
            fg=_COLOR_TEXT_MUTED,
            font=("", 9),
            bg=self._inner.cget("bg"),
            anchor=tk.W,
        )
        self._lbl.pack()
        for widget in (self._border, self._inner, self._lbl):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def set_status(
        self,
        text: str,
        *,
        wav_path: Path | None = None,
        running: bool = False,
    ) -> None:
        self._playable = bool(wav_path and wav_path.is_file() and not running)
        self._wav_path = wav_path.resolve() if self._playable else None
        if running:
            self._stop_audio()
        display = text or "待开始"
        self._lbl.configure(text=display)
        self._refresh_border()

    def _refresh_border(self) -> None:
        if self._hover and self._playable:
            color = _COLOR_BORDER_HOVER
            fg = _COLOR_TEXT_HOVER
            font = ("", 9, "bold")
        elif self._playable:
            color = _COLOR_BORDER_DEFAULT
            fg = _COLOR_TEXT_DEFAULT
            font = ("", 9)
        else:
            color = _COLOR_BORDER_DEFAULT
            fg = _COLOR_TEXT_MUTED if self._lbl.cget("text") == "待开始" else _COLOR_TEXT_DEFAULT
            font = ("", 9)
        self._border.configure(
            highlightbackground=color,
            highlightcolor=color,
        )
        bg = self._inner.cget("bg")
        self._lbl.configure(fg=fg, font=font, bg=bg)

    def _on_enter(self, _event=None) -> None:
        if not self._playable:
            return
        self._hover = True
        self._refresh_border()
        if self._play_after_id:
            self.after_cancel(self._play_after_id)
        self._play_after_id = self.after(_HOVER_DELAY_MS, self._start_playback)

    def _on_leave(self, _event=None) -> None:
        px, py = self._border.winfo_pointerxy()
        rx = self._border.winfo_rootx()
        ry = self._border.winfo_rooty()
        rw = max(self._border.winfo_width(), 1)
        rh = max(self._border.winfo_height(), 1)
        if rx <= px <= rx + rw and ry <= py <= ry + rh:
            return
        self._hover = False
        self._stop_audio()
        self._refresh_border()

    def _start_playback(self) -> None:
        self._play_after_id = None
        if not self._hover or not self._playable or not self._wav_path:
            return
        wav = self._wav_path
        self._stop_audio()

        def worker() -> None:
            proc = None
            try:
                from gui.audio_playback import play_wav_preview

                proc = play_wav_preview(wav, max_seconds=_PREVIEW_CLIP_SEC, loop=True)
            except Exception as exc:
                self.after(0, lambda: self._log(f"混音试听失败: {exc}"))
                return

            def attach() -> None:
                if self._hover and proc is not None:
                    self._audio_proc = proc

            self.after(0, attach)

        self._play_thread = threading.Thread(target=worker, daemon=True)
        self._play_thread.start()

    def _stop_audio(self) -> None:
        if self._play_after_id:
            self.after_cancel(self._play_after_id)
            self._play_after_id = None
        try:
            from gui.audio_playback import stop_wav_playback

            stop_wav_playback(self._audio_proc)
            self._audio_proc = None
        except Exception:
            pass

    def stop_playback(self) -> None:
        self._hover = False
        self._stop_audio()
        self._refresh_border()
