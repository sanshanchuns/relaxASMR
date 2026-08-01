"""磁盘 TTL 缓存：YouTube API 结果 + 远程缩略图，避免反复消耗配额。"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

CACHE_ROOT = Path(__file__).resolve().parent / ".cache" / "youtube"
THUMB_DIR = CACHE_ROOT / "thumbs"
INSIGHT_DIR = CACHE_ROOT / "insights"

DEFAULT_TTL_SEC = 24 * 3600


def _key_path(key: str) -> Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return CACHE_ROOT / f"{digest}.json"


def cache_get(key: str, *, ttl_seconds: float = DEFAULT_TTL_SEC) -> Any | None:
    path = _key_path(key)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    saved_at = payload.get("saved_at")
    if not isinstance(saved_at, (int, float)):
        return None
    if ttl_seconds >= 0 and (time.time() - saved_at) > ttl_seconds:
        return None
    return payload.get("value")


def cache_set(key: str, value: Any) -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    path = _key_path(key)
    payload = {"saved_at": time.time(), "value": value}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def cache_age_seconds(key: str) -> float | None:
    path = _key_path(key)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    saved_at = payload.get("saved_at")
    if not isinstance(saved_at, (int, float)):
        return None
    return time.time() - saved_at


def cache_clear(key: str) -> None:
    path = _key_path(key)
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def download_thumbnail(url: str, *, timeout: float = 15.0) -> Path | None:
    """按 URL 哈希缓存缩略图到本地文件；已存在则直接复用，不重复下载。"""
    if not url:
        return None
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    suffix = ".jpg"
    out = THUMB_DIR / f"{digest}{suffix}"
    if out.is_file() and out.stat().st_size > 0:
        return out
    try:
        import requests

        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        out.write_bytes(resp.content)
        return out
    except Exception:
        return None


__all__ = [
    "CACHE_ROOT",
    "THUMB_DIR",
    "INSIGHT_DIR",
    "DEFAULT_TTL_SEC",
    "cache_get",
    "cache_set",
    "cache_age_seconds",
    "cache_clear",
    "download_thumbnail",
]
