"""GUI 工程配方：仅依据步骤 2 宫格选中。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Reaper" / "scripts"))

from rain_subproject_lib import build_scene_config_from_gui


def test_build_scene_config_only_uses_grid_selection(tmp_path: Path, monkeypatch) -> None:
    video = tmp_path / "MVI_9999_loop.mp4"
    video.write_bytes(b"v")
    rain = tmp_path / "rain.wav"
    wild = tmp_path / "wild.wav"
    rain.write_bytes(b"x")
    wild.write_bytes(b"y")

    monkeypatch.setattr(
        "rain_subproject_lib.ensure_video_in_assets",
        lambda _v, _s: (video, "assets/video/MVI_9999_loop.mp4"),
    )
    monkeypatch.setattr(
        "scripts.new_reaper_project.audio_loudness.adjust_1_rain_layer_vol",
        lambda cfg, **_: None,
    )

    cfg = build_scene_config_from_gui(
        video,
        scene_id="MVI_9999",
        duration_hours=3.0,
        selected_tracks={"1_rain": rain, "4_wildlife": wild},
    )

    rain_layer = next(l for l in cfg["loop_layers"] if l["id"] == "1_rain")
    assert rain_layer["paths"]
    assert Path(rain_layer["paths"][0]).name == "rain.wav"

    random_layer = next(l for l in cfg["scatter_layers"] if l["id"] == "3_random")
    assert random_layer["paths"] == []

    wild_layer = next(l for l in cfg["scatter_layers"] if l["id"] == "4_wildlife")
    assert Path(wild_layer["paths"][0]).name == "wild.wav"


def test_build_scene_config_empty_layers_when_unselected(tmp_path: Path, monkeypatch) -> None:
    video = tmp_path / "MVI_9999_loop.mp4"
    video.write_bytes(b"v")

    monkeypatch.setattr(
        "rain_subproject_lib.ensure_video_in_assets",
        lambda _v, _s: (video, "assets/video/MVI_9999_loop.mp4"),
    )
    monkeypatch.setattr(
        "scripts.new_reaper_project.audio_loudness.adjust_1_rain_layer_vol",
        lambda cfg, **_: None,
    )

    cfg = build_scene_config_from_gui(video, scene_id="MVI_9999", selected_tracks={})

    assert all(not layer.get("paths") for layer in cfg["loop_layers"])
    assert all(not layer.get("paths") for layer in cfg["scatter_layers"])
