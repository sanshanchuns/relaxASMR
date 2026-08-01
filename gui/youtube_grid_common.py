"""YouTube 相关 Tab 共用的宫格渲染逻辑（远程封面 + 标题省略号 + 点击/双击）。"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Callable

from PIL import Image, ImageTk

from gui.ui_theme import GridTheme

CELL_W = 176
CELL_H = 99
CELL_PAD = 6
TITLE_LINES = 2
TITLE_CHARS_PER_LINE = 22
_CLICK_DELAY_MS = 260

# 已做过 LLM 优点分析的视频宫格高亮边框色（黄色，浅/深色主题下都醒目）。
ANALYZED_BORDER_COLOR = "#FFC107"
ANALYZED_BORDER_THICKNESS = 3


def truncate_title(text: str, *, max_chars: int = TITLE_LINES * TITLE_CHARS_PER_LINE) -> str:
    """过长标题裁剪并加省略号，避免撑破宫格。"""
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "…"


def load_local_image(path: Path | None, *, target_w: int, target_h: int) -> Image.Image | None:
    """把本地缩略图文件缩放居中贴到固定尺寸画布（无图返回 None）。"""
    if path is None:
        return None
    try:
        img = Image.open(path).convert("RGB")
    except OSError:
        return None
    iw, ih = img.size
    if iw <= 0 or ih <= 0:
        return None
    scale = min(target_w / iw, target_h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_w, target_h), "#2a2a2a")
    ox, oy = (target_w - nw) // 2, (target_h - nh) // 2
    canvas.paste(resized, (ox, oy))
    return canvas


def compute_cols(container_width: int, *, cell_w: int = CELL_W, min_cols: int = 2) -> int:
    if container_width <= 1:
        return min_cols + 1
    return max(min_cols, container_width // (cell_w + CELL_PAD * 2))


def build_grid_cell(
    host: tk.Widget,
    *,
    row: int,
    col: int,
    title: str,
    subtitle: str = "",
    image: Image.Image | None,
    theme: GridTheme,
    photo_refs: list[ImageTk.PhotoImage],
    on_click: Callable[[], None] | None = None,
    on_double_click: Callable[[], None] | None = None,
    cell_w: int = CELL_W,
    cell_h: int = CELL_H,
    highlighted: bool = False,
) -> dict:
    """渲染单个宫格（封面 + 省略号标题 + 可选副标题），返回内部控件引用字典。

    ``highlighted``：已做过 LLM 优点分析的视频用黄色边框高亮标记。
    """
    # 42 而非 32：爆款分析宫格的副标题可能是「日均播放+总播放+发布时间」三项拼接，
    # 加了 wraplength 后偶尔会换成两行，留一点余量避免第二行被裁掉。
    label_h = 42 if subtitle else 18

    outer = tk.Frame(
        host,
        width=cell_w + CELL_PAD,
        height=cell_h + label_h + CELL_PAD,
        cursor="hand2",
        bg=theme.cell_bg,
    )
    outer.grid(row=row, column=col, padx=CELL_PAD, pady=CELL_PAD)
    outer.grid_propagate(False)

    border = tk.Frame(
        outer,
        bg=theme.cell_bg,
        highlightthickness=ANALYZED_BORDER_THICKNESS if highlighted else 2,
        highlightbackground=ANALYZED_BORDER_COLOR if highlighted else theme.border_default,
        highlightcolor=ANALYZED_BORDER_COLOR if highlighted else theme.border_hover,
    )
    border.pack(fill=tk.BOTH, expand=True)

    img_lbl = tk.Label(border, bd=0, relief=tk.FLAT, bg=theme.cell_bg)
    img_lbl.pack(fill=tk.BOTH, expand=True, padx=1, pady=(1, 0))
    if image is not None:
        photo = ImageTk.PhotoImage(image)
        photo_refs.append(photo)
        img_lbl.configure(image=photo, text="")
    else:
        img_lbl.configure(image="", text="加载中…", fg="#999999")

    title_lbl = tk.Label(
        border,
        text=truncate_title(title),
        font=("", 8),
        fg=theme.fg_default,
        bg=theme.cell_bg,
        anchor=tk.CENTER,
        justify=tk.CENTER,
        wraplength=cell_w - 6,
    )
    title_lbl.pack(fill=tk.X, pady=(0, 0 if subtitle else 2))

    subtitle_lbl = None
    if subtitle:
        subtitle_lbl = tk.Label(
            border,
            text=subtitle,
            font=("", 7),
            fg=theme.fg_muted,
            bg=theme.cell_bg,
            anchor=tk.CENTER,
            justify=tk.CENTER,
            wraplength=cell_w - 4,
        )
        subtitle_lbl.pack(fill=tk.X, pady=(0, 2))

    cell = {
        "outer": outer,
        "border": border,
        "img_lbl": img_lbl,
        "title_lbl": title_lbl,
        "subtitle_lbl": subtitle_lbl,
        "analyzed": highlighted,
    }

    pending: dict[str, str | None] = {"id": None}

    def _on_single(_e=None) -> None:
        if not on_click:
            return
        if pending["id"]:
            outer.after_cancel(pending["id"])
        pending["id"] = outer.after(_CLICK_DELAY_MS, on_click)

    def _on_double(_e=None) -> None:
        if pending["id"]:
            outer.after_cancel(pending["id"])
            pending["id"] = None
        if on_double_click:
            on_double_click()

    widgets = [outer, border, img_lbl, title_lbl] + ([subtitle_lbl] if subtitle_lbl else [])
    for w in widgets:
        w.bind("<Button-1>", _on_single)
        w.bind("<Double-Button-1>", _on_double)

    return cell


def set_cell_image(cell: dict, image: Image.Image | None, photo_refs: list[ImageTk.PhotoImage]) -> None:
    """异步下载完成后回填封面图（首次渲染时可能还没下载好）。"""
    img_lbl = cell.get("img_lbl")
    if img_lbl is None:
        return
    if image is None:
        img_lbl.configure(image="", text="无预览")
        return
    photo = ImageTk.PhotoImage(image)
    photo_refs.append(photo)
    img_lbl.configure(image=photo, text="")


def mark_cell_analyzed(cell: dict) -> None:
    """LLM 分析完成后，把该宫格边框标记为黄色高亮（无需重新渲染整个宫格）。"""
    border = cell.get("border")
    if border is None or cell.get("analyzed"):
        return
    cell["analyzed"] = True
    border.configure(
        highlightthickness=ANALYZED_BORDER_THICKNESS,
        highlightbackground=ANALYZED_BORDER_COLOR,
        highlightcolor=ANALYZED_BORDER_COLOR,
    )


def bind_mousewheel_deep(widget: tk.Widget, handler: Callable[..., None]) -> None:
    """递归给 widget 及其所有子孙控件绑定滚轮事件。

    宫格内容嵌套很深（LabelFrame → Frame → Frame(border) → Label），Tk 的
    ``<MouseWheel>`` 只会派发给鼠标正下方的具体控件，不会像浏览器那样向上冒泡到
    祖先控件；只在最外层 canvas/host 上 bind 会导致「必须把鼠标移到宫格之间的
    空隙才能滚动」。因此宫格渲染完成后需要对整棵子树逐一绑定。
    """
    widget.bind("<MouseWheel>", handler, add="+")
    widget.bind("<Button-4>", handler, add="+")
    widget.bind("<Button-5>", handler, add="+")
    for child in widget.winfo_children():
        bind_mousewheel_deep(child, handler)


def highlight_cell(cell: dict, theme: GridTheme, *, selected: bool) -> None:
    border = cell.get("border")
    if border is None:
        return
    border.configure(
        highlightbackground=theme.border_selected if selected else theme.border_default,
        highlightcolor=theme.border_hover,
    )


__all__ = [
    "CELL_W",
    "CELL_H",
    "CELL_PAD",
    "truncate_title",
    "load_local_image",
    "compute_cols",
    "build_grid_cell",
    "set_cell_image",
    "bind_mousewheel_deep",
    "highlight_cell",
]
