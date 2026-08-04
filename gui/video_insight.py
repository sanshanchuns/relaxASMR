"""调用 agy（Antigravity Gemini）分析爆款视频的成功要素：封面、标题、内容、描述。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gui.youtube_api import VideoInfo  # noqa: E402
from gui.youtube_cache import (  # noqa: E402
    INSIGHT_DIR,
    cache_clear,
    cache_get,
    cache_set,
    download_thumbnail,
)

_SYSTEM_PROMPT = (
    "你是资深 YouTube 增长顾问，专注 ASMR / 助眠 / 白噪音赛道的选题与包装分析。"
    "回答使用简体中文，条理清晰、可直接指导选题与封面制作，不要空泛的套话。"
)

_PROMPT_TEMPLATE = """请分析这条 YouTube 爆款视频为什么受欢迎，聚焦"雨声 / ASMR / 助眠"赛道的选题与包装角度。

视频信息：
- 标题：{title}
- 频道：{channel_title}
- 观看数：{views:,} | 点赞数：{likes:,} | 评论数：{comments:,}
- 发布时间：{published_at}
- 标签：{tags}
- 描述（截取前 800 字）：
{description}

附图是视频封面缩略图。请结合封面图 + 标题 + 描述 + 数据表现，从以下几个角度分析：
1. 封面设计：构图、色调、文字、情绪暗示等吸引点击的要素
2. 标题写法：关键词、结构、痛点/场景词的运用
3. 内容/场景卖点：为什么这个场景（如雨打树叶、湖边、森林小路等）能吸引助眠/放松类观众
4. 可复用的选题/包装建议：给「rain ASMR for sleep/focus」频道 2-3 条具体可执行的建议

请用简洁的分点输出，每点不超过 3 句话。
"""

_OWN_SYSTEM_PROMPT = (
    "你是资深 YouTube 增长顾问，专注 ASMR / 助眠 / 白噪音赛道的选题与包装分析。"
    "回答使用简体中文，条理清晰、可直接指导选题与封面制作，不要空泛的套话；"
    "既要肯定做得好的地方，也要毫不客气地指出可以改进的地方。"
)

_OWN_PROMPT_TEMPLATE = """请分析这条我自己频道（rain ASMR for sleep/focus）发布的视频，找出优点和不足，给出可执行的改进建议。

视频信息：
- 标题：{title}
- 频道：{channel_title}
- 观看数：{views:,} | 点赞数：{likes:,} | 评论数：{comments:,} | 日均播放：{views_per_day:.0f}
- 发布时间：{published_at}
- 标签：{tags}
- 描述（截取前 800 字）：
{description}

附图是视频封面缩略图。请结合封面图 + 标题 + 描述 + 数据表现，从以下几个角度分析：
1. 优点：封面 / 标题 / 选题 / 内容中做得好、值得延续的地方
2. 不足：可能拖累点击率或播放量的问题（封面 / 标题 / 选题 / 描述 / 时长节奏等）
3. 与同赛道爆款的差距：对比典型「叶子 + 雨」类爆款视频，缺了什么
4. 具体改进建议：给出 2-3 条可直接执行的优化动作（如何调整封面 / 标题 / 下一期选题）

请用简洁的分点输出，每点不超过 3 句话，优点和不足要分开清晰列出。
"""


def _insight_cache_key(video_id: str) -> str:
    return f"insight::{video_id}"


def _own_insight_cache_key(video_id: str) -> str:
    return f"own_insight::{video_id}"


def cached_insight(video_id: str) -> str | None:
    return cache_get(_insight_cache_key(video_id), ttl_seconds=-1)


def clear_cached_insight(video_id: str) -> None:
    cache_clear(_insight_cache_key(video_id))


def cached_own_insight(video_id: str) -> str | None:
    return cache_get(_own_insight_cache_key(video_id), ttl_seconds=-1)


def clear_cached_own_insight(video_id: str) -> None:
    cache_clear(_own_insight_cache_key(video_id))


def _run_analysis(
    video: VideoInfo,
    *,
    cache_key: str,
    system: str,
    prompt_template: str,
    force: bool,
    log_fn: Callable[[str], None] | None,
) -> str:
    if not force:
        cached = cache_get(cache_key, ttl_seconds=-1)
        if cached:
            return cached

    from scripts.config.paths import ensure_cli_path

    ensure_cli_path()
    from agy import AgyDirectError, generate_text_via_agy_accounts, has_agy_credentials

    if not has_agy_credentials():
        return (
            "⚠️ 未配置 agy 凭据（cli/agy/credentials.json），无法调用 LLM 分析。\n"
            "请参考 economist/agy 方案放置凭据后重试。"
        )

    images: list[tuple[str, bytes]] = []
    thumb_path = download_thumbnail(video.thumbnail_url)
    if thumb_path is not None:
        try:
            images.append(("image/jpeg", thumb_path.read_bytes()))
        except OSError:
            pass

    description = (video.description or "").strip()[:800] or "（无描述）"
    prompt = prompt_template.format(
        title=video.title,
        channel_title=video.channel_title,
        views=video.view_count,
        likes=video.like_count,
        comments=video.comment_count,
        views_per_day=video.views_per_day(),
        published_at=video.published_at,
        tags=", ".join(video.tags[:15]) or "（无标签）",
        description=description,
    )

    try:
        text, _email = generate_text_via_agy_accounts(
            prompt,
            model="gemini-3.6-flash",
            effort="medium",
            system=system,
            images=images or None,
            log_fn=log_fn,
        )
    except AgyDirectError as exc:
        return f"⚠️ LLM 分析失败：{exc}"
    except Exception as exc:  # noqa: BLE001
        return f"⚠️ LLM 分析失败：{exc}"

    text = text.strip() or "（LLM 未返回内容）"
    cache_set(cache_key, text)
    return text


def analyze_video_success(
    video: VideoInfo,
    *,
    force: bool = False,
    log_fn: Callable[[str], None] | None = None,
) -> str:
    """返回该视频的爆款要素分析文本（含磁盘缓存，避免重复消耗 LLM 配额）。

    用于「爆款分析」Tab：只关注优点，帮助从同类爆款中提炼可复用的选题/包装经验。

    ``log_fn``：进度日志回调；GUI 调用时传入界面日志区回调，避免 agy 调用日志
    只打印在后台终端看不到。
    """
    return _run_analysis(
        video,
        cache_key=_insight_cache_key(video.id),
        system=_SYSTEM_PROMPT,
        prompt_template=_PROMPT_TEMPLATE,
        force=force,
        log_fn=log_fn,
    )


def analyze_own_video(
    video: VideoInfo,
    *,
    force: bool = False,
    log_fn: Callable[[str], None] | None = None,
) -> str:
    """返回自有频道视频的优劣分析文本（含磁盘缓存，避免重复消耗 LLM 配额）。

    用于「我的数据」Tab：既指出优点也指出不足，帮助改进后续选题与包装。
    """
    return _run_analysis(
        video,
        cache_key=_own_insight_cache_key(video.id),
        system=_OWN_SYSTEM_PROMPT,
        prompt_template=_OWN_PROMPT_TEMPLATE,
        force=force,
        log_fn=log_fn,
    )


__all__ = [
    "INSIGHT_DIR",
    "analyze_video_success",
    "analyze_own_video",
    "cached_insight",
    "clear_cached_insight",
    "cached_own_insight",
    "clear_cached_own_insight",
]
