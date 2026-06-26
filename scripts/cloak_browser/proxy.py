"""系统代理检测（WSL / 企业环境常见）。"""

from __future__ import annotations

import os


def detect_system_proxy() -> str | None:
    for key in (
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return None
