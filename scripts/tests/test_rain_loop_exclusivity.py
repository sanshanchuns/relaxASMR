"""1_rain clip/vlm/boom 互斥与 Reaper 映射。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gui.core_controller import (
    collect_selected_tracks_for_reaper,
    is_rain_loop_exclusive_track_name,
)


class _Picker:
    def __init__(self, track_name: str, selected: Path | None) -> None:
        self.track_name = track_name
        self._selected = selected

    def get_selected(self) -> Path | None:
        return self._selected


def test_exclusive_track_names() -> None:
    assert is_rain_loop_exclusive_track_name("1_rain_clip")
    assert is_rain_loop_exclusive_track_name("1_rain_vlm")
    assert is_rain_loop_exclusive_track_name("1_rain_boom")
    assert is_rain_loop_exclusive_track_name("1_rain")
    assert not is_rain_loop_exclusive_track_name("3_random")


def test_collect_single_rain_boom() -> None:
    boom = Path("/tmp/boom.wav")
    pickers = {
        "1_rain": _Picker("1_rain_clip", None),
        "1_rain_vlm": _Picker("1_rain_vlm", None),
        "1_rain_boom": _Picker("1_rain_boom", boom),
        "3_random": _Picker("3_random", Path("/tmp/r.wav")),
    }
    out = collect_selected_tracks_for_reaper(pickers)
    assert out["1_rain"] == boom
    assert out["3_random"] == Path("/tmp/r.wav")
    assert "1_rain_boom" not in out


def test_collect_priority_when_multiple(tmp_path: Path) -> None:
    clip = tmp_path / "clip.wav"
    vlm = tmp_path / "vlm.wav"
    boom = tmp_path / "boom.wav"
    pickers = {
        "1_rain": _Picker("1_rain_clip", clip),
        "1_rain_vlm": _Picker("1_rain_vlm", vlm),
        "1_rain_boom": _Picker("1_rain_boom", boom),
    }
    out = collect_selected_tracks_for_reaper(pickers)
    assert out["1_rain"] == boom


def test_scatter_empty_when_picker_unselected() -> None:
    pickers = {"4_wildlife": _Picker("4_wildlife", None)}
    out = collect_selected_tracks_for_reaper(pickers)
    assert "4_wildlife" not in out


def test_scatter_fallback_ignored_without_picker_selection(tmp_path: Path) -> None:
    """宫格未选中时不会写入该散布层。"""
    wild = tmp_path / "wildlife.wav"
    wild.write_bytes(b"x")
    pickers = {"4_wildlife": _Picker("4_wildlife", None)}
    out = collect_selected_tracks_for_reaper(pickers)
    assert "4_wildlife" not in out
