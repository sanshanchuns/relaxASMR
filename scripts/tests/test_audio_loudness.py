"""1_rain LUFS 默认目标。"""

from unittest.mock import patch

from scripts.new_reaper_project.audio_loudness import resolve_lufs_target


def test_default_lufs_target_is_minus_28() -> None:
    with patch(
        "scripts.new_reaper_project.audio_loudness._read_user_audio_cfg",
        return_value={},
    ):
        lo, hi, center = resolve_lufs_target()
    assert lo == hi == center == -28.0
