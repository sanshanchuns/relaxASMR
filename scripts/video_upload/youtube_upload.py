"""YouTube Data API v3：OAuth + 视频上传 + 缩略图。"""

from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .material_store import (
    load_material_metadata,
    resolve_material_in_dir,
    scene_id_from_material_path,
)
from .parse_youtube_md import pick_description, pick_title

VIDEO_UPLOAD_DIR = Path(__file__).resolve().parent
CONFIG_DIR = VIDEO_UPLOAD_DIR / "config"
DEFAULT_CREDENTIALS = CONFIG_DIR / "credentials_leo.json"
DEFAULT_TOKEN = CONFIG_DIR / "token_leo.json"
DEFAULT_ACCOUNT = "leo"

YOUTUBE_ACCOUNTS: dict[str, dict[str, object]] = {
    "leo": {
        "label": "leo (ace.leo.zhu@gmail.com)",
        "credentials": CONFIG_DIR / "credentials_leo.json",
        "token": CONFIG_DIR / "token_leo.json",
    },
    "leo_usa": {
        "label": "leo_usa (ace.leo.zhu.usa@gmail.com)",
        "credentials": CONFIG_DIR / "credentials_leo_usa.json",
        "token": CONFIG_DIR / "token_leo_usa.json",
    },
}

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

# YouTube 上传固定元数据（与 Studio 默认对齐）
DEFAULT_CATEGORY_ID = "19"  # Travel & Events（旅游与活动）
DEFAULT_VIDEO_LANGUAGE = "en"  # English（标题/说明/音轨语言）
# 字幕认证「This content has never aired on television in the U.S.」无公开 API 字段，需在 Studio 高级设置手动确认

# 大文件（3h FHD ~13G）分块上传：单块失败时重试 + 拉长 HTTP 超时，避免 SSL EOF 直接整段失败。
UPLOAD_CHUNK_SIZE = 32 * 1024 * 1024  # 32 MiB
UPLOAD_HTTP_TIMEOUT_SEC = 600
UPLOAD_CHUNK_MAX_RETRIES = 12
UPLOAD_RETRY_INITIAL_DELAY_SEC = 5
UPLOAD_RETRY_MAX_DELAY_SEC = 120


def resolve_account_paths(
    account: str | None = None,
    *,
    credentials_path: Path | None = None,
    token_path: Path | None = None,
) -> tuple[Path, Path, str]:
    """按账号名解析 OAuth 凭据与 token 路径；可单独覆盖 credentials / token。"""
    name = account or DEFAULT_ACCOUNT
    if name not in YOUTUBE_ACCOUNTS:
        known = ", ".join(sorted(YOUTUBE_ACCOUNTS))
        raise ValueError(f"未知 YouTube 账号：{name}（可选：{known}）")

    info = YOUTUBE_ACCOUNTS[name]
    creds = credentials_path or Path(str(info["credentials"]))
    token = token_path or Path(str(info["token"]))
    if not token.is_file() and name == DEFAULT_ACCOUNT and token_path is None:
        legacy_token = VIDEO_UPLOAD_DIR / "token.json"
        if legacy_token.is_file() and creds.is_file():
            try:
                if client_id_from_token(legacy_token) == client_id_from_credentials(creds):
                    shutil.copy2(legacy_token, token)
            except (ValueError, KeyError, json.JSONDecodeError):
                pass
    return creds.resolve(), token.resolve(), name


def account_label(account: str) -> str:
    info = YOUTUBE_ACCOUNTS.get(account)
    return str(info["label"]) if info else account


def client_id_from_credentials(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("installed", "web"):
        if key in data:
            return data[key]["client_id"]
    raise ValueError(f"无效的 OAuth 凭据文件：{path}")


def client_id_from_token(path: Path) -> str | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("client_id")


def account_for_client_id(client_id: str) -> str | None:
    for name, info in YOUTUBE_ACCOUNTS.items():
        creds_path = Path(str(info["credentials"]))
        if creds_path.is_file() and client_id_from_credentials(creds_path) == client_id:
            return name
    return None


def reconcile_misplaced_token(
    token_path: Path,
    expected_client_id: str,
    *,
    on_log: Callable[[str], None] | None = None,
) -> bool:
    """token 与凭据 client_id 不一致时尝试移到正确账号路径。返回当前路径是否仍有可用 token。"""
    if not token_path.is_file():
        return False

    token_client_id = client_id_from_token(token_path)
    if not token_client_id or token_client_id == expected_client_id:
        return True

    def log(msg: str) -> None:
        if on_log:
            on_log(msg)
        else:
            print(msg)

    owner = account_for_client_id(token_client_id)
    if owner:
        correct_token = Path(str(YOUTUBE_ACCOUNTS[owner]["token"]))
        if correct_token.resolve() != token_path.resolve():
            if correct_token.is_file():
                log(
                    f"警告：{token_path.name} 实际是 {owner} 的 token，"
                    f"且 {correct_token.name} 已存在；将忽略并重新授权"
                )
                return False
            token_path.rename(correct_token)
            log(f"已将错放的 token 移到 {correct_token.name}（属于 {owner}）")
            return False

    log(f"警告：{token_path.name} 与当前凭据 OAuth 客户端不匹配，将重新授权")
    return False


def write_token_file(token_path: Path, creds, account: str | None = None) -> None:
    payload = json.loads(creds.to_json())
    if account:
        payload["account"] = account
    token_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_wsl() -> bool:
    return bool(os.environ.get("WSL_DISTRO_NAME"))


# 系统级安装路径 + 常见的按用户安装路径（`/mnt/c/Users/*/AppData/Local/...`），
# 按优先级从上到下尝试，找到第一个存在的就用它。
_WSL_BROWSER_CANDIDATES: tuple[str, ...] = (
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
)
_WSL_BROWSER_USER_GLOBS: tuple[str, ...] = (
    "*/AppData/Local/Google/Chrome/Application/chrome.exe",
    "*/AppData/Local/Microsoft/Edge/Application/msedge.exe",
)


def _find_wsl_browser_exe() -> Path | None:
    """定位 WSL 宿主机上已安装的 Chrome/Edge 可执行文件（系统级优先）。"""
    for candidate in _WSL_BROWSER_CANDIDATES:
        p = Path(candidate)
        if p.is_file():
            return p
    users_dir = Path("/mnt/c/Users")
    if users_dir.is_dir():
        for pattern in _WSL_BROWSER_USER_GLOBS:
            for p in sorted(users_dir.glob(pattern)):
                if p.is_file():
                    return p
    return None


# 本项目跟 ace.leo.zhu@gmail.com 这个 YouTube 账号绑定（见
# ``gui/youtube_api.py`` 的 ``OWN_ACCOUNT_EMAIL``），优先用登录了这个邮箱的
# Chrome 个人资料打开链接，跟 YouTube 上下文对得上。
_OWN_CHROME_ACCOUNT_EMAIL = "ace.leo.zhu@gmail.com"


def _find_wsl_chrome_profile_dir(target_email: str) -> str | None:
    """按 Chrome 的 ``Local State``（``profile.info_cache``）找登录邮箱匹配的
    本地 profile 文件夹名（如 ``"Default"``/``"Profile 1"``），用来直接指定
    ``--profile-directory`` 跳过多账号机器上的「谁在使用 Chrome？」选择页
    ——不指定的话，只要开了「在 Chrome 启动时显示」这个选项，每次冷启动一个
    全新 chrome.exe 进程都会先卡在这一页，看起来就像「点了没反应」。
    """
    candidates = sorted(
        Path("/mnt/c/Users").glob("*/AppData/Local/Google/Chrome/User Data/Local State"),
        key=lambda p: p.stat().st_mtime if p.is_file() else 0.0,
        reverse=True,
    )
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        info_cache = (data.get("profile") or {}).get("info_cache") or {}
        for folder, meta in info_cache.items():
            if isinstance(meta, dict) and meta.get("user_name") == target_email:
                return str(folder)
    return None


def open_browser_url(url: str) -> None:
    """WSL 下用 Windows 浏览器打开 URL，避免 xdg-open / cmd 截断 & 参数。

    优先直接调起 chrome.exe/msedge.exe 并把 URL 当参数传入——浏览器自带的单
    实例机制会把这个 URL 转发给已经在跑的窗口开新标签页，比
    ``rundll32 url.dll,FileProtocolHandler`` 更可靠：后者走的是 Shell 协议
    关联，在 WSL interop 这种跨 window station 的场景下经常出现「进程起来了
    但没有真正打开新标签页」的情况（哪怕浏览器本身已经在运行）。

    是 Chrome 的话额外带上 ``--profile-directory``：多账号机器上如果开了
    「在 Chrome 启动时显示个人资料选择器」，裸调 ``chrome.exe <url>`` 冷启动
    时会先卡在选择页而不会真正打开链接，必须显式指定 profile 才能跳过。
    """
    if is_wsl():
        browser = _find_wsl_browser_exe()
        if browser is not None:
            args = ["/init", str(browser)]
            if browser.name.lower() == "chrome.exe":
                profile_dir = _find_wsl_chrome_profile_dir(_OWN_CHROME_ACCOUNT_EMAIL)
                if profile_dir:
                    args.append(f"--profile-directory={profile_dir}")
            args.append(url)
            try:
                subprocess.Popen(args, start_new_session=True, cwd="/mnt/c")
                return
            except OSError:
                pass

        win_sys = Path("/mnt/c/Windows/System32")
        # explorer.exe 传 URL 在 WSL 常会打开「文件资源管理器」而非浏览器
        rundll32 = win_sys / "rundll32.exe"
        if rundll32.is_file():
            subprocess.Popen(
                ["/init", str(rundll32), "url.dll,FileProtocolHandler", url],
                start_new_session=True,
                cwd="/mnt/c",
            )
            return
        ps = win_sys / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if ps.is_file():
            ps_url = url.replace("'", "''")
            subprocess.Popen(
                ["/init", str(ps), "-NoProfile", "-Command", f"Start-Process '{ps_url}'"],
                start_new_session=True,
                cwd="/mnt/c",
            )
            return
        raise FileNotFoundError("WSL 下找不到 Chrome/Edge/rundll32/PowerShell，无法打开浏览器")
    import webbrowser

    webbrowser.open(url, new=1)


def run_oauth_local_server(flow, *, on_log: Callable[[str], None] | None = None) -> object:
    def log(msg: str) -> None:
        if on_log:
            on_log(msg)
        else:
            print(msg)

    if is_wsl():
        import webbrowser

        log("WSL：在 Windows 浏览器中打开 Google 授权页…")
        log("请在浏览器完成授权；localhost 回调由 WSL 接收，完成后自动继续")

        class _WslBrowser:
            def open(self, url: str, new: int = 0, autoraise: bool = True) -> bool:
                log("—— Google OAuth 授权链接（可复制到 Windows 浏览器）——")
                log(url)
                log("正在尝试打开 Windows 默认浏览器…")
                open_browser_url(url)
                return True

        original_get = webbrowser.get

        def wsl_webbrowser_get(browser: str | None = None):
            if browser is None:
                return _WslBrowser()
            return original_get(browser)

        webbrowser.get = wsl_webbrowser_get
        try:
            return flow.run_local_server(port=0, open_browser=True)
        finally:
            webbrowser.get = original_get

    return flow.run_local_server(port=0, open_browser=True)


def resolve_video_for_material(material_dir: Path, meta: dict | None = None) -> Path:
    material_dir = material_dir.resolve()
    if material_dir.is_file():
        if meta is None:
            meta = load_material_metadata(material_dir)
        material_dir = material_dir.parent
    elif meta is None:
        mat_path = resolve_material_in_dir(material_dir)
        if mat_path is not None:
            meta = load_material_metadata(mat_path)

    search_roots: list[Path] = []
    for root in (material_dir.parent, material_dir.parent.parent):
        if root not in search_roots:
            search_roots.append(root)

    if meta and meta.get("video_name"):
        for root in search_roots:
            candidate = root / meta["video_name"]
            if candidate.is_file():
                return candidate

    for root in search_roots:
        candidate = root / f"{material_dir.name}.mp4"
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        f"找不到与物料目录对应的 MP4（已搜索 {', '.join(str(r) for r in search_roots)}）"
    )


def resolve_thumbnail_path(material_dir: Path, meta: dict, material_path: Path | None) -> Path:
    scene_id = meta.get("scene_id") or ""
    if not scene_id and material_path is not None:
        scene_id = scene_id_from_material_path(material_path)
    if scene_id:
        candidate = material_dir / f"{scene_id}_thumbnail.jpg"
        if candidate.is_file():
            return candidate
    legacy = material_dir / "thumbnail.jpg"
    return legacy


def get_youtube_service(
    credentials_path: Path | None = None,
    token_path: Path | None = None,
    account: str | None = None,
    on_log: Callable[[str], None] | None = None,
):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise RuntimeError(
            f"YouTube 上传依赖缺失: {e}\n"
            "请安装: pip install -r scripts/video_upload/requirements.txt"
        ) from e

    credentials_path = (credentials_path or DEFAULT_CREDENTIALS).resolve()
    token_path = (token_path or DEFAULT_TOKEN).resolve()

    if not credentials_path.is_file():
        raise FileNotFoundError(f"找不到 OAuth 凭据：{credentials_path}")

    expected_client_id = client_id_from_credentials(credentials_path)
    token_usable = reconcile_misplaced_token(
        token_path,
        expected_client_id,
        on_log=on_log,
    )

    creds = None
    if token_usable and token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = run_oauth_local_server(flow, on_log=on_log)
        write_token_file(token_path, creds, account=account)

    return _build_youtube_service(creds)


def _is_retryable_upload_error(exc: BaseException) -> bool:
    """分块上传过程中可重试的瞬时网络/SSL 错误。"""
    from googleapiclient.errors import HttpError

    if isinstance(exc, HttpError):
        status = getattr(exc.resp, "status", None)
        return status in (408, 429, 500, 502, 503, 504)
    if isinstance(exc, (ssl.SSLError, ConnectionError, BrokenPipeError, TimeoutError)):
        return True
    if isinstance(exc, OSError):
        msg = str(exc).lower()
        return (
            "eof occurred in violation of protocol" in msg
            or "connection reset" in msg
            or "timed out" in msg
            or "broken pipe" in msg
        )
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause is not None and cause is not exc:
        return _is_retryable_upload_error(cause)
    return False


def _configure_resumable_upload_http(http) -> None:
    """Resumable upload 用 308 表示「续传未完成」，不是 RFC 重定向；须从 redirect_codes 排除。"""
    try:
        http.redirect_codes = set(http.redirect_codes) - {308}
    except AttributeError:
        pass


def _build_youtube_service(creds):
    """带较长超时的 AuthorizedHttp，适合大文件 resumable upload。"""
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build

    http = httplib2.Http(timeout=UPLOAD_HTTP_TIMEOUT_SEC)
    _configure_resumable_upload_http(http)
    authorized = AuthorizedHttp(creds, http=http)
    return build("youtube", "v3", http=authorized, cache_discovery=False)


def upload_video(
    service,
    video_path: Path,
    *,
    title: str,
    description: str,
    tags: list[str] | None = None,
    privacy_status: str = "unlisted",
    category_id: str = DEFAULT_CATEGORY_ID,
    on_progress: Callable[[int], None] | None = None,
    on_log: Callable[[str], None] | None = None,
) -> str:
    from googleapiclient.http import MediaFileUpload

    def log(msg: str) -> None:
        if on_log:
            on_log(msg)

    video_path = video_path.resolve()
    if not video_path.is_file():
        raise FileNotFoundError(f"找不到视频：{video_path}")

    tag_list = [t[:100] for t in (tags or []) if t.strip()][:30]
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tag_list,
            "categoryId": category_id,
            "defaultLanguage": DEFAULT_VIDEO_LANGUAGE,
            "defaultAudioLanguage": DEFAULT_VIDEO_LANGUAGE,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    file_size = video_path.stat().st_size
    if file_size < 1_000_000:
        raise RuntimeError(
            f"拒绝上传：文件过小（{file_size} 字节），疑似未完整落到本地。"
            f"协作机请确认 staging 已从 NAS 拷完。"
        )
    log(f"准备上传本地文件：{video_path}（{file_size / (1024**3):.2f} GB）")
    log(
        "开始分块上传到 YouTube（API resumable）。"
        "左侧 Remaining% 来自已确认分块；Studio 网页对 API 上传常一直显示"
        "「准备开始处理 / 0%」，直到整文件传完——与浏览器直传主机时的进度条不同。"
    )

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=UPLOAD_CHUNK_SIZE,
        resumable=True,
    )
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    last_pct = -1
    last_logged_pct = -1
    while response is None:
        attempt = 0
        while True:
            try:
                status, response = request.next_chunk()
                break
            except Exception as exc:  # noqa: BLE001
                if not _is_retryable_upload_error(exc) or attempt >= UPLOAD_CHUNK_MAX_RETRIES:
                    raise
                attempt += 1
                delay = min(
                    UPLOAD_RETRY_INITIAL_DELAY_SEC * (2 ** (attempt - 1)),
                    UPLOAD_RETRY_MAX_DELAY_SEC,
                )
                log(
                    f"上传块失败（{exc.__class__.__name__}: {exc}），"
                    f"{delay}s 后重试 ({attempt}/{UPLOAD_CHUNK_MAX_RETRIES})…"
                )
                time.sleep(delay)
        if status and on_progress:
            pct = int(status.progress() * 100)
            if pct != last_pct:
                on_progress(pct)
                last_pct = pct
            # 日志每 20% 打一行，避免停在「准备上传」误以为没在传。
            if pct >= last_logged_pct + 20 or (pct >= 100 and pct != last_logged_pct):
                sent_gb = file_size * (pct / 100.0) / (1024**3)
                log(f"上传进度：{pct}%（约 {sent_gb:.2f} / {file_size / (1024**3):.2f} GB）")
                last_logged_pct = pct

    if not isinstance(response, dict) or not response.get("id"):
        raise RuntimeError("YouTube 返回了空响应，上传未真正完成（请删除 Studio 里 0% 草稿后重试）")

    video_id = str(response["id"])
    verify_uploaded_video(service, video_id, on_log=on_log)
    return video_id


def verify_uploaded_video(
    service,
    video_id: str,
    *,
    on_log: Callable[[str], None] | None = None,
    attempts: int = 6,
    delay_sec: float = 3.0,
) -> dict:
    """上传结束后向 YouTube 反查，避免「客户端拿到 id、Studio 仍显示 0%」的假完成。"""

    def log(msg: str) -> None:
        if on_log:
            on_log(msg)

    last_status = None
    for i in range(max(1, attempts)):
        data = service.videos().list(
            part="status,contentDetails,processingDetails",
            id=video_id,
        ).execute()
        items = data.get("items") or []
        if not items:
            last_status = "missing"
            log(f"上传校验：尚未查到视频 {video_id}（{i + 1}/{attempts}）…")
            time.sleep(delay_sec)
            continue

        item = items[0]
        upload_status = (item.get("status") or {}).get("uploadStatus")
        last_status = upload_status
        # uploaded / processed 才算字节已到齐；其它状态（含空）视为未真正完成。
        if upload_status in ("uploaded", "processed"):
            duration = ((item.get("contentDetails") or {}).get("duration")) or ""
            processing = ((item.get("processingDetails") or {}).get("processingStatus")) or ""
            log(
                f"上传校验通过：uploadStatus={upload_status}"
                + (f" · processing={processing}" if processing else "")
                + (f" · duration={duration}" if duration else "")
            )
            return item

        log(
            f"上传校验：uploadStatus={upload_status!r}（{i + 1}/{attempts}），"
            f"等待 YouTube 确认…"
        )
        time.sleep(delay_sec)

    raise RuntimeError(
        f"YouTube 端未确认上传完成（video_id={video_id}，最后状态={last_status!r}）。"
        f"Studio 若显示「正在上传 0%」，请手动删除该草稿后，在协作机上重试一键上传。"
    )


def _log_upload_text_field(log: Callable[[str], None], label: str, value: str) -> None:
    text = (value or "").strip()
    if not text:
        log(f"{label}：（空）")
        return
    lines = text.splitlines()
    if len(lines) == 1:
        log(f"{label}：{lines[0]}")
        return
    log(f"{label}：")
    for line in lines:
        log(f"  {line}")


def set_thumbnail(service, video_id: str, thumb_path: Path) -> None:
    from googleapiclient.http import MediaFileUpload

    thumb_path = thumb_path.resolve()
    if not thumb_path.is_file():
        raise FileNotFoundError(f"找不到缩略图：{thumb_path}")
    media = MediaFileUpload(str(thumb_path), mimetype="image/jpeg")
    service.thumbnails().set(videoId=video_id, media_body=media).execute()


def upload_from_material(
    material_dir: Path,
    *,
    language: str = "en",
    privacy_status: str = "unlisted",
    account: str | None = None,
    credentials_path: Path | None = None,
    token_path: Path | None = None,
    override_video_path: Path | None = None,
    service: object | None = None,
    on_log: Callable[[str], None] | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> dict:
    """从物料目录上传：*_material.json + 对应 MP4 + 缩略图。"""

    def log(msg: str) -> None:
        if on_log:
            on_log(msg)
        else:
            print(msg)

    material_dir = Path(material_dir).resolve()
    material_path: Path | None = None
    if material_dir.is_file() and material_dir.suffix.lower() in (".json", ".md"):
        material_path = material_dir
        material_dir = material_path.parent
    else:
        material_path = resolve_material_in_dir(material_dir)

    if material_path is None or not material_path.is_file():
        raise FileNotFoundError(f"找不到物料文件（*_material.json / *_material.md）：{material_dir}")

    meta = load_material_metadata(material_path)
    title = pick_title(meta, language)
    description = pick_description(meta, language)
    tags = meta.get("tags", [])
    if not title:
        raise ValueError(f"{material_path.name} 中缺少标题")

    video_path = override_video_path or resolve_video_for_material(material_dir, meta)
    thumb_path = resolve_thumbnail_path(material_dir, meta, material_path)

    lang_label = "中文" if language == "zh" else "English"
    log("—— 上传元数据 ——")
    log(f"物料：{material_path.name}")
    _log_upload_text_field(log, f"标题（{lang_label}）", title)
    _log_upload_text_field(log, f"描述（{lang_label}）", description)
    if thumb_path.is_file():
        log(f"封面：{thumb_path.name}")
    else:
        log(f"封面：未找到 {thumb_path.name}（上传后将尝试自动截帧）")
    log(f"视频文件：{video_path.name}")

    creds_path, tok_path, account_name = resolve_account_paths(
        account,
        credentials_path=credentials_path,
        token_path=token_path,
    )

    log(f"账号：{account_label(account_name)}")
    log(f"凭据：{creds_path.name}  Token：{tok_path.name}")
    if service is None:
        log("连接 YouTube API（OAuth）…")
        service = get_youtube_service(creds_path, tok_path, account=account_name, on_log=on_log)
    else:
        log("YouTube API 已连接")

    log(f"上传视频：{video_path.name}（{privacy_status}）…")
    log(f"  分类：Travel & Events · 语言：{lang_label}")

    def prog(pct: int) -> None:
        if on_progress:
            on_progress(pct)

    video_id = upload_video(
        service,
        video_path,
        title=title,
        description=description,
        tags=tags,
        privacy_status=privacy_status,
        on_progress=prog,
        on_log=log,
    )
    url = f"https://www.youtube.com/watch?v={video_id}"
    log(f"视频已上传：{url}")

    if not thumb_path.is_file():
        log("未找到 thumbnail.jpg，将尝试自动从视频截取画面...")
        fallback_thumb = material_dir / "auto_thumbnail.jpg"
        try:
            import subprocess
            # Extract at 12 seconds to avoid fade-in black screen
            cmd = [
                "ffmpeg", "-y", "-ss", "12", "-i", str(video_path),
                "-vframes", "1", "-q:v", "2", str(fallback_thumb)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if fallback_thumb.is_file():
                thumb_path = fallback_thumb
                log(f"封面（自动截帧）：{thumb_path.name}")
        except Exception as e:
            log(f"自动截帧失败：{e}")
            
    if thumb_path.is_file():
        log(f"设置封面：{thumb_path.name}")
        set_thumbnail(service, video_id, thumb_path)
        log("封面已设置")
    else:
        log("无法提供缩略图，将使用 YouTube 自动生成（可能为黑屏）")

    record = {
        "video_id": video_id,
        "url": url,
        "title": title,
        "privacy_status": privacy_status,
        "video_file": video_path.name,
        "account": account_name,
        "category_id": DEFAULT_CATEGORY_ID,
        "video_language": DEFAULT_VIDEO_LANGUAGE,
    }
    record_path = material_dir / "upload_record.json"
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"记录已写入：{record_path.name}")

    return record
