"""Cloudflare / bot challenge 检测。"""

from __future__ import annotations

CF_MARKERS = ("Just a moment...", "cf-chl", "challenge-platform")


def is_cloudflare_challenge(text: str) -> bool:
    return any(marker in text for marker in CF_MARKERS)
