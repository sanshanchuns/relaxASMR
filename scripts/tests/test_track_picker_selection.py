"""步骤 2 九宫格选中恢复。"""

from pathlib import Path
from unittest.mock import MagicMock

from gui.track_picker_ui import TrackPickerUI


def test_select_wav_restores_cell() -> None:
    root = MagicMock()
    picker = TrackPickerUI(root, track_name="1_rain_boom", log_fn=lambda _m: None)
    wav = Path("/tmp/a.wav")
    picker.set_candidates(
        [
            {"wav": str(wav), "name": "A", "score": 100},
            {"wav": "/tmp/b.wav", "name": "B", "score": 99},
        ]
    )
    assert picker.select_wav(wav, notify=False)
    assert picker.get_selected() == wav


def test_select_wav_toggle_deselect() -> None:
    root = MagicMock()
    picker = TrackPickerUI(root, track_name="4_wildlife", log_fn=lambda _m: None)
    wav = Path("/tmp/a.wav")
    picker.set_candidates([{"wav": str(wav), "name": "A", "score": 100}])
    picker.select_cell(0)
    assert picker.get_selected() == wav
    picker.select_cell(0)
    assert picker.get_selected() is None
