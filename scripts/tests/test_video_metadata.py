"""Tests for raw video metadata helpers."""

from __future__ import annotations

from pathlib import Path

from gui.video_metadata import (
    _format_aperture,
    _format_bitrate,
    _format_color_temp,
    _format_focal,
    _format_iso,
    _format_shutter,
    _parse_fps,
    clear_raw_video_info_cache,
    format_raw_video_detail_text,
    format_raw_video_meta_lines,
    list_dir_videos,
    peek_raw_video_info_cache,
    read_raw_video_info,
)


def test_list_dir_videos_non_recursive(tmp_path: Path) -> None:
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.MOV").write_bytes(b"x")
    (tmp_path / "c.JPG").write_bytes(b"x")
    (tmp_path / "d.jpeg").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.mp4").write_bytes(b"x")
    (tmp_path / ".hidden.mp4").write_bytes(b"x")
    names = [p.name for p in list_dir_videos(tmp_path)]
    assert names == ["a.mp4", "b.MOV", "c.JPG", "d.jpeg"]


def test_format_raw_image_meta_lines() -> None:
    info = {
        "title": "IMG_7305",
        "kind": "image",
        "resolution": "6000×4000",
        "fps": "—",
        "bitrate": "—",
        "iso": "1600",
        "aperture": "f/2.8",
        "shutter": "1/160s",
        "color_temp": "5200K",
        "focal_length": "50mm",
    }
    line1, line2, line3 = format_raw_video_meta_lines(info)
    assert "6000×4000" in line1
    assert "JPG" in line1
    assert "fps" not in line1
    assert "ISO 1600" in line2
    assert "5200K" in line3
    detail = format_raw_video_detail_text(info)
    assert "帧率" not in detail
    assert "码率" not in detail
    assert "ISO：1600" in detail


def test_format_helpers() -> None:
    from gui.video_metadata import _read_sony_f16, _scan_rtmd_tag_value

    assert _parse_fps("30000/1001") == "29.97fps"
    assert _format_aperture("2.8") == "f/2.8"
    assert _format_iso("799.6") == "800"
    assert _format_bitrate(52_000_000) == "52.0Mbps"
    assert _format_shutter("1/50") == "1/50s"
    assert _format_color_temp("5500") == "5500K"
    assert _format_focal("35") == "35mm"
    assert round(_read_sony_f16(bytes.fromhex("c1e0")) * 1000) == 48
    sample = bytes.fromhex("80050002c1e0800b")
    assert _scan_rtmd_tag_value(sample, 0x8005) == bytes.fromhex("c1e0")


def test_format_raw_video_meta_lines() -> None:
    info = {
        "title": "clip",
        "resolution": "3840×2160",
        "fps": "24fps",
        "bitrate": "100Mbps",
        "iso": "800",
        "aperture": "f/2.8",
        "shutter": "1/50s",
        "color_temp": "5500K",
        "focal_length": "35mm",
    }
    line1, line2, line3 = format_raw_video_meta_lines(info)
    assert "3840×2160" in line1
    assert "100Mbps" in line1
    assert "ISO 800" in line2
    assert "5500K" in line3
    detail = format_raw_video_detail_text(info)
    assert "码率：100Mbps" in detail


def test_raw_video_info_cache_roundtrip(tmp_path: Path, monkeypatch) -> None:
    cache_dir = tmp_path / "meta_cache"
    cache_dir.mkdir()
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake-video")

    monkeypatch.setattr("gui.video_metadata._meta_cache_dir", lambda: cache_dir)

    calls = {"n": 0}

    def fake_probe(path: Path) -> dict[str, str]:
        calls["n"] += 1
        assert path == video
        return {
            "title": path.stem,
            "resolution": "1920×1080",
            "fps": "24fps",
            "bitrate": "50Mbps",
            "iso": "800",
            "aperture": "f/2.8",
            "shutter": "1/50s",
            "color_temp": "5500K",
            "focal_length": "35mm",
        }

    monkeypatch.setattr("gui.video_metadata._probe_raw_video_info", fake_probe)
    clear_raw_video_info_cache()

    first = read_raw_video_info(video)
    second = read_raw_video_info(video)
    cached = peek_raw_video_info_cache(video)

    assert calls["n"] == 1
    assert first["resolution"] == "1920×1080"
    assert second == first
    assert cached == first

    video.write_bytes(b"fake-video-updated")
    assert peek_raw_video_info_cache(video) is None
    third = read_raw_video_info(video)
    assert calls["n"] == 2
    assert third["resolution"] == "1920×1080"
