"""Tab 2「我的数据」：自有频道订阅数/视频数 + 按系列（播放列表）分类的宫格预览。"""

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
from gui.video_insight import cached_own_insight  # noqa: E402
from gui.youtube_api import (  # noqa: E402
    ChannelInfo,
    OwnChannelOverview,
    PlaylistInfo,
    VideoInfo,
    YoutubeApiError,
)
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

# 数据信息（频道概览/播放列表/视频详情）本地缓存：跟「爆款分析」Tab 的
# search.list 结果缓存同一套 gui/youtube_cache 机制，避免每次切换 Tab 都要
# 重新拉一遍频道 + 每个播放列表 + 全部视频详情，加速冷启动。封面缩略图另有
# 单独的、不过期的磁盘缓存（见 ``download_thumbnail``），此处不需要重复处理。
_DATA_CACHE_KEY = "my_channel_data_v1"
_CACHE_TTL_SEC = 24 * 3600


def _video_to_dict(v: VideoInfo) -> dict:
    return dataclasses.asdict(v)


def _video_from_dict(d: dict) -> VideoInfo:
    return VideoInfo(**d)


def _channel_to_dict(c: ChannelInfo) -> dict:
    return dataclasses.asdict(c)


def _channel_from_dict(d: dict) -> ChannelInfo:
    return ChannelInfo(**d)


def _playlist_to_dict(p: PlaylistInfo) -> dict:
    return dataclasses.asdict(p)


def _playlist_from_dict(d: dict) -> PlaylistInfo:
    return PlaylistInfo(**d)


class MyChannelTab(ttk.Frame):
    """自有频道宫格视图。

    预览 / LLM 优劣分析 / 浏览器播放 UI 不再内嵌在本 Tab 里分栏显示，而是交给
    调用方（``gui/app.py``）传入的共享 ``YoutubePreviewPanel``，渲染在应用最外层
    的右半边——这样本 Tab 就能用整个左半边展示宫格，而不是把预览区又挤进本已
    只占应用一半宽度的左侧 Tab 内部。
    """

    def __init__(
        self,
        parent: tk.Widget,
        *,
        preview: YoutubePreviewPanel,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, padding=8)
        self._log = log_fn or (lambda _m: None)
        self._preview = preview
        self._loading = False
        self._loaded_once = False
        self._photo_refs: list = []
        self._cells: dict[str, dict] = {}
        self._videos_by_id: dict[str, VideoInfo] = {}
        self._selected_id: str | None = None
        self._grid_theme = grid_theme(LIGHT)
        self._build_ui()
        bind_ui_root(self)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(toolbar, text="刷新（重新抓取）", command=lambda: self.refresh(force=True)).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="使用缓存加载", command=lambda: self.refresh(force=False)).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        self._lbl_summary = ttk.Label(toolbar, text="尚未加载")
        self._lbl_summary.pack(side=tk.LEFT, padx=(12, 0))
        ttk.Label(
            toolbar,
            text="单击宫格预览 · 双击 / 右侧「播放」按钮在浏览器打开播放 · 黄色边框＝已做过 LLM 优劣分析",
            foreground="gray",
        ).pack(side=tk.RIGHT)

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
        self.refresh(force=False)

    def refresh(self, *, force: bool = False) -> None:
        if self._loading:
            return
        self._loading = True
        self._lbl_status.configure(text="加载中…（拉取频道 / 播放列表 / 视频数据）")
        threading.Thread(target=self._load_bg, args=(force,), daemon=True).start()

    def _fetch_data(
        self, force: bool
    ) -> tuple[
        OwnChannelOverview,
        list[PlaylistInfo],
        dict[str, list[VideoInfo]],
        list[VideoInfo],
        list[VideoInfo],
        bool,
    ]:
        """返回 (频道概览, 播放列表, 系列→视频, 未分类视频, 全部视频, 是否命中缓存)。"""
        if not force:
            cached = cache_get(_DATA_CACHE_KEY, ttl_seconds=_CACHE_TTL_SEC)
            if cached:
                overview = OwnChannelOverview(
                    channel=_channel_from_dict(cached["channel"]),
                    uploads_playlist_id=cached["uploads_playlist_id"],
                )
                playlists = [_playlist_from_dict(d) for d in cached.get("playlists", [])]
                all_videos = [_video_from_dict(d) for d in cached.get("all_videos", [])]
                videos_by_id = {v.id: v for v in all_videos}
                playlist_video_ids: dict[str, list[str]] = cached.get("playlist_video_ids", {})
                playlist_video_map = {
                    pid: [videos_by_id[i] for i in ids if i in videos_by_id]
                    for pid, ids in playlist_video_ids.items()
                }
                classified_ids = {i for ids in playlist_video_ids.values() for i in ids}
                unclassified = [v for v in all_videos if v.id not in classified_ids]
                return overview, playlists, playlist_video_map, unclassified, all_videos, True

        from gui import youtube_api as yt

        overview = yt.get_own_channel_overview(force_refresh=force, log_fn=self._log)
        playlists = yt.list_channel_playlists(overview.channel.id)
        uploads_ids = yt.list_playlist_video_ids(overview.uploads_playlist_id)
        all_videos = yt.get_videos_details(uploads_ids)
        videos_by_id = {v.id: v for v in all_videos}

        playlist_video_map: dict[str, list[VideoInfo]] = {}
        playlist_video_ids: dict[str, list[str]] = {}
        classified_ids: set[str] = set()
        for p in playlists:
            ids = yt.list_playlist_video_ids(p.id)
            vids = [videos_by_id[i] for i in ids if i in videos_by_id]
            vids.sort(key=lambda v: v.view_count, reverse=True)
            playlist_video_map[p.id] = vids
            playlist_video_ids[p.id] = [v.id for v in vids]
            classified_ids.update(ids)

        unclassified = [v for v in all_videos if v.id not in classified_ids]
        unclassified.sort(key=lambda v: v.view_count, reverse=True)

        cache_set(
            _DATA_CACHE_KEY,
            {
                "channel": _channel_to_dict(overview.channel),
                "uploads_playlist_id": overview.uploads_playlist_id,
                "playlists": [_playlist_to_dict(p) for p in playlists],
                "all_videos": [_video_to_dict(v) for v in all_videos],
                "playlist_video_ids": playlist_video_ids,
            },
        )
        return overview, playlists, playlist_video_map, unclassified, all_videos, False

    def _load_bg(self, force: bool) -> None:
        try:
            overview, playlists, playlist_video_map, unclassified, all_videos, from_cache = (
                self._fetch_data(force)
            )
            for v in all_videos:
                download_thumbnail(v.thumbnail_url)

            schedule_on_main(
                self,
                self._render,
                overview,
                playlists,
                playlist_video_map,
                unclassified,
                all_videos,
                from_cache,
            )
        except YoutubeApiError as exc:
            schedule_on_main(self, self._on_error, str(exc))
        except Exception as exc:  # noqa: BLE001
            schedule_on_main(self, self._on_error, f"未知错误：{exc}")

    def _on_error(self, msg: str) -> None:
        self._loading = False
        self._lbl_status.configure(text=f"加载失败：{msg}")
        self._log(f"[我的数据] 加载失败：{msg}")

    def _render(
        self,
        overview: OwnChannelOverview,
        playlists: list[PlaylistInfo],
        playlist_video_map: dict[str, list[VideoInfo]],
        unclassified: list[VideoInfo],
        all_videos: list[VideoInfo],
        from_cache: bool = False,
    ) -> None:
        self._loading = False
        self._loaded_once = True
        self._photo_refs.clear()
        self._cells.clear()
        self._videos_by_id.clear()
        for child in self._grid_host.winfo_children():
            child.destroy()

        age = cache_age_seconds(_DATA_CACHE_KEY)
        age_text = f"（{int(age // 60)} 分钟前抓取）" if age is not None else ""
        source_text = "本地缓存" if from_cache else "刚刚抓取"

        ch = overview.channel
        sub_text = "已隐藏" if ch.hidden_subscriber_count else f"{ch.subscriber_count:,}"
        self._lbl_summary.configure(
            text=(
                f"频道：{ch.title}　·　订阅人数：{sub_text}　·　"
                f"总视频数：{ch.video_count:,}　·　总观看次数：{ch.view_count:,}　·　"
                f"{source_text}{age_text}"
            )
        )
        has_any_playlist_videos = any(playlist_video_map.values())

        if not playlists or not has_any_playlist_videos:
            # 频道没有播放列表（或播放列表都是空的）→ 不支持系列分组，
            # 直接展示一个扁平宫格，全部视频按播放量从高到低排序。
            all_sorted = sorted(all_videos, key=lambda v: v.view_count, reverse=True)
            self._lbl_status.configure(
                text=f"该频道未使用播放列表分系列 · 按播放量排序展示全部 {len(all_sorted)} 个视频"
            )
            if all_sorted:
                self._render_section(f"📁 全部视频（按播放量排序，{len(all_sorted)}）", all_sorted)
            else:
                ttk.Label(self._grid_host, text="没有找到任何视频").pack(padx=8, pady=8)
            bind_mousewheel_deep(self._grid_host, self._on_mousewheel)
            self.after_idle(self._sync_scroll_region)
            return

        total_shown = sum(len(v) for v in playlist_video_map.values()) + len(unclassified)
        self._lbl_status.configure(
            text=f"共 {len(playlists)} 个系列（播放列表）· 展示 {total_shown} 个视频，每个系列内按播放量排序"
        )

        for p in playlists:
            vids = playlist_video_map.get(p.id) or []
            if not vids:
                continue
            self._render_section(f"📁 {p.title}（{len(vids)}）", vids)
        if unclassified:
            self._render_section(f"📁 未分类（{len(unclassified)}）", unclassified)

        bind_mousewheel_deep(self._grid_host, self._on_mousewheel)
        self.after_idle(self._sync_scroll_region)

    def _render_section(self, title: str, videos: list[VideoInfo]) -> None:
        # 独立行块（LabelFrame）+ 彩色标题条：确保每个系列在视觉上明显分组，
        # 而不是所有宫格挤成一整块。
        colors = self._grid_theme
        section = ttk.LabelFrame(self._grid_host, padding=(0, 0, 0, 6))
        section.pack(fill=tk.X, padx=4, pady=(0, 12), anchor=tk.W)

        header = tk.Label(
            section,
            text=title,
            bg=colors.border_hover,
            fg="#ffffff",
            font=("", 9, "bold"),
            anchor=tk.W,
            padx=8,
            pady=4,
        )
        header.pack(fill=tk.X)

        grid_frame = ttk.Frame(section, padding=(6, 6, 6, 0))
        grid_frame.pack(fill=tk.X)

        cols = compute_cols(self._canvas.winfo_width())
        for idx, v in enumerate(videos):
            row, col = divmod(idx, cols)
            thumb_path = download_thumbnail(v.thumbnail_url)
            img = load_local_image(thumb_path, target_w=CELL_W - 4, target_h=CELL_H - 4)
            subtitle = f"👁 {self._fmt_compact(v.view_count)}"
            cell = build_grid_cell(
                grid_frame,
                row=row,
                col=col,
                title=v.title,
                subtitle=subtitle,
                image=img,
                theme=self._grid_theme,
                photo_refs=self._photo_refs,
                on_click=lambda vid=v.id: self._on_select(vid),
                on_double_click=lambda vid=v.id: self._on_play(vid),
                highlighted=bool(cached_own_insight(v.id)),
            )
            self._cells[v.id] = cell
            self._videos_by_id[v.id] = v

    @staticmethod
    def _fmt_compact(n: float) -> str:
        n = float(n)
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(int(n))

    def _on_select(self, video_id: str) -> None:
        video = self._videos_by_id.get(video_id)
        if not video:
            return
        self._selected_id = video_id
        self._preview.show_video(video)
        self._log(f"[我的数据] 预览：{video.title}")

    def _on_play(self, video_id: str) -> None:
        video = self._videos_by_id.get(video_id)
        if not video:
            return
        self._on_select(video_id)
        open_in_browser(video.watch_url)
        self._log(f"[我的数据] 在浏览器播放：{video.title}")

    def _on_video_analyzed(self, video: VideoInfo) -> None:
        """LLM 优劣分析成功完成后，把对应宫格边框标记为黄色（若当前仍在视图中）。"""
        cell = self._cells.get(video.id)
        if cell:
            mark_cell_analyzed(cell)

    def apply_theme(self, theme: UiTheme) -> None:
        self._grid_theme = grid_theme(theme)
        self._preview.apply_theme(theme)
        # 网格宫格用固定色板绘制，主题切换后需下一次刷新才会重绘（与素材库 Tab 一致）


__all__ = ["MyChannelTab"]
