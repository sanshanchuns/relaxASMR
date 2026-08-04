"""加载 / 刷新 ElevenLabs 网页鉴权。

网页 ``POST /v1/content/generations`` 要的是 Firebase ID Token，不是 Cookie，
也不是 ``xi-api-key``。Cookie 只能证明浏览器登录过，API 网关不认。

推荐放 ``refresh_token.md``（从 Chrome DevTools → Application → IndexedDB →
``firebaseLocalStorageDb`` 里 ``stsTokenManager.refreshToken`` 拷出），本模块会
自动换成新的 Bearer。临时调试也可以直接把 Network 面板里的
``Authorization: Bearer eyJ…`` 整段贴进 ``bearer.md``。
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

DIR = Path(__file__).resolve().parent
COOKIE_PATH = DIR / "cookie.md"
BEARER_PATH = DIR / "bearer.md"
REFRESH_PATH = DIR / "refresh_token.md"
HCAPTCHA_PATH = DIR / "hcaptcha_token.md"
# 你习惯把浏览器 curl 贴这里；加载时会自动抠 Bearer / hCaptcha。
GENERATIONS_MOCK_PATH = DIR / "mock" / "generations.md"

# 与 elevenlabs.io 前端 dynamic-env-variables 里一致。
FIREBASE_API_KEY = "AIzaSyBSsRE_1Os04-bxpd5JTLIniy3UK4OqKys"
FIREBASE_REFRESH_URL = (
    f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
)

_BEARER_RE = re.compile(r"^(?:Bearer\s+)?(eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)\s*$")


@dataclass
class ElevenLabsWebAuth:
    bearer: str = ""
    refresh_token: str = ""
    cookie_header: str = ""
    hcaptcha_token: str = ""
    email: str = ""
    workspace_id: str = ""
    user_id: str = ""
    source: str = ""  # bearer_file | refresh | env

    @property
    def ok(self) -> bool:
        return bool(self.bearer.strip())

    def authorization_header(self) -> str:
        token = self.bearer.strip()
        if token.lower().startswith("bearer "):
            return token
        return f"Bearer {token}"


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _normalize_bearer(raw: str) -> str:
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        return ""
    # 允许整段 curl -H 'authorization: Bearer …'
    m = re.search(r"Bearer\s+(eyJ[A-Za-z0-9_\-\.]+)", raw, re.I)
    if m:
        return m.group(1)
    m = _BEARER_RE.match(raw.splitlines()[0].strip())
    return m.group(1) if m else raw.splitlines()[0].strip()


def _parse_cookie_meta(cookie_header: str) -> tuple[str, str, str]:
    """从 xi_website_user cookie 抠 email / workspace / user_id。"""
    email = workspace_id = user_id = ""
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part.startswith("xi_website_user="):
            continue
        raw = unquote(part.split("=", 1)[1])
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            break
        email = str(data.get("email") or "")
        workspace_id = str(data.get("workspace_id") or "")
        user_id = str(data.get("user_id") or "")
        break
    return email, workspace_id, user_id


def _jwt_exp(token: str) -> int | None:
    try:
        import base64

        payload = token.split(".")[1]
        payload += "=" * ((4 - len(payload) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = data.get("exp")
        return int(exp) if exp is not None else None
    except Exception:  # noqa: BLE001
        return None


def _bearer_fresh(token: str, *, skew_sec: int = 120) -> bool:
    exp = _jwt_exp(token)
    if exp is None:
        return bool(token)
    return time.time() < (exp - skew_sec)


def refresh_firebase_id_token(refresh_token: str) -> str:
    """用 Firebase refresh_token 换新的 id_token（即网页用的 Bearer）。"""
    import requests

    # API key 配了 HTTP referrer 限制；空 Referer 会 403 API_KEY_HTTP_REFERRER_BLOCKED。
    r = requests.post(
        FIREBASE_REFRESH_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token.strip()},
        headers={
            "Origin": "https://elevenlabs.io",
            "Referer": "https://elevenlabs.io/",
        },
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Firebase 刷新失败 HTTP {r.status_code}: {r.text[:300]}")
    data = r.json() or {}
    token = data.get("id_token") or data.get("access_token")
    if not token:
        raise RuntimeError(f"Firebase 刷新响应里没有 id_token：{str(data)[:200]}")
    # 若服务端轮换了 refresh_token，落盘以便下次继续用。
    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != refresh_token.strip():
        REFRESH_PATH.write_text(new_refresh.strip() + "\n", encoding="utf-8")
    return str(token)


def _jwt_claims(token: str) -> dict:
    try:
        import base64

        payload = token.split(".")[1]
        payload += "=" * ((4 - len(payload) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _parse_generations_mock(text: str) -> tuple[str, str]:
    """从 curl 抓包里抠 Firebase Bearer 与 hcaptcha_token。"""
    bearer = ""
    m = re.search(r"(?i)authorization:\s*Bearer\s+(eyJ[A-Za-z0-9_\-\.]+)", text)
    if m:
        bearer = m.group(1)
    hcaptcha = ""
    hm = re.search(r'"hcaptcha_token"\s*:\s*"(P1_[^"]+)"', text)
    if hm:
        hcaptcha = hm.group(1)
    return bearer, hcaptcha


def _bearer_exp(token: str) -> int:
    return int(_jwt_claims(token).get("exp") or 0)


def _ttl_sec(token: str) -> int:
    exp = _bearer_exp(token)
    if not exp:
        return 0
    return max(0, exp - int(time.time()))


def load_web_auth(*, force_refresh: bool = False) -> ElevenLabsWebAuth:
    cookie = _read_text(COOKIE_PATH) or os.environ.get("ELEVENLABS_WEB_COOKIE", "").strip()
    email, workspace_id, user_id = _parse_cookie_meta(cookie)
    hcaptcha = _read_text(HCAPTCHA_PATH) or os.environ.get("ELEVENLABS_HCAPTCHA_TOKEN", "").strip()
    refresh = _read_text(REFRESH_PATH) or os.environ.get("ELEVENLABS_FIREBASE_REFRESH_TOKEN", "").strip()
    bearer = _normalize_bearer(
        _read_text(BEARER_PATH) or os.environ.get("ELEVENLABS_WEB_BEARER", "")
    )
    source = ""

    # mock/generations.md：你贴 curl 后优先吃这份（若比现有 bearer 更新）。
    # 已有 refresh_token 时不再依赖 mock（避免过期 curl 盖住自动续期）。
    mock_text = _read_text(GENERATIONS_MOCK_PATH)
    if mock_text and not refresh:
        mock_bearer, mock_hcaptcha = _parse_generations_mock(mock_text)
        if mock_hcaptcha and (not hcaptcha or mock_hcaptcha != hcaptcha):
            hcaptcha = mock_hcaptcha
            HCAPTCHA_PATH.write_text(hcaptcha + "\n", encoding="utf-8")
        if mock_bearer and (
            not bearer
            or not _bearer_fresh(bearer)
            or _bearer_exp(mock_bearer) > _bearer_exp(bearer)
        ):
            bearer = mock_bearer
            BEARER_PATH.write_text(bearer + "\n", encoding="utf-8")
            source = "generations_mock"
    elif mock_text:
        # 仍可同步较新的 hCaptcha（与 refresh 无关）。
        _, mock_hcaptcha = _parse_generations_mock(mock_text)
        if mock_hcaptcha and mock_hcaptcha != hcaptcha:
            hcaptcha = mock_hcaptcha
            HCAPTCHA_PATH.write_text(hcaptcha + "\n", encoding="utf-8")

    if refresh and (force_refresh or not bearer or not _bearer_fresh(bearer)):
        bearer = refresh_firebase_id_token(refresh)
        BEARER_PATH.write_text(bearer + "\n", encoding="utf-8")
        refresh = _read_text(REFRESH_PATH) or refresh
        source = "refresh"
    elif bearer and not source:
        source = "bearer_file" if BEARER_PATH.is_file() else "env"

    claims = _jwt_claims(bearer) if bearer else {}
    email = email or str(claims.get("email") or "")
    workspace_id = workspace_id or str(claims.get("workspace_id") or "")
    user_id = user_id or str(claims.get("workspace_user_id") or claims.get("user_id") or "")

    return ElevenLabsWebAuth(
        bearer=bearer,
        refresh_token=refresh,
        cookie_header=cookie,
        hcaptcha_token=hcaptcha,
        email=email,
        workspace_id=workspace_id,
        user_id=user_id,
        source=source,
    )


def ensure_fresh_auth(
    *,
    min_ttl_sec: int = 300,
    force_refresh: bool = False,
    allow_browser_sync: bool | None = None,
) -> ElevenLabsWebAuth:
    """保证 Bearer 至少还有 *min_ttl_sec* 秒有效。

    优先级：
    1. ``refresh_token.md`` → Firebase 换新 id_token（主路径，全自动）
    2. 可选 headless Playwright 复用 ``.profile``（``ELEVENLABS_AUTO_BROWSER_SYNC=1``）
    3. 退回 ``load_web_auth``（mock curl / 手贴 bearer）
    """
    if allow_browser_sync is None:
        allow_browser_sync = os.environ.get("ELEVENLABS_AUTO_BROWSER_SYNC", "").strip() in (
            "1",
            "true",
            "yes",
        )

    auth = load_web_auth(force_refresh=force_refresh)
    if auth.ok and not force_refresh and _ttl_sec(auth.bearer) >= min_ttl_sec:
        return auth

    refresh = auth.refresh_token or _read_text(REFRESH_PATH) or os.environ.get(
        "ELEVENLABS_FIREBASE_REFRESH_TOKEN", ""
    ).strip()
    if refresh:
        try:
            bearer = refresh_firebase_id_token(refresh)
            BEARER_PATH.write_text(bearer + "\n", encoding="utf-8")
            return load_web_auth()
        except Exception:  # noqa: BLE001
            if not allow_browser_sync:
                raise

    if allow_browser_sync:
        from .browser_sync import PROFILE_DIR, sync_with_persistent_profile

        if PROFILE_DIR.is_dir() and any(PROFILE_DIR.iterdir()):
            sync_with_persistent_profile(headless=True, timeout_sec=90)
            return load_web_auth()

    return load_web_auth(force_refresh=force_refresh)


def auth_status_message(auth: ElevenLabsWebAuth | None = None) -> str:
    auth = auth or load_web_auth()
    if auth.ok:
        who = auth.email or "unknown"
        left = ""
        exp = _bearer_exp(auth.bearer)
        if exp:
            left = f" · ~{max(0, exp - int(time.time()))}s"
        return f"网页会话可用 · {who} · source={auth.source or '?'}{left}"
    parts = [
        "网页通道缺少 Firebase Bearer。",
        "请先：PYTHONPATH=cli:. python -m elevenlabs_http login（导出 refresh_token 后自动续期）；",
        f"或把 curl 贴到 mock/{GENERATIONS_MOCK_PATH.name}；",
        f"或手贴 refreshToken 到 {REFRESH_PATH.name}。",
        "仅有 cookie.md / fern_token 不够。",
    ]
    if auth.email:
        parts.append(f"cookie 里看到的账号是 {auth.email}。")
    return "".join(parts)
