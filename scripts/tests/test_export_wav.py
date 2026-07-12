"""导出 WAV 时长校验。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from gui.export_wav import wav_matches_target_hours


def test_wav_matches_target_hours(tmp_path: Path) -> None:
    fake = tmp_path / "x.wav"
    fake.write_bytes(b"x")
    with patch("gui.export_wav.wav_duration_seconds", return_value=3 * 3600 + 5):
        assert wav_matches_target_hours(fake, 3.0)
    with patch("gui.export_wav.wav_duration_seconds", return_value=3600.0):
        assert not wav_matches_target_hours(fake, 3.0)
