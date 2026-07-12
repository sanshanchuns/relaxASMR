"""长任务 Elapsed / Remaining：主线程定时刷新，后台线程只更新百分比。"""

from __future__ import annotations

import re
import time
from collections.abc import Callable

import tkinter as tk
from tkinter import Misc

PROGRESS_TICK_MS = 250

_PROGRESS_PCT_RE = re.compile(r"\((\d+)%")


def parse_progress_pct(text: str) -> int | None:
    m = _PROGRESS_PCT_RE.search(text)
    if not m:
        return None
    return max(0, min(100, int(m.group(1))))


def make_elapsed_ticker(
    widget: Misc,
    apply_fn: Callable[[str], None],
    *,
    format_status: Callable[[float, int], str],
    interval_ms: int = PROGRESS_TICK_MS,
) -> tuple[Callable[[int], None], Callable[[], None]]:
    """返回 (set_pct, stop)。set_pct 可在任意线程调用。"""
    start = time.monotonic()
    current_pct = [0]
    tick_id: list[str | None] = [None]
    running = [True]

    def refresh() -> None:
        if not running[0]:
            return
        elapsed = time.monotonic() - start
        apply_fn(format_status(elapsed, current_pct[0]))
        try:
            widget.update_idletasks()
        except tk.TclError:
            pass

    def tick() -> None:
        if not running[0]:
            return
        refresh()
        try:
            tick_id[0] = widget.after(interval_ms, tick)
        except tk.TclError:
            tick_id[0] = None

    def set_pct(pct: int) -> None:
        current_pct[0] = max(0, min(100, int(pct)))

    def stop() -> None:
        running[0] = False
        if tick_id[0] is not None:
            try:
                widget.after_cancel(tick_id[0])
            except tk.TclError:
                pass
            tick_id[0] = None

    refresh()
    try:
        tick_id[0] = widget.after(interval_ms, tick)
    except tk.TclError:
        tick_id[0] = None
    return set_pct, stop
