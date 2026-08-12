"""Read resolution / frame rate (ffprobe) and camera tags (exiftool) from video files."""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

_VIDEO_EXTS = {".mp4", ".mov", ".mxf", ".mkv", ".avi", ".webm"}
_IMAGE_EXTS = {".jpg", ".jpeg"}
_MEDIA_EXTS = _VIDEO_EXTS | _IMAGE_EXTS
_META_CACHE_VERSION = 4
_mem_meta_cache: dict[str, tuple[tuple[int, int], dict[str, str]]] = {}
# Sony rtmd WhiteBalance 枚举（exiftool -n 时为数字）
_SONY_WHITE_BALANCE = {
    "0": "Auto",
    "1": "Daylight",
    "2": "Fluorescent",
    "3": "Tungsten",
    "4": "Flash",
    "5": "Cloudy",
    "6": "Custom",
    "7": "Shade",
}


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in _IMAGE_EXTS


def is_video_path(path: Path) -> bool:
    return path.suffix.lower() in _VIDEO_EXTS


def list_dir_videos(directory: Path) -> list[Path]:
    """Non-recursive list of video / JPG files in *directory*."""
    if not directory.is_dir():
        return []
    out: list[Path] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        if path.name.startswith(".") or path.name.startswith("._"):
            continue
        if path.suffix.lower() not in _MEDIA_EXTS:
            continue
        out.append(path)
    return sorted(out, key=lambda p: p.name.lower())


def _meta_cache_dir() -> Path:
    from scripts.config.paths import material_dir

    d = material_dir() / ".raw_video_meta"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _video_fingerprint(video: Path) -> tuple[int, int]:
    st = video.stat()
    return st.st_mtime_ns, st.st_size


def _meta_cache_path(video: Path) -> Path:
    digest = hashlib.sha1(str(video.resolve()).encode("utf-8")).hexdigest()[:20]
    return _meta_cache_dir() / f"{digest}.json"


def peek_raw_video_info_cache(video: Path) -> dict[str, str] | None:
    """Return cached metadata without probing; ``None`` on cache miss."""
    if not video.is_file():
        return None
    key = str(video.resolve())
    try:
        fingerprint = _video_fingerprint(video)
    except OSError:
        return None
    hit = _mem_meta_cache.get(key)
    if hit and hit[0] == fingerprint:
        info = dict(hit[1])
        info["title"] = video.stem
        return info
    path = _meta_cache_path(video)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("version") != _META_CACHE_VERSION:
        return None
    if payload.get("mtime_ns") != fingerprint[0] or payload.get("size") != fingerprint[1]:
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    info = {str(k): str(v) for k, v in info.items()}
    info["title"] = video.stem
    _mem_meta_cache[key] = (fingerprint, info)
    return info


def _save_raw_video_info_cache(video: Path, info: dict[str, str]) -> None:
    key = str(video.resolve())
    fingerprint = _video_fingerprint(video)
    payload = {
        "version": _META_CACHE_VERSION,
        "path": key,
        "mtime_ns": fingerprint[0],
        "size": fingerprint[1],
        "info": info,
    }
    path = _meta_cache_path(video)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    _mem_meta_cache[key] = (fingerprint, dict(info))


def clear_raw_video_info_cache(video: Path | None = None) -> None:
    """Drop cached metadata for one file, or wipe the whole raw-video meta cache."""
    if video is None:
        _mem_meta_cache.clear()
        cache_dir = _meta_cache_dir()
        for path in cache_dir.glob("*.json"):
            try:
                path.unlink()
            except OSError:
                pass
        return
    key = str(video.resolve())
    _mem_meta_cache.pop(key, None)
    path = _meta_cache_path(video)
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def _first_tag(tags: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = tags.get(key)
        if value in (None, "", [], {}):
            continue
        text = str(value).strip()
        if text and text.lower() not in {"unknown", "n/a", "—"}:
            return text
    return ""


def _parse_fps(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "—"
    if "/" in text:
        try:
            num, den = text.split("/", 1)
            value = float(num) / float(den)
            if value <= 0:
                return "—"
            if abs(value - round(value)) < 0.02:
                return f"{round(value)}fps"
            return f"{value:.2f}fps"
        except (ValueError, ZeroDivisionError):
            return text
    try:
        value = float(text)
        if value <= 0:
            return "—"
        if abs(value - round(value)) < 0.02:
            return f"{round(value)}fps"
        return f"{value:.2f}fps"
    except ValueError:
        return text


def _format_iso(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "—"
    try:
        return str(int(round(float(text))))
    except ValueError:
        return text


def _format_bitrate(raw: object) -> str:
    try:
        bps = float(raw)
    except (TypeError, ValueError):
        return "—"
    if bps <= 0:
        return "—"
    mbps = bps / 1_000_000
    if mbps >= 100:
        return f"{mbps:.0f}Mbps"
    if mbps >= 10:
        return f"{mbps:.1f}Mbps"
    return f"{mbps:.2f}Mbps"


def _format_aperture(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "—"
    if text.lower().startswith("f/"):
        return text
    try:
        value = float(text)
        if value <= 0:
            return "—"
        if abs(value - round(value)) < 0.01:
            return f"f/{round(value):g}"
        return f"f/{round(value, 1):g}"
    except ValueError:
        return text


def _format_shutter(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "—"
    if text.endswith("s") and "/" not in text:
        return text
    if "/" in text:
        return f"{text}s"
    try:
        value = float(text)
        if value <= 0:
            return "—"
        if value >= 1:
            return f"{value:g}s"
        den = round(1 / value)
        return f"1/{den}s"
    except ValueError:
        return text


def _format_color_temp(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "—"
    if text.endswith("K") or text.endswith("k"):
        return text.upper().replace("k", "K")
    if text.isdigit():
        return f"{text}K"
    return text


def _color_temp_from_tags(tags: dict[str, str]) -> str:
    ct = _first_tag(tags, "ColorTemperature")
    if ct:
        formatted = _format_color_temp(ct)
        if formatted != "—":
            return formatted
    wb = _first_tag(tags, "WhiteBalance")
    if wb:
        if wb.isdigit():
            named = _SONY_WHITE_BALANCE.get(wb)
            if named:
                return named
        else:
            return wb
    return "—"


def _focal_from_tags(tags: dict[str, str]) -> str:
    focal = _first_tag(tags, "FocalLength", "FocalLengthIn35mmFormat", "FocalLength35efl")
    if focal:
        return _format_focal(focal)
    return "—"


def _read_sony_f16(raw: bytes) -> float | None:
    if len(raw) < 2:
        return None
    num = struct.unpack(">h", raw[:2])[0]
    exp = (num >> 12) & 0x0F
    if exp >= 8:
        exp = -((~exp & 0x7) + 1)
    return (num & 0x0FFF) * (10**exp)


def _scan_rtmd_tag_value(sample: bytes, tag_id: int) -> bytes | None:
    tag_hi = struct.pack(">H", tag_id)
    pos = 0
    while pos < len(sample) - 4:
        if sample[pos : pos + 2] != tag_hi:
            pos += 1
            continue
        size = struct.unpack_from(">H", sample, pos + 2)[0]
        if size == 0 or size > 64 or pos + 4 + size > len(sample):
            pos += 2
            continue
        return sample[pos + 4 : pos + 4 + size]
    return None


def _rtmd_stream_index(path: Path) -> int | None:
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    cmd = [exe, "-v", "error", "-show_streams", "-of", "json", str(path)]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=20)
        data = json.loads(out)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None
    for stream in data.get("streams") or []:
        if stream.get("codec_tag_string") == "rtmd":
            return int(stream.get("index", -1))
    return None


def _read_sony_rtmd_sample(path: Path, *, max_bytes: int = 65536) -> bytes:
    stream_idx = _rtmd_stream_index(path)
    if stream_idx is None:
        return b""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return b""
    cmd = [
        ffmpeg,
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-map",
        f"0:{stream_idx}",
        "-frames:d",
        "1",
        "-c",
        "copy",
        "-f",
        "data",
        "pipe:1",
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=45)
    except (subprocess.SubprocessError, OSError):
        return b""
    return out[:max_bytes]


def _looks_like_sony_xavc(tags: dict[str, str]) -> bool:
    major = str(tags.get("MajorBrand") or "")
    model = str(tags.get("DeviceModelName") or "")
    meta = str(tags.get("MetaFormat") or "")
    if "XAVC" in major.upper():
        return True
    if model.upper().startswith("ILCE"):
        return True
    if meta.lower() == "rtmd":
        return True
    return False


def read_sony_rtmd_tags(path: Path) -> dict[str, str]:
    """从 Sony XAVC rtmd 轨读取 exiftool 拿不到的焦距 / 色温。"""
    sample = _read_sony_rtmd_sample(path)
    if not sample:
        return {}
    out: dict[str, str] = {}
    focal_raw = _scan_rtmd_tag_value(sample, 0x8005)
    if focal_raw:
        mm = _read_sony_f16(focal_raw)
        if mm is not None and mm > 0:
            out["FocalLength"] = f"{round(mm * 1000):g}"
    if "FocalLength" not in out:
        equiv_raw = _scan_rtmd_tag_value(sample, 0x8004)
        if equiv_raw:
            mm = _read_sony_f16(equiv_raw)
            if mm is not None and mm > 0:
                out["FocalLengthIn35mmFormat"] = f"{round(mm * 1000):g}"
    wb_raw = _scan_rtmd_tag_value(sample, 0x810E)
    if wb_raw and len(wb_raw) >= 2:
        kelvin = struct.unpack(">H", wb_raw[:2])[0]
        if kelvin > 0:
            out["ColorTemperature"] = str(kelvin)
    return out


def _merge_sony_rtmd_tags(tags: dict[str, str], path: Path) -> dict[str, str]:
    if not _looks_like_sony_xavc(tags):
        return tags
    need_focal = not _first_tag(tags, "FocalLength", "FocalLengthIn35mmFormat", "FocalLength35efl")
    need_color = not _first_tag(tags, "ColorTemperature")
    if not need_focal and not need_color:
        return tags
    rtmd = read_sony_rtmd_tags(path)
    if not rtmd:
        return tags
    merged = dict(tags)
    for key, value in rtmd.items():
        if value and not merged.get(key):
            merged[key] = value
    return merged


def _format_focal(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return "—"
    if text.lower().endswith("mm"):
        return text
    try:
        value = float(text)
        if value <= 0:
            return "—"
        return f"{value:g}mm"
    except ValueError:
        return text


def probe_video_stream(path: Path) -> dict[str, Any]:
    exe = shutil.which("ffprobe")
    if not exe:
        return {}
    cmd = [
        exe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,avg_frame_rate",
        "-show_entries",
        "format=bit_rate",
        "-of",
        "json",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=20)
        data = json.loads(out)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return {}
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    if not streams:
        return {"bit_rate": fmt.get("bit_rate")}
    stream = streams[0]
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    fps_raw = stream.get("r_frame_rate") or stream.get("avg_frame_rate") or ""
    return {
        "width": width,
        "height": height,
        "fps_raw": str(fps_raw),
        "bit_rate": fmt.get("bit_rate"),
    }


def read_exif_tags(path: Path) -> dict[str, str]:
    exe = shutil.which("exiftool")
    if not exe:
        return {}
    cmd = [
        exe,
        "-json",
        "-n",
        "-ExtractEmbedded",
        "-ISO",
        "-RecommendedExposureIndex",
        "-FNumber",
        "-ApertureValue",
        "-ShutterSpeed",
        "-ExposureTime",
        "-ColorTemperature",
        "-WhiteBalance",
        "-FocalLength",
        "-FocalLengthIn35mmFormat",
        "-FocalLength35efl",
        "-LensModelName",
        "-MajorBrand",
        "-DeviceModelName",
        "-MetaFormat",
        "-ImageWidth",
        "-ImageHeight",
        "-ExifImageWidth",
        "-ExifImageHeight",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=25)
        payload = json.loads(out)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return {}
    if not payload or not isinstance(payload[0], dict):
        return {}
    tags = payload[0]
    return {str(k): str(v) for k, v in tags.items() if v not in (None, "")}


def _camera_fields_from_tags(tags: dict[str, str]) -> dict[str, str]:
    iso = _format_iso(_first_tag(tags, "ISO", "RecommendedExposureIndex"))
    aperture = _format_aperture(_first_tag(tags, "FNumber", "ApertureValue", "Aperture"))
    shutter = _format_shutter(_first_tag(tags, "ShutterSpeed", "ExposureTime"))
    color_temp = _color_temp_from_tags(tags)
    focal = _focal_from_tags(tags)
    if focal == "—":
        equiv = _first_tag(tags, "FocalLengthIn35mmFormat")
        if equiv:
            focal = _format_focal(equiv)
    return {
        "iso": iso,
        "aperture": aperture,
        "shutter": shutter,
        "color_temp": color_temp,
        "focal_length": focal,
    }


def _image_size_from_tags(tags: dict[str, str]) -> tuple[int, int]:
    for w_key, h_key in (
        ("ImageWidth", "ImageHeight"),
        ("ExifImageWidth", "ExifImageHeight"),
    ):
        try:
            width = int(float(tags.get(w_key) or 0))
            height = int(float(tags.get(h_key) or 0))
        except (TypeError, ValueError):
            continue
        if width > 0 and height > 0:
            return width, height
    return 0, 0


def _image_size_from_pil(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            return int(img.width), int(img.height)
    except Exception:
        return 0, 0


def _probe_image_info(path: Path) -> dict[str, str]:
    tags = read_exif_tags(path)
    width, height = _image_size_from_tags(tags)
    if width <= 0 or height <= 0:
        width, height = _image_size_from_pil(path)
    resolution = f"{width}×{height}" if width > 0 and height > 0 else "—"
    camera = _camera_fields_from_tags(tags)
    return {
        "title": path.stem,
        "kind": "image",
        "resolution": resolution,
        "fps": "—",
        "bitrate": "—",
        **camera,
    }


def _probe_raw_video_info(path: Path) -> dict[str, str]:
    if is_image_path(path):
        return _probe_image_info(path)
    stream = probe_video_stream(path)
    tags = _merge_sony_rtmd_tags(read_exif_tags(path), path)
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    resolution = f"{width}×{height}" if width > 0 and height > 0 else "—"
    fps = _parse_fps(str(stream.get("fps_raw") or ""))
    bitrate = _format_bitrate(stream.get("bit_rate"))
    camera = _camera_fields_from_tags(tags)
    return {
        "title": path.stem,
        "kind": "video",
        "resolution": resolution,
        "fps": fps,
        "bitrate": bitrate,
        **camera,
    }


def read_raw_video_info(path: Path, *, use_cache: bool = True) -> dict[str, str]:
    if use_cache:
        cached = peek_raw_video_info_cache(path)
        if cached is not None:
            return cached
    info = _probe_raw_video_info(path)
    if use_cache:
        try:
            _save_raw_video_info_cache(path, info)
        except OSError:
            pass
    return info


def format_raw_video_meta_lines(info: dict[str, str]) -> tuple[str, str, str]:
    if info.get("kind") == "image":
        line1 = f"{info.get('resolution', '—')} · JPG"
    else:
        line1 = (
            f"{info.get('resolution', '—')} · {info.get('fps', '—')} · "
            f"{info.get('bitrate', '—')}"
        )
    line2 = (
        f"ISO {info.get('iso', '—')} · {info.get('aperture', '—')} · "
        f"{info.get('shutter', '—')}"
    )
    line3 = f"{info.get('color_temp', '—')} · {info.get('focal_length', '—')}"
    return line1, line2, line3


def format_raw_video_detail_text(info: dict[str, str]) -> str:
    lines = [
        f"标题：{info.get('title', '—')}",
        f"分辨率：{info.get('resolution', '—')}",
    ]
    if info.get("kind") != "image":
        lines.extend(
            [
                f"帧率：{info.get('fps', '—')}",
                f"码率：{info.get('bitrate', '—')}",
            ]
        )
    lines.extend(
        [
            f"ISO：{info.get('iso', '—')}",
            f"光圈：{info.get('aperture', '—')}",
            f"快门：{info.get('shutter', '—')}",
            f"色温：{info.get('color_temp', '—')}",
            f"焦距：{info.get('focal_length', '—')}",
        ]
    )
    return "\n".join(lines)


def load_raw_media_thumb(path: Path, *, max_side: int = 320) -> "Image.Image | None":
    """Load a thumbnail for video (first frame) or JPG (resized still)."""
    from PIL import Image, ImageOps

    if is_image_path(path):
        try:
            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img)
                rgb = img.convert("RGB")
                rgb.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
                return rgb.copy()
        except Exception:
            return None
    from gui.video_library_tab import load_thumb_image

    thumb, _quality = load_thumb_image(path)
    return thumb
