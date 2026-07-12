"""将后台线程回调安全调度到 Tk 主线程。"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Any

import tkinter as tk
from tkinter import Misc

_QUEUE_ATTR = "_relaxasmr_ui_queue"
_PUMP_ATTR = "_relaxasmr_ui_pump_started"
_ROOT_REF_ATTR = "_relaxasmr_ui_root"


def ensure_ui_pump(root: Misc) -> None:
    """在根窗口上启动 UI 回调队列泵（可重复调用）。"""
    if getattr(root, _PUMP_ATTR, False):
        return
    setattr(root, _PUMP_ATTR, True)
    if not hasattr(root, _QUEUE_ATTR):
        setattr(root, _QUEUE_ATTR, queue.Queue())

    def pump() -> None:
        if not _widget_exists(root):
            return
        q: queue.Queue = getattr(root, _QUEUE_ATTR)
        try:
            while True:
                job = q.get_nowait()
                try:
                    job()
                except tk.TclError:
                    pass
        except queue.Empty:
            pass
        if _widget_exists(root):
            root.after(50, pump)

    root.after(0, pump)


def bind_ui_root(widget: Misc) -> None:
    """在主线程绑定 widget 所属根窗口（供后台线程投递 UI 回调）。"""
    root = widget.winfo_toplevel()
    setattr(widget, _ROOT_REF_ATTR, root)
    ensure_ui_pump(root)


def schedule_on_main(
    widget: Misc,
    callback: Callable[..., Any],
    /,
    *args: Any,
    **kwargs: Any,
) -> None:
    """从任意线程安全地在 Tk 主线程执行 callback。"""
    def run() -> None:
        if not _widget_exists(widget):
            return
        callback(*args, **kwargs)

    root_ref: Misc | None = getattr(widget, _ROOT_REF_ATTR, None)

    if threading.current_thread() is threading.main_thread():
        if root_ref is None:
            try:
                root_ref = widget.winfo_toplevel()
                bind_ui_root(widget)
                root_ref = getattr(widget, _ROOT_REF_ATTR, root_ref)
            except (RuntimeError, tk.TclError):
                return
        if root_ref is None or not _widget_exists(root_ref):
            return
        try:
            root_ref.after(0, run)
        except RuntimeError:
            q = getattr(root_ref, _QUEUE_ATTR, None)
            if q is not None:
                q.put(run)
        return

    # 后台线程：不可调用任何 Tk API，仅写入队列
    if root_ref is None:
        return
    q = getattr(root_ref, _QUEUE_ATTR, None)
    if q is not None:
        q.put(run)


def _widget_exists(widget: Misc) -> bool:
    try:
        return bool(widget.winfo_exists())
    except tk.TclError:
        return False
