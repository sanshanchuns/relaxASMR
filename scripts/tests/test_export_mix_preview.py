"""混音预览宫格状态。"""

from pathlib import Path
from unittest.mock import MagicMock

from gui.export_mix_preview import ExportMixPreviewGrid


def test_export_mix_preview_playable_when_wav_valid(tmp_path: Path) -> None:
    wav = tmp_path / "mix.wav"
    wav.write_bytes(b"x")
    grid = ExportMixPreviewGrid(MagicMock(), log_fn=lambda _m: None)
    grid.set_status("已完成 · export/mix.wav", wav_path=wav, running=False)
    assert grid._playable is True
    assert grid._wav_path == wav.resolve()


def test_export_mix_preview_not_playable_when_running(tmp_path: Path) -> None:
    wav = tmp_path / "mix.wav"
    wav.write_bytes(b"x")
    grid = ExportMixPreviewGrid(MagicMock(), log_fn=lambda _m: None)
    grid.set_status("Elapsed: 00:01:00", wav_path=wav, running=True)
    assert grid._playable is False


def test_export_mix_preview_not_playable_without_wav() -> None:
    grid = ExportMixPreviewGrid(MagicMock(), log_fn=lambda _m: None)
    grid.set_status("待开始", wav_path=None, running=False)
    assert grid._playable is False
