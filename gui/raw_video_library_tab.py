"""素材库 · raw 视频：选定目录下（不含子目录）视频宫格 + 拍摄参数。"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, ttk

from PIL import Image, ImageTk

from gui.tk_thread import bind_ui_root, schedule_on_main
from gui.ui_theme import LIGHT, UiTheme, grid_theme, paint_widget_bg
from gui.video_library_tab import CELL_H, CELL_PAD, CELL_W, file_list_signature
from gui.video_metadata import (
    format_raw_video_meta_lines,
    is_image_path,
    list_dir_videos,
    load_raw_media_thumb,
    peek_raw_video_info_cache,
    read_raw_video_info,
)

META_LINE_H = 14
TITLE_H = 16
CELL_TOTAL_H = CELL_H + TITLE_H + META_LINE_H * 3 + CELL_PAD + 8


class RawVideoLibraryTab(ttk.Frame):
    """展示选定目录根层视频文件及 ffprobe / exiftool 读取的拍摄参数。"""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        get_directory: Callable[[], str],
        set_directory: Callable[[str], None],
        on_video_preview: Callable[[Path, dict[str, str], Image.Image | None], None] | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, padding=8)
        self._get_directory = get_directory
        self._set_directory = set_directory
        self._on_video_preview = on_video_preview
        self._log = log_fn or (lambda _msg: None)
        self._cells: dict[str, dict] = {}
        self._photo_refs: list[ImageTk.PhotoImage] = []
        self._thumb_cache: dict[str, Image.Image] = {}
        self._loading = False
        self._loaded_once = False
        self._list_signature: str | None = None
        self._current_dir: Path | None = None
        self._selected_key: str | None = None
        self._load_generation = 0
        self._dewatermark_busy = False
        self._ui_theme: UiTheme = LIGHT
        self._grid_theme = grid_theme(LIGHT)
        self._section_labels: list[tk.Label] = []
        self._build_ui()
        bind_ui_root(self)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(toolbar, text="选择目录", command=self._pick_directory).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="刷新", command=lambda: self.refresh(force=True)).pack(side=tk.LEFT, padx=(6, 0))
        self._btn_dewatermark = ttk.Button(
            toolbar, text="图片去水印", command=self._on_dewatermark_clicked
        )
        self._btn_dewatermark.pack(side=tk.LEFT, padx=(6, 0))
        self.lbl_stats = ttk.Label(toolbar, text="")
        self.lbl_stats.pack(side=tk.LEFT, padx=(12, 0))
        ttk.Label(
            toolbar,
            text="单击选中后可「图片去水印」· 默认去右上水印 / 有字幕才去底部字幕",
            foreground="gray",
        ).pack(side=tk.RIGHT)

        self.lbl_dir = ttk.Label(self, text="", wraplength=720, foreground="gray")
        self.lbl_dir.pack(anchor=tk.W, pady=(0, 6))

        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)
        self._scroll_container = container
        self._canvas = tk.Canvas(
            container,
            highlightthickness=0,
            bg=self._ui_theme.canvas_bg,
        )
        self._vscroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._on_scroll_set)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._grid_host = tk.Frame(self._canvas, bg=self._ui_theme.canvas_bg)
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
        if not self._needs_scrollbar():
            return
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            delta = -1 * (event.delta // 120) if event.delta else 0
        if delta:
            self._canvas.yview_scroll(delta, "units")

    def _on_scroll_set(self, first: str, last: str) -> None:
        self._vscroll.set(first, last)
        self._update_scrollbar_visibility()

    def _needs_scrollbar(self) -> bool:
        self.update_idletasks()
        content_h = max(self._grid_host.winfo_reqheight(), 1)
        view_h = max(self._canvas.winfo_height(), 1)
        return content_h > view_h + 2

    def _update_scrollbar_visibility(self) -> None:
        need = self._needs_scrollbar()
        mapped = bool(self._vscroll.winfo_ismapped())
        if need and not mapped:
            self._canvas.pack_forget()
            self._vscroll.pack(side=tk.RIGHT, fill=tk.Y)
            self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        elif not need and mapped:
            self._vscroll.pack_forget()
            self._canvas.yview_moveto(0)

    def _on_canvas_configure(self, event=None) -> None:
        if event is not None:
            self._canvas.itemconfigure(self._canvas_window, width=event.width)
        self._sync_scroll_region()

    def _on_grid_configure(self, _event=None) -> None:
        self._sync_scroll_region()

    def _sync_scroll_region(self) -> None:
        self.update_idletasks()
        view_w = max(self._canvas.winfo_width(), 1)
        view_h = max(self._canvas.winfo_height(), 1)
        content_h = max(self._grid_host.winfo_reqheight(), 1)
        # 内容不足一屏时，scrollregion 高度跟视口对齐，避免「假滚动」
        region_h = content_h if content_h > view_h + 2 else view_h
        self._canvas.configure(scrollregion=(0, 0, view_w, region_h))
        self._update_scrollbar_visibility()

    def _update_dir_label(self, directory: Path | None = None) -> None:
        if directory is not None:
            self.lbl_dir.configure(
                text=f"目录：{directory}（仅根层视频/图片，不含子目录）"
            )
            return
        raw = (self._get_directory() or "").strip()
        if not raw:
            self.lbl_dir.configure(text="目录：未选择（仅展示选定目录根层视频/图片，不含子目录）")
            return
        path = Path(raw)
        if path.is_dir():
            self.lbl_dir.configure(
                text=f"目录：{path}（仅根层视频/图片，不含子目录）"
            )
        else:
            self.lbl_dir.configure(text=f"目录：{raw}（路径无效或不可访问）")

    def _pick_directory(self) -> None:
        initial = self._get_directory() or str(Path.home())
        self._log("素材库 raw：打开目录选择…")
        folder = filedialog.askdirectory(title="选择 raw 视频目录", initialdir=initial)
        if not folder:
            self._log("素材库 raw：已取消选择目录")
            return
        directory = Path(folder)
        videos = list_dir_videos(directory) if directory.is_dir() else []
        count = len(videos)
        self.lbl_stats.configure(text=self._format_stats(videos) if videos else "共 0 个")
        self._update_dir_label(directory)
        self._log(f"素材库 raw：已选择目录 {directory}，共 {count} 个文件")
        self._set_directory(folder)
        self._selected_key = None
        self.update_idletasks()
        self.refresh(force=True, announce=False)

    def _resolve_directory(self) -> Path | None:
        raw = (self._get_directory() or "").strip()
        if not raw:
            return None
        path = Path(raw)
        return path if path.is_dir() else None

    def refresh(self, *, force: bool = False, announce: bool = True) -> None:
        directory = self._resolve_directory()
        self._current_dir = directory
        if directory is None:
            self._render_empty("尚未选择目录，请点击「选择目录」")
            return
        self._update_dir_label(directory)
        videos = list_dir_videos(directory)
        sig = f"{directory}:{file_list_signature(videos)}"
        if not force and self._loaded_once and sig == self._list_signature:
            return

        self._list_signature = sig
        self._load_generation += 1
        generation = self._load_generation
        self._loading = True
        self.lbl_stats.configure(text=self._format_stats(videos) if videos else "共 0 个")

        if announce:
            action = "刷新" if force else "加载"
            self._log(f"素材库 raw：{action}目录 {directory}，共 {len(videos)} 个文件")
        self._init_grid_shell(directory, videos)
        threading.Thread(
            target=self._load_items_progressive,
            args=(directory, videos, generation),
            daemon=True,
        ).start()

    def _placeholder_info(self, video: Path) -> dict[str, str]:
        info = {
            "title": video.stem,
            "kind": "image" if is_image_path(video) else "video",
            "resolution": "…",
            "fps": "…",
            "bitrate": "…",
            "iso": "…",
            "aperture": "…",
            "shutter": "…",
            "color_temp": "…",
            "focal_length": "…",
        }
        if is_image_path(video):
            info["format"] = "PNG" if video.suffix.lower() == ".png" else "JPG"
        return info

    def _format_stats(self, paths: list[Path]) -> str:
        videos = sum(1 for p in paths if not is_image_path(p))
        photos = sum(1 for p in paths if is_image_path(p))
        total = len(paths)
        if photos and videos:
            return f"共 {total} 个（视频 {videos} · 照片 {photos}）"
        if photos:
            return f"共 {total} 个（照片）"
        return f"共 {total} 个（视频）"

    def _split_media(self, paths: list[Path]) -> tuple[list[Path], list[Path]]:
        videos = [p for p in paths if not is_image_path(p)]
        photos = [p for p in paths if is_image_path(p)]
        return videos, photos

    def on_tab_selected(self) -> None:
        self.refresh(force=False)
        self.after_idle(self._sync_scroll_region)

    def _load_items_progressive(self, directory: Path, videos: list[Path], generation: int) -> None:
        total = len(videos)
        for idx, video in enumerate(videos, start=1):
            if generation != self._load_generation:
                return

            key = video.name
            self._log(f"素材库 raw：加载封面 ({idx}/{total}) {video.name}")
            cache_key = f"{video}:{video.stat().st_mtime_ns}"
            thumb = self._thumb_cache.get(cache_key)
            if thumb is None:
                thumb = load_raw_media_thumb(video)
                if thumb is not None:
                    self._thumb_cache[cache_key] = thumb
            schedule_on_main(self, self._update_cell_thumb, key, thumb, generation)

            info = peek_raw_video_info_cache(video)
            if info is not None:
                self._log(f"素材库 raw：参数命中缓存 ({idx}/{total}) {video.name}")
                schedule_on_main(self, self._update_cell_info, key, info, generation)
                continue

            if generation != self._load_generation:
                return
            self._log(f"素材库 raw：解析参数 ({idx}/{total}) {video.name}")
            info = read_raw_video_info(video)
            schedule_on_main(self, self._update_cell_info, key, info, generation)

        if generation != self._load_generation:
            return
        schedule_on_main(self, self._finish_loading, directory, total, generation)
        self._log(f"素材库 raw：加载完成，共 {total} 个文件")

    def _render_empty(self, message: str) -> None:
        self._loading = False
        self._loaded_once = True
        self._photo_refs.clear()
        self._cells.clear()
        self._section_labels.clear()
        self._selected_key = None
        for child in self._grid_host.winfo_children():
            child.destroy()
        self._update_dir_label()
        ttk.Label(self._grid_host, text=message).grid(row=0, column=0, padx=8, pady=8)
        self.lbl_stats.configure(text="")
        self.after_idle(self._sync_scroll_region)

    def _add_section_header(self, text: str, row: int, cols: int) -> int:
        lbl = tk.Label(
            self._grid_host,
            text=text,
            font=("", 10, "bold"),
            fg=self._grid_theme.fg_default,
            bg=self._ui_theme.canvas_bg,
            anchor=tk.W,
        )
        lbl.grid(row=row, column=0, columnspan=max(cols, 1), sticky="ew", padx=CELL_PAD, pady=(10, 4))
        self._section_labels.append(lbl)
        self._bind_mousewheel(lbl)
        return row + 1

    def _create_cell(self, video: Path, row: int, col: int) -> None:
        key = video.name
        info = peek_raw_video_info_cache(video) or self._placeholder_info(video)
        line1, line2, line3 = format_raw_video_meta_lines(info)

        outer = tk.Frame(
            self._grid_host,
            width=CELL_W + CELL_PAD,
            height=CELL_TOTAL_H,
            cursor="hand2",
            bg=self._grid_theme.cell_bg,
        )
        outer.grid(row=row, column=col, padx=CELL_PAD, pady=CELL_PAD)
        outer.grid_propagate(False)

        border = tk.Frame(
            outer,
            bg=self._grid_theme.cell_bg,
            highlightthickness=2,
            highlightbackground=self._grid_theme.border_default,
            highlightcolor=self._grid_theme.border_hover,
        )
        border.pack(fill=tk.BOTH, expand=True)

        img_lbl = tk.Label(
            border,
            bd=0,
            relief=tk.FLAT,
            bg=self._grid_theme.cell_bg,
            text="加载中…",
            fg="#999999",
        )
        img_lbl.pack(fill=tk.BOTH, expand=False, padx=1, pady=(1, 0))

        title_lbl = tk.Label(
            border,
            text=info.get("title") or video.stem,
            font=("", 8, "bold"),
            fg=self._grid_theme.fg_default,
            bg=self._grid_theme.cell_bg,
            anchor=tk.W,
        )
        title_lbl.pack(fill=tk.X, padx=4, pady=(2, 0))

        meta_lbl = tk.Label(
            border,
            text=f"{line1}\n{line2}\n{line3}",
            font=("", 7),
            fg=self._grid_theme.fg_muted,
            bg=self._grid_theme.cell_bg,
            justify=tk.LEFT,
            anchor=tk.W,
        )
        meta_lbl.pack(fill=tk.X, padx=4, pady=(0, 2))

        cell = {
            "video": video,
            "info": info,
            "key": key,
            "outer": outer,
            "border": border,
            "img_lbl": img_lbl,
            "title_lbl": title_lbl,
            "meta_lbl": meta_lbl,
            "thumb": None,
            "thumb_loaded": False,
        }
        self._cells[key] = cell
        self._apply_cell_style(cell, selected=(key == self._selected_key))
        self._bind_cell_events(cell)

    def _init_grid_shell(self, directory: Path, videos: list[Path]) -> None:
        self._loaded_once = True
        self._photo_refs.clear()
        self._cells.clear()
        self._section_labels.clear()

        for child in self._grid_host.winfo_children():
            child.destroy()

        self._update_dir_label(directory)
        self._grid_host.configure(bg=self._ui_theme.canvas_bg)
        self._canvas.configure(bg=self._ui_theme.canvas_bg)

        if not videos:
            ttk.Label(self._grid_host, text="该目录下没有视频或图片文件").grid(row=0, column=0, padx=8, pady=8)
            self.lbl_stats.configure(text="共 0 个")
            self._loading = False
            self.after_idle(self._sync_scroll_region)
            return

        cols = max(2, self._canvas.winfo_width() // (CELL_W + CELL_PAD * 2)) if self._canvas.winfo_width() > 1 else 3
        video_paths, photo_paths = self._split_media(videos)
        row = 0

        if video_paths:
            row = self._add_section_header(f"视频（{len(video_paths)}）", row, cols)
            for idx, video in enumerate(video_paths):
                r, c = divmod(idx, cols)
                self._create_cell(video, row + r, c)
            row += (len(video_paths) + cols - 1) // cols

        if photo_paths:
            row = self._add_section_header(f"照片（{len(photo_paths)}）", row, cols)
            for idx, photo in enumerate(photo_paths):
                r, c = divmod(idx, cols)
                self._create_cell(photo, row + r, c)

        self.lbl_stats.configure(text=self._format_stats(videos))
        self.after_idle(self._sync_scroll_region)

    def _update_cell_thumb(
        self,
        key: str,
        thumb: Image.Image | None,
        generation: int,
    ) -> None:
        if generation != self._load_generation:
            return
        cell = self._cells.get(key)
        if not cell:
            return
        cell["thumb"] = thumb
        cell["thumb_loaded"] = True
        self._apply_cell_style(cell, selected=(key == self._selected_key))

    def _update_cell_info(self, key: str, info: dict[str, str], generation: int) -> None:
        if generation != self._load_generation:
            return
        cell = self._cells.get(key)
        if not cell:
            return
        cell["info"] = info
        line1, line2, line3 = format_raw_video_meta_lines(info)
        cell["meta_lbl"].configure(text=f"{line1}\n{line2}\n{line3}")
        cell["title_lbl"].configure(text=info.get("title") or cell["video"].stem)

    def _finish_loading(self, directory: Path, total: int, generation: int) -> None:
        if generation != self._load_generation:
            return
        self._loading = False
        self._current_dir = directory
        paths = [cell["video"] for cell in self._cells.values()]
        self.lbl_stats.configure(text=self._format_stats(paths) if paths else f"共 {total} 个")
        self.after_idle(self._sync_scroll_region)

    def apply_theme(self, theme: UiTheme) -> None:
        self._ui_theme = theme
        self._grid_theme = grid_theme(theme)
        self._canvas.configure(bg=theme.canvas_bg)
        self._grid_host.configure(bg=theme.canvas_bg)
        for lbl in self._section_labels:
            try:
                lbl.configure(bg=theme.canvas_bg, fg=self._grid_theme.fg_default)
            except tk.TclError:
                pass
        for key, cell in self._cells.items():
            paint_widget_bg(
                self._grid_theme.cell_bg,
                cell["outer"],
                cell["border"],
                cell["img_lbl"],
                cell["title_lbl"],
                cell["meta_lbl"],
            )
            self._apply_cell_style(cell, selected=(key == self._selected_key))

    def _select_cell(self, key: str) -> None:
        if self._selected_key == key:
            return
        prev = self._selected_key
        self._selected_key = key
        if prev and prev in self._cells:
            self._apply_cell_style(self._cells[prev], selected=False)
        if key in self._cells:
            self._apply_cell_style(self._cells[key], selected=True)

    def _apply_cell_style(self, cell: dict, *, selected: bool = False) -> None:
        thumb: Image.Image | None = cell.get("thumb")
        colors = self._grid_theme
        border_color = colors.border_selected if selected else colors.border_default
        cell["border"].configure(
            highlightbackground=border_color,
            highlightcolor=colors.border_hover,
        )
        cell["title_lbl"].configure(fg=colors.fg_default, bg=colors.cell_bg)
        cell["meta_lbl"].configure(fg=colors.fg_muted, bg=colors.cell_bg)
        cell["img_lbl"].configure(bg=colors.cell_bg)
        if thumb is not None:
            tw, th = CELL_W - 4, CELL_H - 4
            iw, ih = thumb.size
            scale = min(tw / iw, th / ih)
            nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
            fitted = thumb.resize((nw, nh), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (tw, th), "#2a2a2a")
            canvas.paste(fitted, ((tw - nw) // 2, (th - nh) // 2))
            photo = ImageTk.PhotoImage(canvas)
            self._photo_refs.append(photo)
            cell["img_lbl"].configure(image=photo, text="")
        elif cell.get("thumb_loaded"):
            cell["img_lbl"].configure(image="", text="无预览", fg="#999999")

    def _on_dewatermark_clicked(self) -> None:
        from tkinter import messagebox

        if self._dewatermark_busy:
            messagebox.showinfo("图片去水印", "正在处理中，请稍候…")
            return
        if not self._selected_key or self._selected_key not in self._cells:
            messagebox.showwarning("图片去水印", "请先单击选中一张照片。")
            return
        cell = self._cells[self._selected_key]
        path: Path = cell["video"]
        if not is_image_path(path):
            messagebox.showwarning("图片去水印", "当前选中的是视频，请选择照片。")
            return
        if not path.is_file():
            messagebox.showerror("图片去水印", f"文件不存在：\n{path}")
            return

        self._dewatermark_busy = True
        self._btn_dewatermark.configure(state=tk.DISABLED)
        self._log(f"素材库 raw：去水印开始 → {path.name}")

        def worker() -> None:
            try:
                from scripts.video_analysis.image_dewatermark import remove_image_watermarks

                result = remove_image_watermarks(path, log_fn=self._log)
                parts = []
                if result.removed_top_right:
                    parts.append("右上水印")
                if result.removed_subtitle:
                    parts.append("底部字幕")
                summary = "、".join(parts) if parts else "未发现可去内容"
                schedule_on_main(
                    self,
                    self._on_dewatermark_done,
                    True,
                    result.output_path,
                    summary,
                )
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._on_dewatermark_done, False, path, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_dewatermark_done(self, ok: bool, out_path: Path, detail: str) -> None:
        from tkinter import messagebox

        self._dewatermark_busy = False
        try:
            self._btn_dewatermark.configure(state=tk.NORMAL)
        except tk.TclError:
            pass
        if not ok:
            self._log(f"素材库 raw：去水印失败 — {detail}")
            messagebox.showerror("图片去水印失败", detail)
            return
        self._log(f"素材库 raw：去水印完成（{detail}）→ {out_path.name}")
        # 刷新目录，让 *_clean 出现在宫格；并尽量选中输出图
        self.refresh(force=True, announce=False)
        self.after(300, lambda p=out_path: self._select_output_if_present(p))
        messagebox.showinfo("图片去水印", f"完成：{detail}\n已保存：{out_path.name}")

    def _select_output_if_present(self, out_path: Path) -> None:
        key = out_path.name
        if key not in self._cells:
            return
        self._select_cell(key)
        cell = self._cells[key]
        if self._on_video_preview:
            self._on_video_preview(cell["video"], cell["info"], cell.get("thumb"))

    def _bind_cell_events(self, cell: dict) -> None:
        def on_click(_e) -> None:
            key: str = cell["key"]
            self._select_cell(key)
            video: Path = cell["video"]
            info: dict[str, str] = cell["info"]
            thumb: Image.Image | None = cell.get("thumb")
            if self._on_video_preview:
                self._on_video_preview(video, info, thumb)

        for w in (cell["outer"], cell["border"], cell["img_lbl"], cell["title_lbl"], cell["meta_lbl"]):
            w.bind("<Button-1>", on_click)
            self._bind_mousewheel(w)
