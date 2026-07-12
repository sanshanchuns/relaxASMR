"""booms → booms_16bit 持久化缓存。"""

from pathlib import Path
from unittest.mock import patch

from gui.audio_playback import _S16_CACHE, _wav_for_legacy_player
from scripts.audio.booms_16bit import (
    booms_16bit_path_for,
    ensure_booms_16bit,
    is_booms_16bit_fresh,
    prewarm_booms_16bit,
)


def test_booms_16bit_path_for_under_booms(tmp_path: Path) -> None:
    wav = tmp_path / "1_rain" / "booms" / "foo.wav"
    wav.parent.mkdir(parents=True)
    wav.touch()
    assert booms_16bit_path_for(wav) == tmp_path / "1_rain" / "booms_16bit" / "foo.wav"


def test_booms_16bit_path_for_outside_booms(tmp_path: Path) -> None:
    wav = tmp_path / "1_rain" / "sounds" / "foo.wav"
    wav.parent.mkdir(parents=True)
    wav.touch()
    assert booms_16bit_path_for(wav) is None


def test_wav_for_legacy_player_uses_booms_16bit_l2(tmp_path: Path) -> None:
    _S16_CACHE.clear()
    booms = tmp_path / "1_rain" / "booms"
    booms.mkdir(parents=True)
    src = booms / "foo.wav"
    src.write_bytes(b"src")
    dst = tmp_path / "1_rain" / "booms_16bit" / "foo.wav"
    dst.parent.mkdir(parents=True)
    dst.write_bytes(b"16bit")

    with patch("gui.audio_playback._wav_bits_per_sample", return_value=24):
        out = _wav_for_legacy_player(src)
    assert out == dst
    assert _S16_CACHE[f"{src.resolve()}:{src.stat().st_mtime_ns}"] == dst


def test_wav_for_legacy_player_transcodes_to_booms_16bit(tmp_path: Path) -> None:
    _S16_CACHE.clear()
    booms = tmp_path / "3_random" / "booms"
    booms.mkdir(parents=True)
    src = booms / "wind.wav"
    src.write_bytes(b"src")

    def fake_transcode(src_path: Path, dst_path: Path) -> None:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        dst_path.write_bytes(b"converted")

    with patch("gui.audio_playback._wav_bits_per_sample", return_value=24):
        with patch("gui.audio_playback.which", return_value="/usr/bin/ffmpeg"):
            with patch("scripts.audio.booms_16bit.transcode_wav_to_s16le", side_effect=fake_transcode):
                out = _wav_for_legacy_player(src)
    assert out == tmp_path / "3_random" / "booms_16bit" / "wind.wav"
    assert out.read_bytes() == b"converted"


def test_ensure_booms_16bit_skips_when_fresh(tmp_path: Path) -> None:
    booms = tmp_path / "1_rain" / "booms"
    booms.mkdir(parents=True)
    src = booms / "a.wav"
    src.write_bytes(b"x")
    dst = tmp_path / "1_rain" / "booms_16bit" / "a.wav"
    dst.parent.mkdir(parents=True)
    dst.write_bytes(b"cached")

    with patch("scripts.audio.booms_16bit.wav_bits_per_sample", return_value=24):
        with patch("scripts.audio.booms_16bit.transcode_wav_to_s16le") as transcode:
            out = ensure_booms_16bit(src)
    assert out == dst
    transcode.assert_not_called()
    assert is_booms_16bit_fresh(src, dst)


def test_prewarm_booms_16bit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("scripts.audio.booms_16bit.audio_dir", lambda: tmp_path / "audio")
    audio_root = tmp_path / "audio"
    booms = audio_root / "1_rain" / "booms"
    booms.mkdir(parents=True)
    src = booms / "rain.wav"
    src.write_bytes(b"src")
    converted: list[Path] = []

    def fake_transcode(src_path: Path, dst_path: Path) -> None:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        dst_path.write_bytes(b"ok")
        converted.append(dst_path)

    with patch("scripts.audio.booms_16bit.wav_bits_per_sample", return_value=24):
        with patch("scripts.audio.booms_16bit.transcode_wav_to_s16le", side_effect=fake_transcode):
            skipped, done, failed = prewarm_booms_16bit()
    assert skipped == 0
    assert done == 1
    assert failed == 0
    assert converted == [audio_root / "1_rain" / "booms_16bit" / "rain.wav"]
