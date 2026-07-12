"""稀疏层推子：3_random LUFS 动态 / 2、4 legacy。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scripts.new_reaper_project.audio_loudness import (
    SCATTER_LEGACY_TRACK_VOL,
    adjust_3_random_layer_vol,
    apply_scatter_layer_vols,
    vol_for_target_lufs,
)


def _cfg_with_scatter(paths: dict[str, Path]) -> dict:
    layers = []
    for i, (lid, p) in enumerate(paths.items(), start=2):
        layers.append({"track": i, "id": lid, "paths": [str(p)]})
    return {"scatter_layers": layers}


def test_apply_scatter_legacy_vol_for_2_and_4(tmp_path: Path) -> None:
    impact = tmp_path / "hit.wav"
    wild = tmp_path / "bird.wav"
    impact.write_bytes(b"x")
    wild.write_bytes(b"y")
    cfg = _cfg_with_scatter({"2_impact": impact, "4_wildlife": wild})

    with patch(
        "scripts.new_reaper_project.audio_loudness.adjust_3_random_layer_vol",
        return_value=None,
    ):
        apply_scatter_layer_vols(cfg)

    impact_layer = next(l for l in cfg["scatter_layers"] if l["id"] == "2_impact")
    wild_layer = next(l for l in cfg["scatter_layers"] if l["id"] == "4_wildlife")
    assert impact_layer["vol"] == SCATTER_LEGACY_TRACK_VOL["2_impact"]
    assert wild_layer["vol"] == SCATTER_LEGACY_TRACK_VOL["4_wildlife"]


def test_adjust_3_random_uses_offset_below_rain_target(tmp_path: Path) -> None:
    boom = tmp_path / "boom.wav"
    boom.write_bytes(b"x")
    cfg = _cfg_with_scatter({"3_random": boom})

    with patch(
        "scripts.new_reaper_project.audio_loudness.measure_lufs_i",
        return_value=-20.0,
    ):
        with patch(
            "scripts.new_reaper_project.audio_loudness.resolve_lufs_target",
            return_value=(-28.0, -28.0, -28.0),
        ):
            with patch(
                "scripts.new_reaper_project.audio_loudness.resolve_3_random_lufs_offset_db",
                return_value=-10.0,
            ):
                info = adjust_3_random_layer_vol(cfg)

    assert info is not None
    assert info["target_lufs"] == -38.0
    random_layer = next(l for l in cfg["scatter_layers"] if l["id"] == "3_random")
    expected = round(vol_for_target_lufs(-20.0, -38.0), 4)
    assert random_layer["vol"] == expected


def test_adjust_3_random_fallback_when_measure_fails(tmp_path: Path) -> None:
    boom = tmp_path / "boom.wav"
    boom.write_bytes(b"x")
    cfg = _cfg_with_scatter({"3_random": boom})

    with patch(
        "scripts.new_reaper_project.audio_loudness.measure_lufs_i",
        return_value=None,
    ):
        adjust_3_random_layer_vol(cfg)

    random_layer = next(l for l in cfg["scatter_layers"] if l["id"] == "3_random")
    assert random_layer["vol"] == 0.35
