"""混音试听片段截取。"""

from pathlib import Path
from unittest.mock import patch

from gui.audio_playback import (
    DEFAULT_PREVIEW_CLIP_SEC,
    _PREVIEW_CLIP_MIN_BYTES,
    wav_preview_clip,
)


def test_wav_preview_clip_small_file_uses_legacy(tmp_path: Path) -> None:
    wav = tmp_path / "short.wav"
    wav.write_bytes(b"x" * 1000)
    with patch("gui.audio_playback._wav_for_legacy_player", return_value=wav) as legacy:
        out = wav_preview_clip(wav)
    legacy.assert_called_once_with(wav)
    assert out == wav


def test_wav_preview_clip_large_file_ffmpeg(tmp_path: Path) -> None:
    wav = tmp_path / "long.wav"
    wav.write_bytes(b"x" * (_PREVIEW_CLIP_MIN_BYTES + 1))
    clip = tmp_path / "clip.wav"
    clip.write_bytes(b"c")

    def fake_run(cmd, **kwargs):
        assert "-t" in cmd
        assert "12.0" in cmd
        clip.write_bytes(b"c")

    with patch("gui.audio_playback.which", return_value="/usr/bin/ffmpeg"):
        with patch("gui.audio_playback.subprocess.run", side_effect=fake_run):
            out = wav_preview_clip(wav, max_seconds=12.0)
    assert out.name.startswith("relaxasmr_clip_")
