"""YouTube Data API v3：OAuth + 视频上传 + 缩略图（relaxASMR 物料层）。"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
_REPO = _SCRIPTS.parent
_UTILS = _REPO.parent / "utils"
if _UTILS.is_dir() and str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

from youtube.upload import (  # noqa: E402
    DEFAULT_ACCOUNT,
    DEFAULT_CATEGORY_ID,
    DEFAULT_CREDENTIALS,
    DEFAULT_TOKEN,
    DEFAULT_VIDEO_LANGUAGE,
    SCOPES,
    YOUTUBE_ACCOUNTS,
    account_label,
    get_youtube_service,
    resolve_account_paths,
    set_thumbnail,
    upload_video,
    write_token_file,
)

from .material_store import (
    load_material_metadata,
    resolve_material_in_dir,
    scene_id_from_material_path,
)
from .parse_youtube_md import pick_description, pick_title

__all__ = [
    "DEFAULT_ACCOUNT",
    "DEFAULT_CATEGORY_ID",
    "DEFAULT_CREDENTIALS",
    "DEFAULT_TOKEN",
    "DEFAULT_VIDEO_LANGUAGE",
    "SCOPES",
    "YOUTUBE_ACCOUNTS",
    "account_label",
    "get_youtube_service",
    "resolve_account_paths",
    "resolve_thumbnail_path",
    "resolve_video_for_material",
    "set_thumbnail",
    "upload_from_material",
    "upload_video",
    "write_token_file",
]


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
    return material_dir / "thumbnail.jpg"


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
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                "12",
                "-i",
                str(video_path),
                "-vframes",
                "1",
                "-q:v",
                "2",
                str(fallback_thumb),
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if fallback_thumb.is_file():
                thumb_path = fallback_thumb
                log(f"封面（自动截帧）：{thumb_path.name}")
        except Exception as exc:
            log(f"自动截帧失败：{exc}")

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
