"""GUI 浅色 / 深色主题。"""

from __future__ import annotations

import os
from dataclasses import dataclass

import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True)
class UiTheme:
    name: str
    window_bg: str
    fg: str
    text_bg: str
    canvas_bg: str
    entry_bg: str
    entry_fg: str
    select_bg: str
    select_fg: str
    trough: str


@dataclass(frozen=True)
class GridTheme:
    """九宫格 / 素材库宫格配色（须显式设置 bg，避免 macOS 跟随系统深浅色）。"""

    cell_bg: str
    fg_default: str
    fg_muted: str
    fg_hover: str
    fg_selected: str
    fg_pinned: str
    border_default: str
    border_hover: str
    border_selected: str
    border_pinned: str
    border_uploaded: str


LIGHT = UiTheme(
    name="light",
    window_bg="#f3f3f3",
    fg="#1a1a1a",
    text_bg="#ffffff",
    canvas_bg="#ffffff",
    entry_bg="#ffffff",
    entry_fg="#1a1a1a",
    select_bg="#cce4f7",
    select_fg="#1a1a1a",
    trough="#e0e0e0",
)

DARK = UiTheme(
    name="dark",
    window_bg="#1e1e1e",
    fg="#e8e8e8",
    text_bg="#252526",
    canvas_bg="#2d2d2d",
    entry_bg="#3c3c3c",
    entry_fg="#e8e8e8",
    select_bg="#264f78",
    select_fg="#ffffff",
    trough="#3a3a3a",
)

PRIMARY_BG = "#0078d4"
PRIMARY_FG = "#ffffff"
PRIMARY_DISABLED_BG = "#9eb9d4"
PRIMARY_ACTIVE_BG = "#005a9e"
PRIMARY_PRESSED_BG = "#004578"


def normalize_theme(name: str | None) -> str:
    if name and str(name).lower().startswith("dark"):
        return "dark"
    return "light"


def get_theme(name: str | None) -> UiTheme:
    return DARK if normalize_theme(name) == "dark" else LIGHT


def grid_theme(theme: UiTheme) -> GridTheme:
    if theme.name == "dark":
        return GridTheme(
            cell_bg=theme.entry_bg,
            fg_default=theme.fg,
            fg_muted="#999999",
            fg_hover="#6eb5ff",
            fg_selected="#ffffff",
            fg_pinned="#D4A8A8",
            border_default="#555555",
            border_hover="#4a90d9",
            border_selected="#e8e8e8",
            border_pinned="#B07A7A",
            border_uploaded="#666666",
        )
    return GridTheme(
        cell_bg=theme.text_bg,
        fg_default="#222222",
        fg_muted="#666666",
        fg_hover="#1a5fb4",
        fg_selected="#000000",
        fg_pinned="#8B5E5E",
        border_default="#c8c8c8",
        border_hover="#4a90d9",
        border_selected="#000000",
        border_pinned="#A67B7B",
        border_uploaded="#888888",
    )


def paint_widget_bg(bg: str, *widgets: tk.Widget | None) -> None:
    for widget in widgets:
        if widget is None:
            continue
        try:
            widget.configure(bg=bg)
        except tk.TclError:
            pass


def theme_toggle_label(mode: str) -> str:
    return "浅色模式" if normalize_theme(mode) == "dark" else "深色模式"


def _ime_entry_font(parent: tk.Misc) -> tuple[str, int]:
    """WSLg 优先用 Windows 同步的中文字体，便于微信输入法候选与上屏。"""
    for family in (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "SimHei",
        "PingFang SC",
        "WenQuanYi Micro Hei",
        "Noto Sans CJK SC",
    ):
        try:
            probe = f"_ime_font_{family.replace(' ', '_')}"
            parent.tk.call("font", "create", probe, "-family", family, "-size", 10)
            parent.tk.call("font", "delete", probe)
            return (family, 10)
        except tk.TclError:
            continue
    return ("", 10)


def make_ime_entry(
    parent: tk.Misc,
    textvariable: tk.StringVar | None = None,
    *,
    width: int = 16,
    theme: UiTheme | None = None,
) -> tk.Entry:
    """单行输入框。Linux/WSL 下 ``ttk.Entry`` 常无法输入中文，故用 ``tk.Entry``。"""
    palette = theme or LIGHT
    kwargs: dict = {
        "width": width,
        "font": _ime_entry_font(parent) if os.environ.get("WSL_DISTRO_NAME") else ("", 10),
        "bg": palette.entry_bg,
        "fg": palette.entry_fg,
        "insertbackground": palette.entry_fg,
        "selectbackground": palette.select_bg,
        "selectforeground": palette.select_fg,
        "relief": tk.FLAT,
        "highlightthickness": 1,
        "highlightbackground": palette.trough,
        "highlightcolor": palette.trough,
    }
    if textvariable is not None:
        kwargs["textvariable"] = textvariable
    return tk.Entry(parent, **kwargs)


def style_ime_entry(entry: tk.Entry, theme: UiTheme) -> None:
    entry.configure(
        bg=theme.entry_bg,
        fg=theme.entry_fg,
        insertbackground=theme.entry_fg,
        selectbackground=theme.select_bg,
        selectforeground=theme.select_fg,
        highlightbackground=theme.trough,
        highlightcolor=theme.trough,
    )


def ensure_clam_style(style: ttk.Style) -> None:
    try:
        if style.theme_use() not in ("clam", "alt"):
            style.theme_use("clam")
    except tk.TclError:
        pass


def apply_primary_button_style(style: ttk.Style) -> str:
    ensure_clam_style(style)
    style.configure(
        "Primary.TButton",
        foreground=PRIMARY_FG,
        background=PRIMARY_BG,
        font=("", 10, "bold"),
        padding=(10, 5),
    )
    style.map(
        "Primary.TButton",
        background=[
            ("disabled", PRIMARY_DISABLED_BG),
            ("active", PRIMARY_ACTIVE_BG),
            ("pressed", PRIMARY_PRESSED_BG),
        ],
        foreground=[("disabled", "#f0f4f8")],
    )
    return "Primary.TButton"


def apply_ttk_theme(style: ttk.Style, theme: UiTheme) -> None:
    ensure_clam_style(style)
    bg = theme.window_bg
    fg = theme.fg
    style.configure(".", background=bg, foreground=fg)
    style.configure("TFrame", background=bg)
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("TLabelframe", background=bg, foreground=fg, bordercolor=theme.trough)
    style.configure("TLabelframe.Label", background=bg, foreground=fg)
    style.configure("TButton", background=theme.trough, foreground=fg)
    style.map(
        "TButton",
        background=[("active", theme.entry_bg), ("pressed", theme.trough)],
        foreground=[("disabled", "#888888")],
    )
    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=theme.trough,
        foreground=fg,
        padding=(10, 4),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", theme.text_bg), ("active", theme.entry_bg)],
        foreground=[("selected", fg)],
    )
    style.configure(
        "TEntry",
        fieldbackground=theme.entry_bg,
        foreground=theme.entry_fg,
        insertcolor=theme.entry_fg,
    )
    style.configure(
        "TCombobox",
        fieldbackground=theme.entry_bg,
        foreground=theme.entry_fg,
        background=theme.trough,
        arrowcolor=fg,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", theme.entry_bg)],
        foreground=[("readonly", theme.entry_fg)],
    )
    style.configure("TCheckbutton", background=bg, foreground=fg)
    style.map("TCheckbutton", background=[("active", bg)])
    style.configure("Horizontal.TPanedwindow", background=bg)
    style.configure("Vertical.TPanedwindow", background=bg)
    style.configure("TScrollbar", background=theme.trough, troughcolor=bg)
    apply_primary_button_style(style)


def apply_tk_theme(root: tk.Misc, theme: UiTheme, widgets: dict[str, tk.Widget | list[tk.Widget]]) -> None:
    root.configure(bg=theme.window_bg)
    canvas_keys = (
        "cover_canvas",
        "preview_canvas",
        "left_scroll_canvas",
        "library_canvas",
        "video_library_canvas",
        "library_canvases",
    )
    for key in canvas_keys:
        w = widgets.get(key)
        if w is None:
            continue
        if isinstance(w, list):
            for item in w:
                item.configure(bg=theme.canvas_bg)
        else:
            w.configure(bg=theme.canvas_bg)
    for key in ("cover_title", "preview_title"):
        w = widgets.get(key)
        if w is not None:
            w.configure(bg=theme.window_bg, fg=theme.fg)
    for key in ("cover_desc", "preview_desc", "log_text"):
        w = widgets.get(key)
        if w is not None:
            w.configure(
                bg=theme.text_bg,
                fg=theme.fg,
                insertbackground=theme.fg,
                selectbackground=theme.select_bg,
                selectforeground=theme.select_fg,
            )
