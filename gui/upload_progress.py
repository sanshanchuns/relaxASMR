"""YouTube 上传进度文案。"""

from __future__ import annotations


def should_refresh_upload_progress(pct: int, last_shown: int) -> bool:
    """仅当整数进度相对上次展示变化 ≥1% 时刷新（含 100%）。"""
    pct = max(0, min(100, int(pct)))
    if last_shown < 0:
        return True
    if pct >= 100:
        return pct != last_shown
    return pct - last_shown >= 1


def format_transfer_progress(elapsed: float, pct: int) -> str:
    from gui.reaper_launch import format_hms

    pct = max(0, min(100, int(pct)))
    if pct > 0:
        remain = elapsed * (100 - pct) / pct
        pct_text = f"({pct}%)"
    else:
        remain = 0.0
        pct_text = "(…)"
    return (
        f"Elapsed: {format_hms(elapsed)}  "
        f"Remaining: ~{format_hms(remain)}  {pct_text}"
    )
