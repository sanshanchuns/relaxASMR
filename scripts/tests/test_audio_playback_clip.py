"""混音试听片段截取。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from gui.audio_playback import (
    DEFAULT_PREVIEW_CLIP_SEC,
    _PREVIEW_CLIP_MIN_BYTES,
    _launch_wav,
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


def test_wsl_large_wav_uses_soundplayer_not_ffplay(tmp_path: Path) -> None:
    wav = tmp_path / "QP03 0300 Rain strong consistent.wav"
    wav.write_bytes(b"x" * (_PREVIEW_CLIP_MIN_BYTES + 1))
    sound_proc = MagicMock(name="soundplayer")
    with patch("gui.reaper_launch.is_wsl", return_value=True):
        with patch("gui.audio_playback._play_wsl_soundplayer", return_value=sound_proc) as sp:
            with patch("gui.audio_playback._start_large_wav") as ffplay:
                out = _launch_wav(wav, loop=True)
    assert out is sound_proc
    sp.assert_called_once_with(wav.resolve(), loop=True)
    ffplay.assert_not_called()
