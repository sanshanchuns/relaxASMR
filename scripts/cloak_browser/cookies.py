"""Cookie 字符串 → Playwright cookie 列表。"""

from __future__ import annotations

from urllib.parse import unquote


def parse_cookie_header(
    cookie_str: str,
    *,
    domain: str,
    path: str = "/",
) -> list[dict[str, str]]:
    cookies: list[dict[str, str]] = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies.append(
            {
                "name": name.strip(),
                "value": unquote(value.strip()),
                "domain": domain,
                "path": path,
            }
        )
    return cookies
