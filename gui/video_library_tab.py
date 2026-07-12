"""baseURL 根目录 MP4 首帧宫格预览与上传状态标记。"""

from __future__ import annotations

import re
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk

import cv2
from PIL import Image, ImageEnhance, ImageTk

from scripts.config.paths import base_url, material_dir
from gui.tk_thread import bind_ui_root, schedule_on_main

CELL_W = 168
CELL_H = 96
CELL_PAD = 6
LABEL_H = 18
_CLICK_DELAY_MS = 280


def scene_num_from_video(path: Path) -> str:
    m = re.search(r"MVI_(\d+)", path.name, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\d+", path.stem)
    return m.group() if m else path.stem


def list_root_mp4s() -> list[Path]:
    bu = base_url()
    if not bu.is_dir():
        return []
    return sorted(
        (p for p in bu.glob("*.mp4") if not p.name.startswith("._") and not p.name.startswith(".")),
        key=lambda p: p.name.lower(),
    )


def _thumb_cache_dir() -> Path:
    d = material_dir() / ".root_mp4_thumbs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _quality_from_size(width: int, height: int) -> str:
    if width >= 3840 or height >= 2160:
        return "4K"
    if width >= 1920 or height >= 1080:
        return "FHD"
    return ""


def read_video_quality(video: Path) -> str:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return ""
    try:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        cap.release()
    return _quality_from_size(w, h)


def extract_first_frame(video: Path, out: Path, *, width: int = CELL_W - 4) -> tuple[bool, str]:
    if out.is_file() and out.stat().st_mtime >= video.stat().st_mtime:
        quality_cache = out.with_suffix(".quality")
        if quality_cache.is_file():
            return True, quality_cache.read_text(encoding="utf-8").strip()
        return True, read_video_quality(video)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return False, ""
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return False, ""
    h, w = frame.shape[:2]
    if w <= 0 or h <= 0:
        return False, ""
    quality = _quality_from_size(w, h)
    scale = width / w
    nh = max(1, int(h * scale))
    resized = cv2.resize(frame, (width, nh))
    out.parent.mkdir(parents=True, exist_ok=True)
    saved = cv2.imwrite(str(out), resized)
    if saved and quality:
        out.with_suffix(".quality").write_text(quality, encoding="utf-8")
    return saved, quality


def load_thumb_image(video: Path) -> tuple[Image.Image | None, str]:
    cache = _thumb_cache_dir() / f"{video.stem}_{int(video.stat().st_mtime)}.jpg"
    ok, quality = extract_first_frame(video, cache)
    if not ok:
        return None, quality
    try:
        return Image.open(cache).convert("RGB"), quality
    except OSError:
        return None, quality


def styled_thumb(img: Image.Image, *, uploaded: bool) -> Image.Image:
    target = Image.new("RGB", (CELL_W - 4, CELL_H - 4), "#2a2a2a")
    iw, ih = img.size
    tw, th = CELL_W - 4, CELL_H - 4
    scale = min(tw / iw, th / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    fitted = img.resize((nw, nh), Image.Resampling.LANCZOS)
    ox, oy = (tw - nw) // 2, (th - nh) // 2
    if uploaded:
        fitted = ImageEnhance.Brightness(fitted.convert("L").convert("RGB")).enhance(0.45)
    target.paste(fitted, (ox, oy))
    return target


def file_list_signature(videos: list[Path]) -> str:
    return "|".join(f"{p.name}:{p.stat().st_mtime_ns}" for p in videos)


class VideoLibraryTab(ttk.Frame):
    """平铺 baseURL 根目录所有 loop MP4 首帧，支持上传标记。"""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        is_uploaded: Callable[[str], bool],
        toggle_uploaded: Callable[[str, bool], None],
        on_video_select: Callable[[Path], None] | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, padding=8)
        self._is_uploaded = is_uploaded
        self._toggle_uploaded = toggle_uploaded
        self._on_video_select = on_video_select
        self._log = log_fn or (lambda _msg: None)
        self._cells: dict[str, dict] = {}
        self._photo_refs: list[ImageTk.PhotoImage] = []
        self._thumb_cache: dict[str, Image.Image] = {}
        self._loading = False
        self._loaded_once = False
        self._list_signature: str | None = None
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
            text="单击切换「已上传」· 双击选定视频",
            foreground="gray",
        ).pack(side=tk.RIGHT)

        self.lbl_base = ttk.Label(self, text="", wraplength=520, foreground="gray")
        self.lbl_base.pack(anchor=tk.W, pady=(0, 6))

        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)
        self._scroll_container = container
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

    def refresh(self, *, force: bool = False) -> None:
        if self._loading:
            return
        videos = list_root_mp4s()
        sig = file_list_signature(videos)
        if not force and self._loaded_once and sig == self._list_signature:
            self._sync_all_cell_styles()
            return
        self._list_signature = sig
        self._loading = True
        threading.Thread(target=self._load_and_render, args=(videos,), daemon=True).start()

    def on_tab_selected(self) -> None:
        """切到素材库 Tab 时调用：仅在首次或文件变化时重建宫格。"""
        self.refresh(force=False)
        self.after_idle(self._sync_scroll_region)

    def _sync_all_cell_styles(self) -> None:
        changed = False
        for cell in self._cells.values():
            if cell.get("uploaded") != self._is_uploaded(cell["num"]):
                self._apply_cell_style(cell)
                changed = True
        if changed or not self.lbl_stats.cget("text"):
            self._update_stats()

    def refresh_cell(self, scene_num: str) -> None:
        cell = self._cells.get(scene_num)
        if not cell:
            self.refresh()
            return
        self._apply_cell_style(cell)

    def mark_uploaded(self, scene_num: str, uploaded: bool = True) -> None:
        if self._is_uploaded(scene_num) != uploaded:
            self._toggle_uploaded(scene_num, uploaded)
        self.refresh_cell(scene_num)
        self._update_stats()

    def _load_and_render(self, videos: list[Path]) -> None:
        items: list[tuple[Path, str, Image.Image | None, str]] = []
        for video in videos:
            num = scene_num_from_video(video)
            cache_key = f"{video}:{video.stat().st_mtime_ns}"
            thumb = self._thumb_cache.get(cache_key)
            quality = ""
            if thumb is None:
                thumb, quality = load_thumb_image(video)
                if thumb is not None:
                    self._thumb_cache[cache_key] = thumb
            else:
                cache = _thumb_cache_dir() / f"{video.stem}_{int(video.stat().st_mtime)}.jpg"
                qf = cache.with_suffix(".quality")
                if qf.is_file():
                    quality = qf.read_text(encoding="utf-8").strip()
                elif cache.is_file():
                    quality = read_video_quality(video)
            items.append((video, num, thumb, quality))
        schedule_on_main(self, self._render_grid, items)

    def _render_grid(self, items: list[tuple[Path, str, Image.Image | None, str]]) -> None:
        self._loading = False
        self._loaded_once = True
        self._photo_refs.clear()
        self._cells.clear()

        for child in self._grid_host.winfo_children():
            child.destroy()

        bu = base_url()
        self.lbl_base.configure(text=f"baseURL：{bu}（仅根目录 *.mp4）")

        if not items:
            ttk.Label(self._grid_host, text="未找到 MP4 文件").grid(row=0, column=0, padx=8, pady=8)
            self._update_stats()
            self.after_idle(self._sync_scroll_region)
            return

        cols = max(2, self._canvas.winfo_width() // (CELL_W + CELL_PAD * 2)) if self._canvas.winfo_width() > 1 else 3

        for idx, (video, num, thumb, quality) in enumerate(items):
            row, col = divmod(idx, cols)
            uploaded = self._is_uploaded(num)

            outer = tk.Frame(
                self._grid_host,
                width=CELL_W + CELL_PAD,
                height=CELL_H + LABEL_H + CELL_PAD,
                cursor="hand2",
            )
            outer.grid(row=row, column=col, padx=CELL_PAD, pady=CELL_PAD)
            outer.grid_propagate(False)

            border = tk.Frame(
                outer,
                highlightthickness=2,
                highlightbackground="#888888" if uploaded else "#c8c8c8",
                highlightcolor="#4a90d9",
            )
            border.pack(fill=tk.BOTH, expand=True)

            img_lbl = tk.Label(border, bd=0, relief=tk.FLAT)
            img_lbl.pack(fill=tk.BOTH, expand=True, padx=1, pady=(1, 0))

            base_name = f"MVI_{num}" if num.isdigit() else video.stem[:20]
            if quality:
                base_name = f"{base_name} {quality}"
            name_lbl = tk.Label(
                border,
                text=base_name,
                font=("", 8),
                fg="#666666" if uploaded else "#222222",
                anchor=tk.CENTER,
            )
            name_lbl.pack(fill=tk.X, pady=(0, 2))

            cell = {
                "video": video,
                "num": num,
                "base_name": base_name,
                "uploaded": uploaded,
                "outer": outer,
                "border": border,
                "img_lbl": img_lbl,
                "name_lbl": name_lbl,
                "thumb": thumb,
            }
            self._cells[num] = cell
            self._apply_cell_style(cell)
            self._bind_cell_events(cell)

        self._update_stats()
        self.after_idle(self._sync_scroll_region)

    def _apply_cell_style(self, cell: dict) -> None:
        num = cell["num"]
        uploaded = self._is_uploaded(num)
        cell["uploaded"] = uploaded
        thumb: Image.Image | None = cell.get("thumb")
        border = cell["border"]
        img_lbl = cell["img_lbl"]
        name_lbl = cell["name_lbl"]

        border.configure(highlightbackground="#666666" if uploaded else "#c8c8c8")
        name_lbl.configure(
            fg="#888888" if uploaded else "#222222",
            text=cell["base_name"] + ("  ✓已上传" if uploaded else ""),
        )

        if thumb is not None:
            shown = styled_thumb(thumb, uploaded=uploaded)
            photo = ImageTk.PhotoImage(shown)
            self._photo_refs.append(photo)
            img_lbl.configure(image=photo, text="")
        else:
            img_lbl.configure(image="", text="无预览", fg="#999999")

    def _bind_cell_events(self, cell: dict) -> None:
        """单击标记上传状态；双击选定视频（避免双击连带触发单击）。"""
        scene_num = cell["num"]
        pending: dict[str, str | None] = {"id": None}

        def on_single(_e) -> None:
            if pending["id"]:
                cell["outer"].after_cancel(pending["id"])
            pending["id"] = cell["outer"].after(
                _CLICK_DELAY_MS,
                lambda: self._on_cell_click(scene_num),
            )

        def on_double(_e) -> None:
            if pending["id"]:
                cell["outer"].after_cancel(pending["id"])
                pending["id"] = None
            self._on_cell_double_click(scene_num)

        for w in (cell["outer"], cell["border"], cell["img_lbl"], cell["name_lbl"]):
            w.bind("<Button-1>", on_single)
            w.bind("<Double-Button-1>", on_double)
            self._bind_mousewheel(w)

    def _on_cell_double_click(self, scene_num: str) -> None:
        cell = self._cells.get(scene_num)
        if not cell or not self._on_video_select:
            return
        video: Path = cell["video"]
        self._on_video_select(video)
        self._log(f"素材库：双击选定 {video.name}")

    def _on_cell_click(self, scene_num: str) -> None:
        uploaded = self._is_uploaded(scene_num)
        self._toggle_uploaded(scene_num, not uploaded)
        cell = self._cells.get(scene_num)
        if cell:
            self._apply_cell_style(cell)
        self._update_stats()
        state = "已上传" if not uploaded else "未上传"
        self._log(f"素材库：MVI_{scene_num} → 标记为{state}")

    def _update_stats(self) -> None:
        total = len(self._cells)
        done = sum(1 for n in self._cells if self._is_uploaded(n))
        self.lbl_stats.configure(text=f"共 {total} 个 · 已上传 {done} · 待上传 {total - done}")
