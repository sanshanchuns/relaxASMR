"""YouTube Data API v3 封装：自有频道数据 + 同类爆款视频聚合。

- 常规查询（频道详情、播放列表、视频统计、关键词搜索）统一走 ``YOUTUBE_DATA_API_KEY``
  （环境变量），这些都是公开数据，无需 OAuth。
- 仅「解析自己频道 ID」与「订阅数被频道设置隐藏时的兜底」两处复用
  ``scripts/video_upload`` 现成的 leo 账号 OAuth token（同一账号
  ace.leo.zhu@gmail.com），避免让用户重新配置一套凭据。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gui.youtube_cache import cache_get, cache_set  # noqa: E402

API_KEY_ENV = "YOUTUBE_DATA_API_KEY"
OWN_ACCOUNT_EMAIL = "ace.leo.zhu@gmail.com"
_OWN_CHANNEL_CACHE_KEY = "own_channel_id::leo"

_MAX_RESULTS_PER_PAGE = 50


class YoutubeApiError(RuntimeError):
    """YouTube Data API 调用失败（含缺少 API key）。"""


def _parse_iso8601(text: str) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_relative_time(published_at: str) -> str:
    """把 ISO8601 发布时间转成「1天前 / 1月前 / 1年前」这类相对时间文案。"""
    published = _parse_iso8601(published_at)
    if published is None:
        return ""
    seconds = max((datetime.now(timezone.utc) - published).total_seconds(), 0.0)
    minutes = seconds / 60
    if minutes < 60:
        return f"{max(1, int(minutes))}分钟前"
    hours = minutes / 60
    if hours < 24:
        return f"{max(1, int(hours))}小时前"
    days = hours / 24
    if days < 30:
        return f"{max(1, int(days))}天前"
    months = days / 30
    if months < 12:
        return f"{max(1, int(months))}月前"
    years = days / 365
    return f"{max(1, int(years))}年前"


@dataclass
class PlaylistInfo:
    id: str
    title: str
    item_count: int
    thumbnail_url: str = ""


@dataclass
class VideoInfo:
    id: str
    title: str
    description: str
    channel_id: str
    channel_title: str
    published_at: str
    thumbnail_url: str
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    duration: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def watch_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"

    def score(self) -> float:
        """简单爆款分（绝对量级）：观看数为主，点赞/评论加权（点赞比评论更常见，权重更低）。"""
        return self.view_count + self.like_count * 20 + self.comment_count * 40

    def days_since_published(self) -> float:
        """发布至今的天数（公开 Data API 拿不到逐日播放曲线，用此做增长速度的代理指标）。"""
        if not self.published_at:
            return 1.0
        try:
            text = self.published_at.replace("Z", "+00:00")
            published = datetime.fromisoformat(text)
        except ValueError:
            return 1.0
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - published).total_seconds() / 86400.0
        return max(days, 1.0)

    def views_per_day(self) -> float:
        """归一化「日均播放量」：识别近期快速增长的黑马，而非只看播放总量绝对值。"""
        return self.view_count / self.days_since_published()

    def growth_score(self) -> float:
        """归一化爆款分：日均观看为主，日均点赞/评论加权。"""
        days = self.days_since_published()
        return (self.view_count + self.like_count * 20 + self.comment_count * 40) / days

    def relative_age_label(self) -> str:
        """上传时间的相对文案，如「1天前 / 1月前 / 1年前」。"""
        return format_relative_time(self.published_at)


@dataclass
class ChannelInfo:
    id: str
    title: str
    subscriber_count: int
    hidden_subscriber_count: bool
    view_count: int
    video_count: int
    published_at: str
    thumbnail_url: str = ""

    @property
    def channel_url(self) -> str:
        return f"https://www.youtube.com/channel/{self.id}"


@dataclass
class OwnChannelOverview:
    channel: ChannelInfo
    uploads_playlist_id: str


def _api_key() -> str:
    key = (os.environ.get(API_KEY_ENV) or "").strip()
    if not key:
        raise YoutubeApiError(f"未设置环境变量 {API_KEY_ENV}，无法调用 YouTube Data API")
    return key


_api_key_service_cache: Any = None


def _api_key_service():
    global _api_key_service_cache
    if _api_key_service_cache is None:
        from googleapiclient.discovery import build

        _api_key_service_cache = build(
            "youtube", "v3", developerKey=_api_key(), cache_discovery=False
        )
    return _api_key_service_cache


_oauth_service_cache: Any = None
_oauth_error: str | None = None


def _oauth_service(*, log_fn: Callable[[str], None] | None = None):
    """复用 scripts/video_upload 的 leo 账号 OAuth token（若已授权且未过期）。"""
    global _oauth_service_cache, _oauth_error
    if _oauth_service_cache is not None:
        return _oauth_service_cache
    if _oauth_error is not None:
        raise YoutubeApiError(_oauth_error)
    try:
        from scripts.video_upload.youtube_upload import (
            DEFAULT_ACCOUNT,
            resolve_account_paths,
        )
        from scripts.video_upload.youtube_upload import get_youtube_service

        creds_path, token_path, account = resolve_account_paths(DEFAULT_ACCOUNT)
        if not token_path.is_file():
            raise YoutubeApiError(
                "未找到已授权的 YouTube OAuth token"
                f"（{token_path}）；请先在「上传 YouTube」步骤完成一次授权。"
            )
        _oauth_service_cache = get_youtube_service(
            credentials_path=creds_path,
            token_path=token_path,
            account=account,
            on_log=log_fn,
        )
        return _oauth_service_cache
    except Exception as exc:  # noqa: BLE001
        _oauth_error = f"OAuth 服务初始化失败：{exc}"
        raise YoutubeApiError(_oauth_error) from exc


def _run(request) -> dict[str, Any]:
    from googleapiclient.errors import HttpError

    try:
        return request.execute()
    except HttpError as exc:
        raise YoutubeApiError(f"YouTube API 错误：{exc}") from exc


def resolve_own_channel_id(*, force: bool = False, log_fn: Callable[[str], None] | None = None) -> str:
    if not force:
        cached = cache_get(_OWN_CHANNEL_CACHE_KEY, ttl_seconds=-1)
        if cached:
            return str(cached)
    service = _oauth_service(log_fn=log_fn)
    data = _run(service.channels().list(part="id", mine=True))
    items = data.get("items") or []
    if not items:
        raise YoutubeApiError("OAuth 账号下没有找到任何 YouTube 频道")
    channel_id = str(items[0]["id"])
    cache_set(_OWN_CHANNEL_CACHE_KEY, channel_id)
    return channel_id


def best_thumbnail_url(thumbnails: dict[str, Any]) -> str:
    for key in ("maxres", "standard", "high", "medium", "default"):
        item = thumbnails.get(key)
        if item and item.get("url"):
            return str(item["url"])
    return ""


def _channel_info_from_item(item: dict[str, Any]) -> ChannelInfo:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    return ChannelInfo(
        id=str(item.get("id") or ""),
        title=str(snippet.get("title") or ""),
        subscriber_count=int(stats.get("subscriberCount") or 0),
        hidden_subscriber_count=bool(stats.get("hiddenSubscriberCount")),
        view_count=int(stats.get("viewCount") or 0),
        video_count=int(stats.get("videoCount") or 0),
        published_at=str(snippet.get("publishedAt") or ""),
        thumbnail_url=best_thumbnail_url(snippet.get("thumbnails") or {}),
    )


def get_own_channel_overview(
    *, force_refresh: bool = False, log_fn: Callable[[str], None] | None = None
) -> OwnChannelOverview:
    """自有频道概览：优先 API key（公开数据），订阅数被隐藏时兜底走 OAuth。"""
    channel_id = resolve_own_channel_id(force=force_refresh, log_fn=log_fn)
    data = _run(
        _api_key_service().channels().list(
            part="snippet,statistics,contentDetails",
            id=channel_id,
        )
    )
    items = data.get("items") or []
    if not items:
        raise YoutubeApiError(f"找不到频道 {channel_id} 的公开信息")
    item = items[0]
    channel = _channel_info_from_item(item)
    uploads_playlist_id = (
        (item.get("contentDetails") or {}).get("relatedPlaylists", {}).get("uploads", "")
    )

    if channel.hidden_subscriber_count:
        try:
            oauth_data = _run(
                _oauth_service(log_fn=log_fn).channels().list(part="statistics", mine=True)
            )
            oauth_items = oauth_data.get("items") or []
            if oauth_items:
                stats = oauth_items[0].get("statistics") or {}
                channel.subscriber_count = int(stats.get("subscriberCount") or 0)
        except YoutubeApiError:
            pass

    return OwnChannelOverview(channel=channel, uploads_playlist_id=str(uploads_playlist_id))


def list_channel_playlists(channel_id: str) -> list[PlaylistInfo]:
    service = _api_key_service()
    playlists: list[PlaylistInfo] = []
    page_token: str | None = None
    while True:
        data = _run(
            service.playlists().list(
                part="snippet,contentDetails",
                channelId=channel_id,
                maxResults=_MAX_RESULTS_PER_PAGE,
                pageToken=page_token,
            )
        )
        for item in data.get("items") or []:
            snippet = item.get("snippet") or {}
            content = item.get("contentDetails") or {}
            playlists.append(
                PlaylistInfo(
                    id=str(item.get("id") or ""),
                    title=str(snippet.get("title") or "未命名系列"),
                    item_count=int(content.get("itemCount") or 0),
                    thumbnail_url=best_thumbnail_url(snippet.get("thumbnails") or {}),
                )
            )
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return playlists


def list_playlist_video_ids(playlist_id: str) -> list[str]:
    service = _api_key_service()
    ids: list[str] = []
    page_token: str | None = None
    while True:
        data = _run(
            service.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=_MAX_RESULTS_PER_PAGE,
                pageToken=page_token,
            )
        )
        for item in data.get("items") or []:
            vid = (item.get("contentDetails") or {}).get("videoId")
            if vid:
                ids.append(str(vid))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return ids


def _chunked(seq: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _video_info_from_item(item: dict[str, Any]) -> VideoInfo:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    content = item.get("contentDetails") or {}
    return VideoInfo(
        id=str(item.get("id") or ""),
        title=str(snippet.get("title") or ""),
        description=str(snippet.get("description") or ""),
        channel_id=str(snippet.get("channelId") or ""),
        channel_title=str(snippet.get("channelTitle") or ""),
        published_at=str(snippet.get("publishedAt") or ""),
        thumbnail_url=best_thumbnail_url(snippet.get("thumbnails") or {}),
        view_count=int(stats.get("viewCount") or 0),
        like_count=int(stats.get("likeCount") or 0),
        comment_count=int(stats.get("commentCount") or 0),
        duration=str(content.get("duration") or ""),
        tags=list(snippet.get("tags") or []),
    )


def get_videos_details(video_ids: list[str]) -> list[VideoInfo]:
    if not video_ids:
        return []
    service = _api_key_service()
    out: list[VideoInfo] = []
    for chunk in _chunked(video_ids, _MAX_RESULTS_PER_PAGE):
        data = _run(
            service.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(chunk),
            )
        )
        for item in data.get("items") or []:
            out.append(_video_info_from_item(item))
    return out


def get_channels_details(channel_ids: list[str]) -> dict[str, ChannelInfo]:
    ids = [c for c in dict.fromkeys(channel_ids) if c]
    if not ids:
        return {}
    service = _api_key_service()
    out: dict[str, ChannelInfo] = {}
    for chunk in _chunked(ids, _MAX_RESULTS_PER_PAGE):
        data = _run(
            service.channels().list(part="snippet,statistics", id=",".join(chunk))
        )
        for item in data.get("items") or []:
            info = _channel_info_from_item(item)
            out[info.id] = info
    return out


def search_video_ids(
    query: str,
    *,
    max_results: int = 25,
    order: str = "viewCount",
    region_code: str | None = None,
    relevance_language: str | None = None,
) -> list[str]:
    """``search.list``：单次调用消耗 100 配额，请勿在无缓存的情况下频繁调用。"""
    service = _api_key_service()
    ids: list[str] = []
    page_token: str | None = None
    while len(ids) < max_results:
        page_size = min(_MAX_RESULTS_PER_PAGE, max_results - len(ids))
        kwargs: dict[str, Any] = dict(
            part="id",
            q=query,
            type="video",
            order=order,
            maxResults=page_size,
            pageToken=page_token,
        )
        if region_code:
            kwargs["regionCode"] = region_code
        if relevance_language:
            kwargs["relevanceLanguage"] = relevance_language
        data = _run(service.search().list(**kwargs))
        for item in data.get("items") or []:
            vid = (item.get("id") or {}).get("videoId")
            if vid:
                ids.append(str(vid))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return ids


__all__ = [
    "API_KEY_ENV",
    "OWN_ACCOUNT_EMAIL",
    "YoutubeApiError",
    "PlaylistInfo",
    "VideoInfo",
    "ChannelInfo",
    "OwnChannelOverview",
    "best_thumbnail_url",
    "format_relative_time",
    "resolve_own_channel_id",
    "get_own_channel_overview",
    "list_channel_playlists",
    "list_playlist_video_ids",
    "get_videos_details",
    "get_channels_details",
    "search_video_ids",
]
