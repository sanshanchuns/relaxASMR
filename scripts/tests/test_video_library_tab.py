"""素材库视频 Tab：目录扫描在后台线程，不阻塞 refresh()。"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path

from gui.raw_video_library_tab import RawVideoLibraryTab
from gui.tk_thread import _QUEUE_ATTR
from gui.video_library_tab import VideoLibraryTab


def _pump_until(root: tk.Tk, pred, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    q: queue.Queue = getattr(root, _QUEUE_ATTR)
    while time.monotonic() < deadline:
        try:
            while True:
                q.get_nowait()()
        except queue.Empty:
            pass
        root.update()
        if pred():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for UI callback")


def test_loop_video_refresh_lists_off_main_thread(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()
    worker_thread = []

    def fake_list():
        started.set()
        release.wait(timeout=2)
        worker_thread.append(threading.current_thread() is not threading.main_thread())
        return []

    monkeypatch.setattr("gui.video_library_tab.list_root_mp4s", fake_list)
    monkeypatch.setattr("gui.video_library_tab.base_url", lambda: Path("/tmp"))

    root = tk.Tk()
    root.withdraw()
    try:
        tab = VideoLibraryTab(
            root,
            is_uploaded=lambda _n: False,
            toggle_uploaded=lambda _n, _v: None,
        )
        tab.refresh(force=True)
        assert tab._loading
        assert started.wait(timeout=1)
        assert worker_thread == []
        release.set()
        _pump_until(root, lambda: tab._loaded_once and not tab._loading)
        assert worker_thread == [True]
    finally:
        release.set()
        root.destroy()


def test_raw_video_refresh_lists_off_main_thread(tmp_path: Path, monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()
    worker_thread = []

    def fake_list(directory: Path):
        started.set()
        release.wait(timeout=2)
        worker_thread.append(threading.current_thread() is not threading.main_thread())
        return []

    monkeypatch.setattr("gui.raw_video_library_tab.list_dir_videos", fake_list)

    root = tk.Tk()
    root.withdraw()
    try:
        tab = RawVideoLibraryTab(
            root,
            get_directory=lambda: str(tmp_path),
            set_directory=lambda _d: None,
        )
        tab.refresh(force=True)
        assert tab._loading
        assert started.wait(timeout=1)
        assert worker_thread == []
        release.set()
        _pump_until(root, lambda: tab._loaded_once and not tab._loading)
        assert worker_thread == [True]
    finally:
        release.set()
        root.destroy()
