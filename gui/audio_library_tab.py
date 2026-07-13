"""baseURL/audio 下 Boom 声源宫格：悬停叠加循环试听、双击全局互斥常驻循环、单击多选（最多 9 个）。"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

from gui.tk_thread import bind_ui_root, schedule_on_main
from gui.ui_theme import LIGHT, UiTheme, grid_theme, paint_widget_bg

from scripts.config.paths import audio_booms_dir

CELL_W = 180
CELL_H = 56
CELL_PAD = 6
MAX_SELECT = 9
_HOVER_DELAY_MS = 400
_CLICK_DELAY_MS = 250
_BORDER_THICKNESS = 2

# 双击常驻循环：全局至多一个（同 tab / 跨 tab 互斥）
_PINNED_TAB: AudioLibraryTab | None = None
_PINNED_KEY: str | None = None
_PINNED_PROC: object | None = None


def _is_pinned(key: str) -> bool:
    return _PINNED_KEY == key


def _pinned_title(tab: AudioLibraryTab | None, key: str | None) -> str:
    if not tab or not key:
        return ""
    cell = tab._cells.get(key)
    return str(cell["title"]) if cell else ""


def _clear_pin(*, stop_audio: bool = True, log_cancel: bool = True) -> None:
    global _PINNED_TAB, _PINNED_KEY, _PINNED_PROC
    old_tab = _PINNED_TAB
    old_key = _PINNED_KEY
    proc = _PINNED_PROC
    _PINNED_TAB = None
    _PINNED_KEY = None
    _PINNED_PROC = None
    if stop_audio and proc is not None:
        try:
            from gui.audio_playback import stop_wav_playback

            stop_wav_playback(proc)
        except Exception:
            pass
    if log_cancel and old_tab is not None and old_key:
        title = _pinned_title(old_tab, old_key)
        if title:
            old_tab._log(f"{title} 取消常驻播放")
    if old_tab is not None:
        old_tab._refresh_playback_styles()


def _unpin_all(*, stop_audio: bool = True) -> None:
    _clear_pin(stop_audio=stop_audio, log_cancel=False)


def resolve_booms_dir(*, layer_id: str = "", booms_dir: Path | None = None) -> Path:
    if booms_dir is not None:
        return booms_dir
    if layer_id == "2_impact":
        from scripts.config.paths import audio_layer_dir

        return audio_layer_dir("2_impact")
    return audio_booms_dir(layer_id)


def list_boom_wavs(layer_id: str = "", *, booms_dir: Path | None = None) -> list[Path]:
    root = resolve_booms_dir(layer_id=layer_id, booms_dir=booms_dir)
    if not root.is_dir():
        return []
    return sorted(
        (p for p in root.glob("*.wav") if p.is_file()),
        key=lambda p: p.name.lower(),
    )


def wav_display_title(path: Path) -> str:
    return path.stem


class AudioLibraryTab(ttk.Frame):
    """宫格展示 booms 声源：悬停叠加循环试听、双击全局互斥常驻循环、最多 9 项选中。"""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        layer_id: str,
        track_id: str,
        on_selection_changed: Callable[[str, list[Path]], None] | None = None,
        log_fn: Callable[[str], None] | None = None,
        booms_dir: Path | None = None,
    ) -> None:
        super().__init__(parent, padding=8)
        self.layer_id = layer_id
        self.track_id = track_id
        self._booms_dir = booms_dir
        self._on_selection_changed = on_selection_changed
        self._log = log_fn or (lambda _msg: None)
        self._cells: dict[str, dict] = {}
        self._selected: list[Path] = []
        self._hover_key: str | None = None
        self._hover_proc = None
        self._play_after_id: str | None = None
        self._click_after_id: str | None = None
        self._loading = False
        self._loaded_once = False
        self._list_signature: str | None = None
        self._grid_theme = grid_theme(LIGHT)
        self._build_ui()
        bind_ui_root(self)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(toolbar, text="刷新", command=lambda: self.refresh(force=True)).pack(side=tk.LEFT)
        self.lbl_stats = ttk.Label(toolbar, text="")
        self.lbl_stats.pack(side=tk.LEFT, padx=(12, 0))
        ttk.Label(
            toolbar,
            text="单击选中/取消 · 悬停叠加循环试听 · 双击常驻循环（再次双击或双击其他格取消）· 最多 9 个",
            foreground="gray",
        ).pack(side=tk.RIGHT)

        self.lbl_base = ttk.Label(self, text="", wraplength=520, foreground="gray")
        self.lbl_base.pack(anchor=tk.W, pady=(0, 6))

        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)
        self._canvas = tk.Canvas(container, highlightthickness=0)
        self._vscroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vscroll.set)
        self._vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._grid_host = ttk.Frame(self._canvas)
        self._canvas_window = self._canvas.create_window((0, 0), window=self._grid_host, anchor=tk.NW)
        self._grid_host.bind("<Configure>", self._on_grid_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        for w in (container, self._canvas, self._grid_host):
            self._bind_mousewheel(w)

    def _bind_mousewheel(self, widget: tk.Widget) -> None:
        widget.bind("<MouseWheel>", self._on_mousewheel)
        widget.bind("<Button-4>", self._on_mousewheel)
        widget.bind("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event) -> None:
        if not self.winfo_ismapped():
            return
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            delta = -1 * (event.delta // 120) if event.delta else 0
        if delta:
            self._canvas.yview_scroll(delta, "units")

    def _on_canvas_configure(self, event=None) -> None:
        if event is not None:
            self._canvas.itemconfigure(self._canvas_window, width=event.width)
        self._sync_scroll_region()

    def _on_grid_configure(self, _event=None) -> None:
        self._sync_scroll_region()

    def _sync_scroll_region(self) -> None:
        self.update_idletasks()
        w = max(self._grid_host.winfo_reqwidth(), self._canvas.winfo_width(), 1)
        h = max(self._grid_host.winfo_reqheight(), 1)
        self._canvas.configure(scrollregion=(0, 0, w, h))

    def get_selected(self) -> list[Path]:
        return list(self._selected)

    def set_selected(self, paths: list[Path], *, notify: bool = True) -> None:
        valid = [p.resolve() for p in paths if p.is_file()][:MAX_SELECT]
        self._selected = valid
        self._apply_all_styles()
        if notify:
            self._notify_selection()

    def refresh(self, *, force: bool = False) -> None:
        if self._loading:
            return
        if not force and self._loaded_once and self._cells:
            self._apply_all_styles()
            return
        wavs = list_boom_wavs(self.layer_id, booms_dir=self._booms_dir)
        sig = "|".join(f"{p.name}:{p.stat().st_mtime_ns}" for p in wavs)
        if not force and self._loaded_once and sig == self._list_signature:
            self._apply_all_styles()
            return
        self._list_signature = sig
        self._loading = True
        items = [(w, wav_display_title(w)) for w in wavs]
        schedule_on_main(self, self._render_grid, items)

    def on_tab_selected(self) -> None:
        if self._loaded_once and self._cells:
            self.after_idle(self._sync_scroll_region)
            return
        self.refresh(force=False)

    def stop_playback(self) -> None:
        """切换 tab 时仅停止悬停试听，双击常驻循环保持播放。"""
        if self._play_after_id:
            self.after_cancel(self._play_after_id)
            self._play_after_id = None
        self._hover_key = None
        self._stop_hover_audio()
        self._refresh_playback_styles()

    def _render_grid(self, items: list[tuple[Path, str]]) -> None:
        self._loading = False
        self._loaded_once = True
        new_keys = {str(w.resolve()) for w, _ in items}
        if _PINNED_TAB is self and _PINNED_KEY and _PINNED_KEY not in new_keys:
            _clear_pin(log_cancel=False)
        self._cells.clear()
        self.stop_playback()

        for child in self._grid_host.winfo_children():
            child.destroy()

        booms = resolve_booms_dir(layer_id=self.layer_id, booms_dir=self._booms_dir)
        self.lbl_base.configure(text=f"声源目录：{booms}")

        if not items:
            ttk.Label(self._grid_host, text="未找到 WAV 文件").grid(row=0, column=0, padx=8, pady=8)
            self._update_stats()
            self.after_idle(self._sync_scroll_region)
            return

        cols = max(2, self._canvas.winfo_width() // (CELL_W + CELL_PAD * 2)) if self._canvas.winfo_width() > 1 else 3
        selected_keys = {str(p.resolve()) for p in self._selected}

        for idx, (wav, title) in enumerate(items):
            row, col = divmod(idx, cols)
            key = str(wav.resolve())
            is_selected = key in selected_keys

            outer = tk.Frame(
                self._grid_host,
                width=CELL_W + CELL_PAD,
                height=CELL_H + CELL_PAD,
                cursor="hand2",
                bg=self._grid_theme.cell_bg,
            )
            outer.grid(row=row, column=col, padx=CELL_PAD, pady=CELL_PAD)
            outer.grid_propagate(False)

            border = tk.Frame(
                outer,
                width=CELL_W - 2,
                height=CELL_H - 2,
                bg=self._grid_theme.cell_bg,
                highlightthickness=_BORDER_THICKNESS,
                highlightbackground=self._grid_theme.border_default,
                highlightcolor=self._grid_theme.border_hover,
            )
            border.pack(fill=tk.BOTH, expand=True)
            border.pack_propagate(False)

            lbl = tk.Label(
                border,
                text=title,
                wraplength=CELL_W - 20,
                justify=tk.CENTER,
                font=("", 9),
                anchor=tk.CENTER,
                bg=self._grid_theme.cell_bg,
            )
            lbl.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

            cell = {
                "key": key,
                "wav": wav,
                "title": title,
                "outer": outer,
                "border": border,
                "lbl": lbl,
                "selected": is_selected,
            }
            self._cells[key] = cell
            self._bind_cell_events(cell)
            self._apply_cell_style(cell)

        for i in range(cols):
            self._grid_host.columnconfigure(i, minsize=CELL_W + CELL_PAD * 2)

        self._update_stats()
        self.after_idle(self._sync_scroll_region)

    def _bind_cell_events(self, cell: dict) -> None:
        key = cell["key"]
        wav = cell["wav"]

        def on_click(_e) -> None:
            if self._click_after_id:
                self.after_cancel(self._click_after_id)
            self._click_after_id = self.after(_CLICK_DELAY_MS, lambda: self._on_cell_click(wav))

        def on_double_click(_e) -> None:
            if self._click_after_id:
                self.after_cancel(self._click_after_id)
                self._click_after_id = None
            self._toggle_pin(key)

        def on_enter(_e) -> None:
            self._on_cell_enter(key)

        def on_leave(_e) -> None:
            self._on_cell_leave(key, cell["border"])

        for w in (cell["outer"], cell["border"], cell["lbl"]):
            w.bind("<Button-1>", on_click)
            w.bind("<Double-Button-1>", on_double_click)
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            self._bind_mousewheel(w)

    def _on_cell_click(self, wav: Path) -> None:
        self._click_after_id = None
        self._toggle_select(wav)

    def _toggle_select(self, wav: Path) -> None:
        resolved = wav.resolve()
        if resolved in self._selected:
            self._selected = [p for p in self._selected if p != resolved]
            self._log(f"{self.track_id}：取消 {wav_display_title(wav)}")
        else:
            if len(self._selected) >= MAX_SELECT:
                messagebox.showinfo("提示", f"{self.track_id} 最多选择 {MAX_SELECT} 个声源。")
                return
            self._selected.append(resolved)
            self._log(f"{self.track_id}：选中 {wav_display_title(wav)} ({len(self._selected)}/{MAX_SELECT})")
        self._apply_all_styles()
        self._notify_selection()

    def _notify_selection(self) -> None:
        if self._on_selection_changed:
            self._on_selection_changed(self.track_id, list(self._selected))

    def _apply_all_styles(self) -> None:
        selected_keys = {str(p.resolve()) for p in self._selected}
        for key, cell in self._cells.items():
            cell["selected"] = key in selected_keys
            self._apply_cell_style(cell)
        self._update_stats()

    def apply_theme(self, theme: UiTheme) -> None:
        self._grid_theme = grid_theme(theme)
        for cell in self._cells.values():
            paint_widget_bg(self._grid_theme.cell_bg, cell["outer"], cell["border"], cell["lbl"])
            self._apply_cell_style(cell)

    def _refresh_playback_styles(self) -> None:
        for cell in self._cells.values():
            self._apply_cell_style(cell)

    def _apply_cell_style(self, cell: dict) -> None:
        selected = cell.get("selected", False)
        key = cell["key"]
        pinned = _is_pinned(key)
        hovering = self._hover_key == key and not pinned
        colors = self._grid_theme
        if pinned:
            cell["border"].configure(
                highlightbackground=colors.border_pinned,
                highlightcolor=colors.border_pinned,
            )
            cell["lbl"].configure(text=cell["title"], fg=colors.fg_pinned, bg=colors.cell_bg)
        elif selected:
            cell["border"].configure(highlightbackground=colors.border_selected, highlightcolor=colors.border_selected)
            cell["lbl"].configure(text=cell["title"], fg=colors.fg_selected, bg=colors.cell_bg)
        elif hovering:
            cell["border"].configure(highlightbackground=colors.border_hover, highlightcolor=colors.border_hover)
            cell["lbl"].configure(text=cell["title"], fg=colors.fg_hover, bg=colors.cell_bg)
        else:
            cell["border"].configure(highlightbackground=colors.border_default, highlightcolor=colors.border_hover)
            cell["lbl"].configure(text=cell["title"], fg=colors.fg_default, bg=colors.cell_bg)

    def _toggle_pin(self, key: str) -> None:
        global _PINNED_TAB, _PINNED_KEY, _PINNED_PROC

        if _PINNED_TAB is not None and _PINNED_KEY == key:
            _clear_pin(stop_audio=True)
            if self._hover_key == key:
                cell = self._cells.get(key)
                if cell and cell["wav"].is_file():
                    self._play_hover_loop(cell["wav"], key)
            return

        cell = self._cells.get(key)
        if not cell:
            return
        wav = cell["wav"]
        if not wav.is_file():
            return

        _clear_pin(stop_audio=True)

        if self._hover_key == key:
            self._stop_hover_audio()
        if self._play_after_id:
            self.after_cancel(self._play_after_id)
            self._play_after_id = None

        try:
            from gui.audio_playback import start_wav_loop

            proc = start_wav_loop(wav)
            _PINNED_TAB = self
            _PINNED_KEY = key
            _PINNED_PROC = proc
            self._log(f"{cell['title']} 常驻播放")
            self._refresh_playback_styles()
        except Exception as exc:
            self._log(f"常驻播放失败: {exc}")

    def _on_cell_enter(self, key: str) -> None:
        if self._hover_key == key:
            return
        if self._play_after_id:
            self.after_cancel(self._play_after_id)
            self._play_after_id = None

        prev_key = self._hover_key
        if prev_key and prev_key != key and not _is_pinned(prev_key):
            self._stop_hover_audio()
        if prev_key and prev_key != key:
            prev_cell = self._cells.get(prev_key)
            if prev_cell:
                self._apply_cell_style(prev_cell)

        self._hover_key = key
        cell = self._cells.get(key)
        if cell:
            self._apply_cell_style(cell)

        if _is_pinned(key):
            return

        def start_play() -> None:
            if self._hover_key != key or _is_pinned(key):
                return
            cell = self._cells.get(key)
            if not cell:
                return
            wav = cell["wav"]
            if wav.is_file():
                self._play_hover_loop(wav, key)
                if self._hover_key == key:
                    self._apply_cell_style(cell)

        self._play_after_id = self.after(_HOVER_DELAY_MS, start_play)

    def _on_cell_leave(self, key: str, border: tk.Widget) -> None:
        px, py = border.winfo_pointerxy()
        rx, ry = border.winfo_rootx(), border.winfo_rooty()
        rw, rh = border.winfo_width(), border.winfo_height()
        if rx <= px <= rx + rw and ry <= py <= ry + rh:
            return
        if self._play_after_id:
            self.after_cancel(self._play_after_id)
            self._play_after_id = None
        if self._hover_key == key:
            self._hover_key = None
            if not _is_pinned(key):
                self._stop_hover_audio()
            cell = self._cells.get(key)
            if cell:
                self._apply_cell_style(cell)

    def _play_hover_loop(self, wav_path: Path, key: str) -> None:
        try:
            from gui.audio_playback import start_wav_preview_loop

            if self._hover_key != key or _is_pinned(key):
                return
            self._hover_proc = start_wav_preview_loop(wav_path)
        except Exception as exc:
            self._log(f"播放失败: {exc}")

    def _stop_hover_audio(self) -> None:
        if not self._hover_proc:
            return
        try:
            from gui.audio_playback import stop_wav_playback

            stop_wav_playback(self._hover_proc)
        except Exception:
            pass
        self._hover_proc = None

    def _update_stats(self) -> None:
        total = len(self._cells)
        sel = len(self._selected)
        self.lbl_stats.configure(text=f"共 {total} 个 · 已选 {sel}/{MAX_SELECT}")
