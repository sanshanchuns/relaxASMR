"""通用的轨道素材拾取器 UI 组件（支持 3x3 九宫格及悬停试听）。"""

import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable, Optional

CELL_W = 180
CELL_H = 56
CELL_PAD = 4
_HOVER_DELAY_MS = 400
_BORDER_THICKNESS = 2
_COLOR_BORDER_DEFAULT = "#c8c8c8"
_COLOR_BORDER_HOVER = "#4a90d9"
_COLOR_BORDER_SELECTED = "black"
_COLOR_TEXT_DEFAULT = "#222222"
_COLOR_TEXT_MUTED = "#666666"
_COLOR_TEXT_HOVER = "#1a5fb4"


class TrackPickerUI(ttk.Frame):
    """通用的轨道拾取组件，内含 3x3 九宫格，支持悬停试听。"""

    def __init__(
        self,
        parent: tk.Widget,
        track_name: str,
        log_fn: Callable[[str], None]
    ):
        super().__init__(parent)
        self.track_name = track_name
        self._log = log_fn
        
        self._selected_idx: int | None = None
        self._selected_wav: Path | None = None
        self._audio_proc = None
        self._hover_idx: int | None = None
        self._play_after_id: str | None = None
        self.on_select_callback: Callable[[str], None] | None = None
        
        self._build_ui()

    def _build_ui(self) -> None:
        # Top bar: Track Name and Status
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, pady=(0, 8))
        
        self.lbl_title = ttk.Label(top_frame, text=f"当前轨道：{self.track_name}", font=("", 10, "bold"))
        self.lbl_title.pack(side=tk.LEFT)
        self.lbl_status = ttk.Label(top_frame, text="暂无候选数据", foreground="gray")
        self.lbl_status.pack(side=tk.RIGHT)
        
        # Grid frame
        self.grid_frame = ttk.Frame(self)
        self.grid_frame.pack()
        
        self._grid_cells = []
        for i in range(9):
            row = i // 3
            col = i % 3
            cell = tk.Frame(self.grid_frame, width=CELL_W, height=CELL_H)
            cell.grid(row=row, column=col, padx=CELL_PAD, pady=CELL_PAD)
            cell.grid_propagate(False)

            border = tk.Frame(
                cell,
                width=CELL_W - 2,
                height=CELL_H - 2,
                highlightthickness=_BORDER_THICKNESS,
                highlightbackground=_COLOR_BORDER_DEFAULT,
                highlightcolor=_COLOR_BORDER_HOVER,
            )
            border.pack(fill=tk.BOTH, expand=True)
            border.pack_propagate(False)

            inner_cell = tk.LabelFrame(
                border,
                text=f"备选 {i + 1}",
                fg=_COLOR_TEXT_MUTED,
                font=("", 8),
                bd=0,
                relief=tk.FLAT,
                labelanchor="nw",
            )
            inner_cell.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

            lbl_name = tk.Label(
                inner_cell,
                text="—",
                wraplength=CELL_W - 16,
                justify="center",
                fg=_COLOR_TEXT_MUTED,
                font=("", 9),
                bg=inner_cell.cget("bg"),
            )
            lbl_name.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

            def on_click(e, idx=i):
                self.select_cell(idx)

            def on_enter(e, idx=i):
                self._on_grid_enter(idx)

            def on_leave(e, idx=i):
                self._on_grid_leave(idx)

            for w in (cell, border, inner_cell, lbl_name):
                w.bind("<Button-1>", on_click)
                w.bind("<Enter>", on_enter)
                w.bind("<Leave>", on_leave)
                w.configure(cursor="hand2")

            self._grid_cells.append({
                "border": border,
                "frame": inner_cell,
                "lbl_name": lbl_name,
                "wav_path": None,
                "name": None,
            })
            
        for i in range(3):
            self.grid_frame.columnconfigure(i, minsize=CELL_W + CELL_PAD * 2)
            self.grid_frame.rowconfigure(i, minsize=CELL_H + CELL_PAD * 2)

    def set_candidates(self, candidates: list[dict]) -> None:
        """直接设置候选列表（无需 JSON 文件）。"""
        self.lbl_status.configure(
            text=f"已加载 {len(candidates)} 个候选" if candidates else "暂无候选数据"
        )
        for i in range(9):
            cell = self._grid_cells[i]
            if i < len(candidates):
                match = candidates[i]
                name = match.get("name", match.get("rain_name", "未知"))
                wav_path = match.get("wav")
                cell["lbl_name"].configure(text=name)
                cell["wav_path"] = Path(wav_path) if wav_path else None
                cell["name"] = name
            else:
                cell["lbl_name"].configure(text="—")
                cell["wav_path"] = None
                cell["name"] = None
        if self._selected_wav:
            valid = {
                Path(c["wav"]).resolve()
                for c in candidates
                if c.get("wav") and Path(c["wav"]).is_file()
            }
            if self._selected_wav.resolve() not in valid:
                self._selected_idx = None
                self._selected_wav = None
        self._update_all_visuals()

    def load_candidates(self, json_path: Path | str) -> None:
        """加载候选 JSON 文件并刷新 UI。"""
        p = Path(json_path)
        if not p.is_file():
            self.lbl_status.configure(text=f"未找到数据文件")
            self._clear_grid()
            return
            
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            if isinstance(data, dict):
                cands = data.get("candidates", [])
                title = data.get("title")
                if title:
                    self.set_title(title)
            elif isinstance(data, list):
                cands = data
            else:
                self.lbl_status.configure(text="数据格式错误")
                return

            self.set_candidates(cands)

        except Exception as e:
            self._log(f"加载 {self.track_name} 失败: {e}")
            self.lbl_status.configure(text="加载失败")

    def _clear_grid(self) -> None:
        for cell in self._grid_cells:
            cell["lbl_name"].configure(text="—")
            cell["wav_path"] = None
            cell["name"] = None

    def select_cell(self, idx: int) -> None:
        cell = self._grid_cells[idx]
        if not cell["name"]:
            return

        if self._selected_idx == idx:
            self._selected_idx = None
            self._selected_wav = None
            self._update_all_visuals()
            if self.on_select_callback:
                self.on_select_callback(self.track_name)
            return

        self._selected_idx = idx
        self._selected_wav = cell["wav_path"]
        self._update_all_visuals()

        if self.on_select_callback:
            self.on_select_callback(self.track_name)

    def select_wav(self, wav: Path | str, *, notify: bool = True) -> bool:
        """按 WAV 路径选中对应格子（用于重启后恢复选中状态）。"""
        target = Path(wav).resolve()
        for i, cell in enumerate(self._grid_cells):
            wp = cell.get("wav_path")
            if wp and wp.resolve() == target:
                self._selected_idx = i
                self._selected_wav = wp
                self._update_all_visuals()
                if notify and self.on_select_callback:
                    self.on_select_callback(self.track_name)
                return True
        return False

    def clear_selection(self) -> None:
        self._selected_idx = None
        self._selected_wav = None
        self._update_all_visuals()
        
    def _update_all_visuals(self) -> None:
        for i in range(9):
            self._update_cell_visuals(i)
            
    def _update_cell_visuals(self, idx: int) -> None:
        cell = self._grid_cells[idx]
        is_selected = self._selected_idx == idx
        is_playing = self._hover_idx == idx
        has_content = bool(cell["name"])

        header = "选中" if is_selected else f"备选 {idx + 1}"

        if is_selected:
            cell["border"].configure(
                highlightthickness=_BORDER_THICKNESS,
                highlightbackground=_COLOR_BORDER_SELECTED,
                highlightcolor=_COLOR_BORDER_SELECTED,
            )
            cell["frame"].configure(text=header, fg=_COLOR_BORDER_SELECTED, font=("", 8, "bold"))
            cell["lbl_name"].configure(fg=_COLOR_BORDER_SELECTED, font=("", 9, "bold"))
        elif is_playing and has_content:
            cell["border"].configure(
                highlightthickness=_BORDER_THICKNESS,
                highlightbackground=_COLOR_BORDER_HOVER,
                highlightcolor=_COLOR_BORDER_HOVER,
            )
            cell["frame"].configure(text=header, fg=_COLOR_TEXT_HOVER, font=("", 8, "bold"))
            cell["lbl_name"].configure(fg=_COLOR_TEXT_HOVER, font=("", 9, "bold"))
        else:
            cell["border"].configure(
                highlightthickness=_BORDER_THICKNESS,
                highlightbackground=_COLOR_BORDER_DEFAULT,
                highlightcolor=_COLOR_BORDER_HOVER,
            )
            fg = _COLOR_TEXT_DEFAULT if has_content else _COLOR_TEXT_MUTED
            cell["frame"].configure(text=header, fg=_COLOR_TEXT_MUTED, font=("", 8))
            cell["lbl_name"].configure(fg=fg, font=("", 9))

        self.update_idletasks()
        
    def set_title(self, text: str) -> None:
        self.lbl_title.configure(text=text)
        
    def get_selected(self) -> Path | None:
        return self._selected_wav

    # ------------------------------------------------------------------
    # Audio Playback with Debounce
    # ------------------------------------------------------------------

    def _on_grid_enter(self, idx: int) -> None:
        if getattr(self, "_hover_idx", None) == idx:
            return
            
        if getattr(self, "_play_after_id", None):
            self.after_cancel(self._play_after_id)
            self._play_after_id = None

        prev_idx = getattr(self, "_hover_idx", None)
        if prev_idx is not None and prev_idx != idx:
            self._stop_audio()
            self._update_cell_visuals(prev_idx)
        elif prev_idx is None:
            self._stop_audio()

        self._hover_idx = idx
        
        def start_play():
            if getattr(self, "_hover_idx", None) != idx:
                return
            self._stop_audio()
            cell = self._grid_cells[idx]
            wav = cell["wav_path"]
            if wav and wav.is_file():
                try:
                    from gui.audio_playback import play_wav_preview

                    self._audio_proc = play_wav_preview(wav)
                except Exception as e:
                    self._log(f"播放失败: {e}")
                if getattr(self, "_hover_idx", None) == idx:
                    self._update_cell_visuals(idx)
                
        # Debounce: wait before starting playback (与素材库一致)
        self._play_after_id = self.after(_HOVER_DELAY_MS, start_play)

    def _on_grid_leave(self, idx: int) -> None:
        cell_frame = self._grid_cells[idx]["frame"]
        
        px, py = cell_frame.winfo_pointerxy()
        rx = cell_frame.winfo_rootx()
        ry = cell_frame.winfo_rooty()
        rw = cell_frame.winfo_width()
        rh = cell_frame.winfo_height()
        
        if rx <= px <= rx + rw and ry <= py <= ry + rh:
            return
            
        if getattr(self, "_play_after_id", None):
            self.after_cancel(self._play_after_id)
            self._play_after_id = None
            
        self._hover_idx = None
        self._stop_audio()
        self._update_cell_visuals(idx)

    def _stop_audio(self) -> None:
        if getattr(self, "_play_after_id", None):
            self.after_cancel(self._play_after_id)
            self._play_after_id = None

        try:
            from gui.audio_playback import stop_wav_playback

            stop_wav_playback(getattr(self, "_audio_proc", None))
            self._audio_proc = None
        except Exception:
            pass

    def force_stop_all(self) -> None:
        self._stop_audio()
        try:
            from gui.audio_playback import force_stop_all_playback

            force_stop_all_playback()
        except Exception:
            pass
