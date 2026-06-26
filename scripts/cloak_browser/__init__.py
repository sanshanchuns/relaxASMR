"""共享 CloakBrowser 能力（过 Cloudflare / bot 检测）。

pip: cloakbrowser — https://github.com/CloakHQ/cloakbrowser
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from cloak_browser.challenge import CF_MARKERS, is_cloudflare_challenge
from cloak_browser.cookies import parse_cookie_header
from cloak_browser.proxy import detect_system_proxy
from cloak_browser.session import CloakBrowserSession, default_profile_dir

__all__ = [
    "CF_MARKERS",
    "CloakBrowserSession",
    "default_profile_dir",
    "detect_system_proxy",
    "is_cloudflare_challenge",
    "parse_cookie_header",
]
