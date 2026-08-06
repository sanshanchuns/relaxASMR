"""导出 WAV 时长校验。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from gui.export_wav import (
    export_mp4_belongs_to_scene,
    export_wav_belongs_to_scene,
    find_export_mp4_for_scene,
    find_export_wav_for_scene,
    format_mp4_export_stats_suffix,
    format_size_compact_bytes,
    wav_matches_target_minutes,
)


def test_wav_matches_target_minutes(tmp_path: Path) -> None:
    fake = tmp_path / "x.wav"
    fake.write_bytes(b"x")
    with patch("gui.export_wav.wav_duration_seconds", return_value=180 * 60 + 5):
        assert wav_matches_target_minutes(fake, 180.0)
    with patch("gui.export_wav.wav_duration_seconds", return_value=3600.0):
        assert not wav_matches_target_minutes(fake, 180.0)


def test_format_size_compact_bytes() -> None:
    assert format_size_compact_bytes(10 * 1024**3) == "10G"
    assert format_size_compact_bytes(int(1.5 * 1024**3)) == "1.5G"
    assert format_size_compact_bytes(500 * 1024**2) == "500M"


def test_format_mp4_export_stats_suffix(tmp_path: Path) -> None:
    mp4 = tmp_path / "a.mp4"
    mp4.write_bytes(b"x" * 100)
    with patch("gui.export_wav.probe_format_bitrate_bps", return_value=6_200_000):
        suffix = format_mp4_export_stats_suffix(mp4)
        assert "6.2 Mbps" in suffix
        assert suffix.endswith("0M")


def test_export_mp4_belongs_to_scene(tmp_path: Path) -> None:
    own = tmp_path / "MVI_7004_180min_fhd.mp4"
    other = tmp_path / "MVI_6989_180min_fhd.mp4"
    legacy = tmp_path / "MVI_7004_3h_fhd.mp4"
    own.write_bytes(b"x")
    other.write_bytes(b"x")
    legacy.write_bytes(b"x")
    assert export_mp4_belongs_to_scene(own, "MVI_7004", minutes=180.0)
    assert export_mp4_belongs_to_scene(legacy, "MVI_7004", minutes=180.0)
    assert not export_mp4_belongs_to_scene(other, "MVI_7004", minutes=180.0)
    assert not export_mp4_belongs_to_scene(own, "MVI_7004", minutes=120.0)


def test_export_wav_belongs_to_scene(tmp_path: Path) -> None:
    own = tmp_path / "MVI_7004_180min.wav"
    other = tmp_path / "MVI_6989_180min.wav"
    legacy = tmp_path / "MVI_7004_3h.wav"
    own.write_bytes(b"x")
    other.write_bytes(b"x")
    legacy.write_bytes(b"x")
    assert export_wav_belongs_to_scene(own, "MVI_7004", minutes=180.0)
    assert export_wav_belongs_to_scene(legacy, "MVI_7004", minutes=180.0)
    assert not export_wav_belongs_to_scene(other, "MVI_7004", minutes=180.0)
    assert not export_wav_belongs_to_scene(own, "MVI_7004", minutes=120.0)


def test_find_export_wav_for_scene_legacy_3h(tmp_path: Path) -> None:
    legacy = tmp_path / "MVI_7047_3h.wav"
    legacy.write_bytes(b"ok")
    found = find_export_wav_for_scene("MVI_7047", minutes=180.0, export_root=tmp_path)
    assert found == legacy


def test_find_export_wav_for_scene(tmp_path: Path) -> None:
    old = tmp_path / "MVI_7004_180min.wav"
    newer = tmp_path / "MVI_7004_3h.wav"
    wrong = tmp_path / "MVI_6989_180min.wav"
    old.write_bytes(b"old")
    newer.write_bytes(b"newer")
    wrong.write_bytes(b"wrong")
    old_ts = 1_000_000_000
    newer_ts = 2_000_000_000
    old.touch()
    newer.touch()
    import os

    os.utime(old, (old_ts, old_ts))
    os.utime(newer, (newer_ts, newer_ts))
    found = find_export_wav_for_scene("MVI_7004", minutes=180.0, export_root=tmp_path)
    assert found == newer


def test_find_export_mp4_for_scene_legacy_3h(tmp_path: Path) -> None:
    legacy = tmp_path / "MVI_6922_3h_fhd.mp4"
    legacy.write_bytes(b"ok")
    found = find_export_mp4_for_scene("MVI_6922", minutes=180.0, export_root=tmp_path)
    assert found == legacy


def test_find_export_mp4_for_scene(tmp_path: Path) -> None:
    old = tmp_path / "MVI_7004_180min_fhd.mp4"
    newer = tmp_path / "MVI_7004_180min_4k.mp4"
    wrong = tmp_path / "MVI_6989_180min_fhd.mp4"
    old.write_bytes(b"old")
    newer.write_bytes(b"newer")
    wrong.write_bytes(b"wrong")
    old_ts = 1_000_000_000
    newer_ts = 2_000_000_000
    old.touch()
    newer.touch()
    import os

    os.utime(old, (old_ts, old_ts))
    os.utime(newer, (newer_ts, newer_ts))
    found = find_export_mp4_for_scene("MVI_7004", minutes=180.0, export_root=tmp_path)
    assert found == newer
