"""YouTube Data API v3：OAuth + 视频上传 + 缩略图。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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


def open_browser_url(url: str) -> None:
    """WSL 下用 Windows 默认浏览器打开 URL，避免 xdg-open / cmd 截断 & 参数。"""
    if is_wsl():
        # 勿用 cmd.exe /c start：OAuth URL 含 &，cmd 会截断，导致缺 client_id/redirect_uri
        explorer = Path("/mnt/c/Windows/explorer.exe")
        if explorer.is_file():
            subprocess.Popen(
                ["/init", str(explorer), url],
                start_new_session=True,
                cwd="/mnt/c",
            )
            return
        ps = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
        if ps.is_file():
            subprocess.Popen(
                ["/init", str(ps), "-NoProfile", "-Command", f"Start-Process '{url}'"],
                start_new_session=True,
                cwd="/mnt/c",
            )
            return
        raise FileNotFoundError("WSL 下找不到 explorer.exe / PowerShell，无法打开浏览器")
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
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

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

    return build("youtube", "v3", credentials=creds)


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
) -> str:
    from googleapiclient.http import MediaFileUpload

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

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=10 * 1024 * 1024,
        resumable=True,
    )
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status and on_progress:
            on_progress(int(status.progress() * 100))

    return response["id"]


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

    creds_path, tok_path, account_name = resolve_account_paths(
        account,
        credentials_path=credentials_path,
        token_path=token_path,
    )

    log(f"账号：{account_label(account_name)}")
    log(f"凭据：{creds_path.name}  Token：{tok_path.name}")
    log("连接 YouTube API（OAuth）…")
    service = get_youtube_service(creds_path, tok_path, account=account_name, on_log=on_log)

    log(f"上传视频：{video_path.name}（{privacy_status}）…")
    log(f"  分类：Travel & Events · 语言：English")
    last_pct = [-1]
    def prog(pct: int) -> None:
        if on_progress:
            on_progress(pct)
        if pct % 10 == 0 and pct != last_pct[0]:
            log(f"  上传进度 {pct}%")
            last_pct[0] = pct

    video_id = upload_video(
        service,
        video_path,
        title=title,
        description=description,
        tags=tags,
        privacy_status=privacy_status,
        on_progress=prog,
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
        except Exception as e:
            log(f"自动截帧失败：{e}")
            
    if thumb_path.is_file():
        log("设置缩略图…")
        set_thumbnail(service, video_id, thumb_path)
        log("缩略图已设置")
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
