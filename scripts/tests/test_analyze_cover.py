"""封面生成：可选雨效。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts.video_analysis.analyze import analyze_video


def _write_jpg(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (16, 16), color).save(path, "JPEG")


def test_analyze_video_plain_cover_skips_rain(tmp_path: Path) -> None:
    video = tmp_path / "MVI_2026_loop.mp4"
    video.write_bytes(b"fake-mp4")
    frame_color = (12, 34, 56)

    def fake_extract(_video_path, out_jpg, on_progress=None):
        del on_progress
        _write_jpg(Path(out_jpg), frame_color)

    with patch("scripts.video_analysis.analyze.extract_first_frame", fake_extract):
        with patch("scripts.video_analysis.cover_composite.composite_rain_cover") as rain:
            result = analyze_video(
                video,
                tmp_path,
                skip_clip=True,
                apply_rain_fx=False,
                force_refresh=True,
            )

    rain.assert_not_called()
    thumb = Path(result["thumbnail_jpg"])
    raw = Path(result["frame_jpg"])
    assert thumb.is_file()
    assert thumb.read_bytes() == raw.read_bytes()
