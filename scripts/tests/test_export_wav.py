"""导出 WAV 时长校验。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from gui.export_wav import (
    format_mp4_export_stats_suffix,
    format_size_compact_bytes,
    wav_matches_target_hours,
)


def test_wav_matches_target_hours(tmp_path: Path) -> None:
    fake = tmp_path / "x.wav"
    fake.write_bytes(b"x")
    with patch("gui.export_wav.wav_duration_seconds", return_value=3 * 3600 + 5):
        assert wav_matches_target_hours(fake, 3.0)
    with patch("gui.export_wav.wav_duration_seconds", return_value=3600.0):
        assert not wav_matches_target_hours(fake, 3.0)


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
