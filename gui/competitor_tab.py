"""Tab 3「爆款分析」：聚合同类 rain ASMR 高赞/高评论/高观看视频，按作者分组 + LLM 优点分析。

关键词默认「leaf rain」，可在输入框中改成任意自定义关键词（逗号分隔可搜索多个）。

配额策略：``search.list`` 单次调用消耗 100 配额，因此每组关键词的搜索结果按
24 小时 TTL 缓存在本地（见 ``gui/youtube_cache.py``），仅点击「刷新」时才会
重新拉取（可选是否忽略缓存强制刷新）。

每个作者分组标题栏右上角有「✕」删除按钮：删除后会从预备池里补一个新分组，
优先挑选「黑马」——总播放量还不高、但日均播放量（归一化播放次数）增长很快
的作者，而不是简单地按总播放量再选一个大号。删除记录按关键词组合本地持久化
（不设 TTL），重启应用 / 重新抓取后依然不会再出现。
"""

from __future__ import annotations

import dataclasses
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gui.tk_thread import bind_ui_root, schedule_on_main  # noqa: E402
from gui.ui_theme import LIGHT, UiTheme, grid_theme  # noqa: E402
from gui.video_insight import cached_insight  # noqa: E402
from gui.youtube_api import ChannelInfo, VideoInfo, YoutubeApiError, format_relative_time  # noqa: E402
from gui.youtube_cache import cache_age_seconds, cache_get, cache_set, download_thumbnail  # noqa: E402
from gui.youtube_grid_common import (  # noqa: E402
    CELL_H,
    CELL_W,
    bind_mousewheel_deep,
    build_grid_cell,
    compute_cols,
    load_local_image,
    mark_cell_analyzed,
)
from gui.youtube_preview_panel import YoutubePreviewPanel, open_in_browser  # noqa: E402

DEFAULT_KEYWORDS_TEXT = "leaf rain"

_SEARCH_MAX_RESULTS = 25
_MAX_KEYWORDS = 6
_INITIAL_GROUPS_SHOWN = 10
_MAX_PER_AUTHOR_SHOWN = 10
_CACHE_TTL_SEC = 24 * 3600
# v3：关键词可自定义（不再局限于内置的 4 组「叶子+雨/池塘/森林/小路」预设），
# 且每个关键词额外拉取一次按「最新发布」排序的结果，扩大候选池、方便挖掘黑马。
_POOL_CACHE_KEY_PREFIX = "competitor_pool_v3::"
# 用户手动删除的分组（按作者频道 id）持久化在磁盘上（不设 TTL，永不过期），
# 跟当前关键词组合绑定：切换关键词等于换一批候选池，删除记录自然不跟着搬；
# 同一组关键词下，重启应用 / 点「刷新」重新抓取后，这些频道也不会再出现在
# 首屏或预备池里，除非用户清空本地缓存。
_DELETED_CACHE_KEY_PREFIX = "competitor_deleted_v1::"


def _video_to_dict(v: VideoInfo) -> dict:
    return dataclasses.asdict(v)


def _video_from_dict(d: dict) -> VideoInfo:
    return VideoInfo(**d)


def _channel_to_dict(c: ChannelInfo) -> dict:
    return dataclasses.asdict(c)


def _channel_from_dict(d: dict) -> ChannelInfo:
    return ChannelInfo(**d)


def _parse_keywords(text: str) -> list[str]:
    parts = [p.strip() for p in text.replace("，", ",").split(",")]
    keywords = [p for p in parts if p]
    return keywords[:_MAX_KEYWORDS] or [DEFAULT_KEYWORDS_TEXT]


def _darkhorse_score(v: VideoInfo) -> float:
    """「黑马」优先级：总播放量还不算高、但日均播放量（归一化）很高的视频优先。

    用 ``views_per_day / sqrt(view_count)`` 而不是单纯用日均播放量本身，是为了
    压低那些总量已经很大的老爆款（它们日均播放量也可能很高，但已经不是「黑马」）。
    """
    return v.views_per_day() / ((v.view_count + 1) ** 0.5)


class CompetitorTab(ttk.Frame):
    """同类爆款视频聚合视图。

    预览 / LLM 分析 / 浏览器播放 UI 由调用方（``gui/app.py``）传入的共享
    ``YoutubePreviewPanel`` 负责，渲染在应用最外层的右半边，本 Tab 只负责
    左半边的关键词输入 + 分组宫格。
    """

    def __init__(
        self,
        parent: tk.Widget,
        *,
        preview: YoutubePreviewPanel,
        log_fn: Callable[[str], None] | None = None,
        initial_keywords: str | None = None,
        on_keywords_changed: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, padding=8)
        self._log = log_fn or (lambda _m: None)
        self._preview = preview
        self._initial_keywords_text = (initial_keywords or "").strip() or DEFAULT_KEYWORDS_TEXT
        self._on_keywords_changed = on_keywords_changed or (lambda _t: None)
        self._loading = False
        self._loaded_once = False
        self._photo_refs: list = []
        self._videos_by_id: dict[str, VideoInfo] = {}
        self._channels_by_id: dict[str, ChannelInfo] = {}
        self._cells: dict[str, dict] = {}
        self._sections: dict[str, tk.Widget] = {}
        self._channel_videos: dict[str, list[VideoInfo]] = {}
        self._shown_channel_order: list[str] = []
        self._reserve_channel_ids: list[str] = []
        self._current_keywords: list[str] = []
        self._deleted_channel_ids: set[str] = set()
        self._grid_theme = grid_theme(LIGHT)
        self._build_ui()
        bind_ui_root(self)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(toolbar, text="刷新（重新抓取）", command=lambda: self.refresh(force=True)).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="使用缓存加载", command=lambda: self.refresh(force=False)).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        self._lbl_summary = ttk.Label(toolbar, text="尚未加载")
        self._lbl_summary.pack(side=tk.LEFT, padx=(12, 0))

        keyword_row = ttk.Frame(self)
        keyword_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(keyword_row, text="关键词：").pack(side=tk.LEFT)
        self._keyword_var = tk.StringVar(value=self._initial_keywords_text)
        keyword_entry = ttk.Entry(keyword_row, textvariable=self._keyword_var, width=40)
        keyword_entry.pack(side=tk.LEFT, padx=(0, 6))
        keyword_entry.bind("<Return>", lambda _e: self.refresh(force=True))
        keyword_entry.bind("<FocusOut>", lambda _e: self._persist_keywords_text())
        ttk.Label(keyword_row, text="（逗号分隔多个关键词，默认 leaf rain，回车即可重新抓取）", foreground="gray").pack(
            side=tk.LEFT
        )

        ttk.Label(
            self,
            text="按「日均播放量」（发布至今归一化，识别快速增长的黑马）排序，每位作者展示 Top 10 · "
            "单击视频宫格预览 · 双击直接播放 · 单击标题条查看频道信息 · "
            "分组标题栏「✕」可删除并自动补充黑马新分组（删除记录本地持久化，重启后依然生效） · "
            "黄色边框＝已做过 LLM 优点分析 · "
            "search.list 有配额限制，结果本地缓存 24 小时",
            foreground="gray",
            wraplength=700,
            justify=tk.LEFT,
        ).pack(fill=tk.X, anchor=tk.W, pady=(0, 4))

        self._lbl_status = ttk.Label(self, text="", foreground="gray")
        self._lbl_status.pack(fill=tk.X, anchor=tk.W, pady=(0, 6))

        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)
        self._canvas = tk.Canvas(container, highlightthickness=0)
        vscroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._grid_host = ttk.Frame(self._canvas)
        self._canvas_window = self._canvas.create_window((0, 0), window=self._grid_host, anchor=tk.NW)
        self._grid_host.bind("<Configure>", lambda _e: self._sync_scroll_region())
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        for w in (container, self._canvas, self._grid_host):
            w.bind("<MouseWheel>", self._on_mousewheel)
            w.bind("<Button-4>", self._on_mousewheel)
            w.bind("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event) -> None:
        if not self.winfo_ismapped():
            return
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            delta = -1 * (event.delta // 120) if event.delta else 0
        if delta:
            self._canvas.yview_scroll(delta, "units")

    def _on_canvas_configure(self, event=None) -> None:
        if event is not None:
            self._canvas.itemconfigure(self._canvas_window, width=event.width)
        self._sync_scroll_region()

    def _sync_scroll_region(self) -> None:
        self.update_idletasks()
        w = max(self._grid_host.winfo_reqwidth(), self._canvas.winfo_width(), 1)
        h = max(self._grid_host.winfo_reqheight(), 1)
        self._canvas.configure(scrollregion=(0, 0, w, h))

    def on_tab_selected(self) -> None:
        if not self._loaded_once:
            self.refresh(force=False)

    def _persist_keywords_text(self) -> None:
        keywords = _parse_keywords(self._keyword_var.get())
        text = ", ".join(keywords)
        if self._keyword_var.get() != text:
            self._keyword_var.set(text)
        self._on_keywords_changed(text)

    def refresh(self, *, force: bool) -> None:
        if self._loading:
            return
        keywords = _parse_keywords(self._keyword_var.get())
        self._keyword_var.set(", ".join(keywords))
        self._on_keywords_changed(", ".join(keywords))
        self._loading = True
        self._lbl_status.configure(text="加载中…（搜索关键词 / 拉取视频与频道数据）")
        threading.Thread(target=self._load_bg, args=(force, keywords), daemon=True).start()

    def _fetch_pool(
        self, force: bool, keywords: list[str]
    ) -> tuple[list[VideoInfo], dict[str, ChannelInfo], bool]:
        """返回 (视频池, 频道信息, 是否命中缓存)。"""
        from gui import youtube_api as yt

        cache_key = _POOL_CACHE_KEY_PREFIX + "|".join(keywords)

        if not force:
            cached = cache_get(cache_key, ttl_seconds=_CACHE_TTL_SEC)
            if cached:
                videos = [_video_from_dict(d) for d in cached.get("videos", [])]
                channels = {
                    cid: _channel_from_dict(d) for cid, d in (cached.get("channels") or {}).items()
                }
                return videos, channels, True

        seen_ids: dict[str, None] = {}
        for kw in keywords:
            # 分别按「总播放量」和「最新发布」各搜一次：只按播放量排序容易只捞到
            # 早已成名的老爆款，加一路「最新发布」能补充刚起量、还没冲上总量榜的黑马候选。
            self._log(f"[爆款分析] 搜索关键词「{kw}」（按播放量）…")
            for vid in yt.search_video_ids(kw, max_results=_SEARCH_MAX_RESULTS, order="viewCount"):
                seen_ids.setdefault(vid, None)
            self._log(f"[爆款分析] 搜索关键词「{kw}」（按最新发布，挖黑马）…")
            for vid in yt.search_video_ids(kw, max_results=_SEARCH_MAX_RESULTS, order="date"):
                seen_ids.setdefault(vid, None)

        all_details = yt.get_videos_details(list(seen_ids.keys()))

        channel_ids = list(dict.fromkeys(v.channel_id for v in all_details))
        channels = yt.get_channels_details(channel_ids)

        cache_set(
            cache_key,
            {
                "videos": [_video_to_dict(v) for v in all_details],
                "channels": {cid: _channel_to_dict(c) for cid, c in channels.items()},
            },
        )
        return all_details, channels, False

    def _load_bg(self, force: bool, keywords: list[str]) -> None:
        try:
            videos, channels, from_cache = self._fetch_pool(force, keywords)
            for v in videos:
                download_thumbnail(v.thumbnail_url)
            for c in channels.values():
                download_thumbnail(c.thumbnail_url)
            schedule_on_main(self, self._render, videos, channels, from_cache, keywords)
        except YoutubeApiError as exc:
            schedule_on_main(self, self._on_error, str(exc))
        except Exception as exc:  # noqa: BLE001
            schedule_on_main(self, self._on_error, f"未知错误：{exc}")

    def _on_error(self, msg: str) -> None:
        self._loading = False
        self._lbl_status.configure(text=f"加载失败：{msg}")
        self._log(f"[爆款分析] 加载失败：{msg}")

    @staticmethod
    def _deleted_cache_key(keywords: list[str]) -> str:
        return _DELETED_CACHE_KEY_PREFIX + "|".join(keywords)

    def _load_deleted_ids(self, keywords: list[str]) -> set[str]:
        raw = cache_get(self._deleted_cache_key(keywords), ttl_seconds=-1)
        return set(raw) if isinstance(raw, list) else set()

    def _save_deleted_ids(self) -> None:
        cache_set(self._deleted_cache_key(self._current_keywords), sorted(self._deleted_channel_ids))

    def _render(
        self,
        videos: list[VideoInfo],
        channels: dict[str, ChannelInfo],
        from_cache: bool,
        keywords: list[str],
    ) -> None:
        self._loading = False
        self._loaded_once = True
        self._photo_refs.clear()
        self._videos_by_id.clear()
        self._cells.clear()
        self._sections.clear()
        self._channel_videos.clear()
        self._shown_channel_order.clear()
        self._reserve_channel_ids.clear()
        self._channels_by_id = dict(channels)
        self._current_keywords = keywords
        self._deleted_channel_ids = self._load_deleted_ids(keywords)
        for child in self._grid_host.winfo_children():
            child.destroy()

        cache_key = _POOL_CACHE_KEY_PREFIX + "|".join(keywords)
        age = cache_age_seconds(cache_key)
        age_text = f"（{int(age // 60)} 分钟前抓取）" if age is not None else ""
        source_text = "本地缓存" if from_cache else "刚刚抓取"
        self._lbl_summary.configure(text=f"聚合 {len(videos)} 个爆款视频 · {source_text}{age_text}")

        groups: dict[str, list[VideoInfo]] = {}
        order: list[str] = []
        for v in videos:
            self._videos_by_id[v.id] = v
            if v.channel_id not in groups:
                groups[v.channel_id] = []
                order.append(v.channel_id)
            groups[v.channel_id].append(v)
        self._channel_videos = groups

        # 主排序：按各分组内最高日均播放量降序，作为首屏展示顺序；已被用户手动
        # 删除过的作者（本地持久化，见 _DELETED_CACHE_KEY_PREFIX）排除在外，
        # 不管是首屏还是预备池都不应该再出现，除非清空本地缓存。
        order = [cid for cid in order if cid not in self._deleted_channel_ids]
        order.sort(key=lambda cid: max(v.growth_score() for v in groups[cid]), reverse=True)
        shown = order[:_INITIAL_GROUPS_SHOWN]
        remaining = order[_INITIAL_GROUPS_SHOWN:]
        # 预备池：按「黑马优先级」重新排序，删除分组后优先从这里补充。
        remaining.sort(key=lambda cid: max(_darkhorse_score(v) for v in groups[cid]), reverse=True)
        self._reserve_channel_ids = remaining

        if not shown:
            ttk.Label(self._grid_host, text="没有抓取到视频（可能是网络问题或配额用尽）").pack(
                padx=8, pady=8
            )
        for channel_id in shown:
            self._append_group(channel_id)

        self._lbl_status.configure(
            text=(
                f"共 {len(order)} 位作者（展示 {len(shown)}，预备 {len(remaining)}）· "
                f"每位作者按日均播放量展示 Top {_MAX_PER_AUTHOR_SHOWN}"
            )
        )
        bind_mousewheel_deep(self._grid_host, self._on_mousewheel)
        self.after_idle(self._sync_scroll_region)

    def _append_group(self, channel_id: str) -> None:
        vids_all = self._channel_videos.get(channel_id) or []
        if not vids_all:
            return
        vids = sorted(vids_all, key=lambda v: v.growth_score(), reverse=True)[:_MAX_PER_AUTHOR_SHOWN]
        channel = self._channels_by_id.get(channel_id)
        title = channel.title if channel else vids[0].channel_title
        self._render_author_section(channel_id, f"👤 {title}（{len(vids_all)}）", vids)
        self._shown_channel_order.append(channel_id)

    def _render_author_section(self, channel_id: str, title: str, videos: list[VideoInfo]) -> None:
        # 独立的行块（LabelFrame）+ 明显的彩色标题条，确保每个作者分组在视觉上清晰分隔，
        # 而不是所有宫格挤成一整块。
        colors = self._grid_theme
        section = ttk.LabelFrame(self._grid_host, padding=(0, 0, 0, 6))
        section.pack(fill=tk.X, padx=4, pady=(0, 12), anchor=tk.W)
        self._sections[channel_id] = section

        header_bar = tk.Frame(section, bg=colors.border_hover)
        header_bar.pack(fill=tk.X)

        header = tk.Label(
            header_bar,
            text=f"{title}　·　点击查看该作者频道信息",
            bg=colors.border_hover,
            fg="#ffffff",
            font=("", 9, "bold"),
            anchor=tk.W,
            padx=8,
            pady=4,
            cursor="hand2",
        )
        header.pack(side=tk.LEFT, fill=tk.X, expand=True)
        header.bind("<Button-1>", lambda _e, cid=channel_id: self._on_select_channel(cid))

        del_btn = tk.Label(
            header_bar,
            text="✕",
            bg=colors.border_hover,
            fg="#ffffff",
            font=("", 10, "bold"),
            padx=8,
            pady=4,
            cursor="hand2",
        )
        del_btn.pack(side=tk.RIGHT)
        del_btn.bind("<Button-1>", lambda _e, cid=channel_id: self._on_delete_group(cid))

        grid_frame = ttk.Frame(section, padding=(6, 6, 6, 0))
        grid_frame.pack(fill=tk.X)

        cols = compute_cols(self._canvas.winfo_width())
        for idx, v in enumerate(videos):
            row, col = divmod(idx, cols)
            thumb_path = download_thumbnail(v.thumbnail_url)
            img = load_local_image(thumb_path, target_w=CELL_W - 4, target_h=CELL_H - 4)
            age_label = format_relative_time(v.published_at)
            subtitle = (
                f"📈{self._fmt_compact(v.views_per_day())}/天　👁{self._fmt_compact(v.view_count)}"
                + (f"　🕒{age_label}" if age_label else "")
            )
            cell = build_grid_cell(
                grid_frame,
                row=row,
                col=col,
                title=v.title,
                subtitle=subtitle,
                image=img,
                theme=self._grid_theme,
                photo_refs=self._photo_refs,
                on_click=lambda vid=v.id: self._on_select_video(vid),
                on_double_click=lambda vid=v.id: self._on_play_video(vid),
                highlighted=bool(cached_insight(v.id)),
            )
            self._cells[v.id] = cell

    def _on_delete_group(self, channel_id: str) -> None:
        section = self._sections.pop(channel_id, None)
        if section is not None:
            section.destroy()
        if channel_id in self._shown_channel_order:
            self._shown_channel_order.remove(channel_id)
        for vid in [v.id for v in self._channel_videos.get(channel_id, [])]:
            self._cells.pop(vid, None)

        self._deleted_channel_ids.add(channel_id)
        self._save_deleted_ids()

        channel = self._channels_by_id.get(channel_id)
        title = channel.title if channel else "该作者"
        self._log(f"[爆款分析] 已删除分组「{title}」（重启后仍保持删除），尝试补充黑马新分组…")

        appended = self._append_next_reserve_group()
        if appended:
            self._lbl_status.configure(
                text=(
                    f"共 {len(self._shown_channel_order)} 位作者（预备 {len(self._reserve_channel_ids)}）· "
                    f"每位作者按日均播放量展示 Top {_MAX_PER_AUTHOR_SHOWN}"
                )
            )
        else:
            self._lbl_status.configure(
                text=f"共 {len(self._shown_channel_order)} 位作者 · 没有更多预备黑马分组了，可点击刷新重新抓取"
            )
        self.after_idle(self._sync_scroll_region)

    def _append_next_reserve_group(self) -> bool:
        while self._reserve_channel_ids:
            cid = self._reserve_channel_ids.pop(0)
            if cid in self._shown_channel_order:
                continue
            self._append_group(cid)
            bind_mousewheel_deep(self._sections[cid], self._on_mousewheel)
            return True
        self._log("[爆款分析] 预备池已空，没有更多黑马候选分组了")
        return False

    @staticmethod
    def _fmt_compact(n: float) -> str:
        n = float(n)
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(int(n))

    def _on_select_video(self, video_id: str) -> None:
        video = self._videos_by_id.get(video_id)
        if not video:
            return
        self._preview.show_video(video)
        self._log(f"[爆款分析] 预览：{video.title}")

    def _on_play_video(self, video_id: str) -> None:
        video = self._videos_by_id.get(video_id)
        if not video:
            return
        self._on_select_video(video_id)
        open_in_browser(video.watch_url)
        self._log(f"[爆款分析] 在浏览器播放：{video.title}")

    def _on_video_analyzed(self, video: VideoInfo) -> None:
        """LLM 分析成功完成后，把对应宫格边框标记为黄色（若当前仍在视图中）。"""
        cell = self._cells.get(video.id)
        if cell:
            mark_cell_analyzed(cell)

    def _on_select_channel(self, channel_id: str) -> None:
        channel = self._channels_by_id.get(channel_id)
        if not channel:
            return
        self._preview.show_channel(channel)
        self._log(f"[爆款分析] 查看频道：{channel.title}")

    def apply_theme(self, theme: UiTheme) -> None:
        self._grid_theme = grid_theme(theme)
        self._preview.apply_theme(theme)


__all__ = ["CompetitorTab", "DEFAULT_KEYWORDS_TEXT"]
