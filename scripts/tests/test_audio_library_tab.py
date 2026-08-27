"""素材库 boom 宫格：2_impact 同时列出 sounds/ 与 booms/。"""

import queue
import threading
import time
import tkinter as tk
from pathlib import Path

from gui.audio_library_tab import (
    AudioLibraryTab,
    collect_boom_grid_data,
    list_boom_wavs,
    resolve_boom_dirs,
    wav_display_title,
)
from gui.tk_thread import _QUEUE_ATTR
from scripts.audio.booms_16bit import booms_16bit_path_for


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


def test_impact_lists_sounds_then_booms(tmp_path: Path, monkeypatch) -> None:
    layer = tmp_path / "2_impact"
    sounds = layer / "sounds"
    booms = layer / "booms"
    sounds.mkdir(parents=True)
    booms.mkdir(parents=True)
    (sounds / "中雨_水滴.wav").write_bytes(b"s")
    (booms / "QP01 0017 Stream sparkling.wav").write_bytes(b"b")
    (booms / "not-a-wav.txt").write_text("x")

    monkeypatch.setattr(
        "scripts.config.paths.audio_layer_dir",
        lambda layer_id: sounds if layer_id == "2_impact" else tmp_path / layer_id,
    )
    monkeypatch.setattr(
        "gui.audio_library_tab.audio_booms_dir",
        lambda layer_id: booms if layer_id == "2_impact" else tmp_path / layer_id / "booms",
    )

    dirs = resolve_boom_dirs(layer_id="2_impact")
    assert dirs == [sounds, booms]

    wavs = list_boom_wavs("2_impact")
    assert [p.name for p in wavs] == [
        "中雨_水滴.wav",
        "QP01 0017 Stream sparkling.wav",
    ]
    assert wav_display_title(wavs[0], multi_dir=True) == "sounds/中雨_水滴"
    assert wav_display_title(wavs[1], multi_dir=True) == "booms/QP01 0017 Stream sparkling"
    assert booms_16bit_path_for(wavs[0]) is None
    assert booms_16bit_path_for(wavs[1]) == booms.parent / "booms_16bit" / wavs[1].name


def test_rain_only_lists_booms(tmp_path: Path, monkeypatch) -> None:
    booms = tmp_path / "1_rain" / "booms"
    sounds = tmp_path / "1_rain" / "sounds"
    booms.mkdir(parents=True)
    sounds.mkdir(parents=True)
    (booms / "rain.wav").write_bytes(b"b")
    (sounds / "ignored.wav").write_bytes(b"s")

    monkeypatch.setattr(
        "gui.audio_library_tab.audio_booms_dir",
        lambda layer_id: tmp_path / layer_id / "booms",
    )

    wavs = list_boom_wavs("1_rain")
    assert [p.name for p in wavs] == ["rain.wav"]
    assert wav_display_title(wavs[0]) == "rain"


def test_collect_boom_grid_data_titles_and_keys(tmp_path: Path) -> None:
    (tmp_path / "a.wav").write_bytes(b"a")
    (tmp_path / "b.wav").write_bytes(b"b")
    items, sig, roots = collect_boom_grid_data(booms_dir=tmp_path)
    assert roots == [tmp_path]
    assert [title for _, title, _ in items] == ["a", "b"]
    assert all(key.endswith(".wav") for _, _, key in items)
    assert "a.wav" in sig and "b.wav" in sig


def test_audio_refresh_scans_off_main_thread(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.wav").write_bytes(b"a")
    started = threading.Event()
    release = threading.Event()
    worker_thread = []

    def fake_collect(layer_id: str = "", *, booms_dir=None):
        started.set()
        release.wait(timeout=2)
        worker_thread.append(threading.current_thread() is not threading.main_thread())
        return collect_boom_grid_data(layer_id, booms_dir=booms_dir)

    monkeypatch.setattr("gui.audio_library_tab.collect_boom_grid_data", fake_collect)

    root = tk.Tk()
    root.withdraw()
    try:
        tab = AudioLibraryTab(root, layer_id="3_random", track_id="3_random", booms_dir=tmp_path)
        tab.refresh(force=True)
        assert tab._loading
        assert started.wait(timeout=1)
        assert worker_thread == []
        release.set()
        _pump_until(root, lambda: tab._loaded_once and not tab._loading)
        assert worker_thread == [True]
        assert len(tab._cells) == 1
    finally:
        release.set()
        root.destroy()
