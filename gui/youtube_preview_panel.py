"""右侧「预览区」：上半区展示封面（后续可扩展成视频播放），下半区展示元数据；
点击「LLM 分析」后下半区会切换成分析结果，可再切回元数据。"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from tkinter import ttk
import tkinter as tk
from typing import Callable

from PIL import Image, ImageTk

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gui.tk_thread import bind_ui_root, schedule_on_main  # noqa: E402
from gui.ui_theme import LIGHT, UiTheme, grid_theme  # noqa: E402
from gui.youtube_api import ChannelInfo, VideoInfo  # noqa: E402
from gui.youtube_cache import download_thumbnail  # noqa: E402
from gui.youtube_grid_common import load_local_image  # noqa: E402

_THUMB_W, _THUMB_H = 320, 180


def open_in_browser(url: str) -> None:
    try:
        from scripts.video_upload.youtube_upload import open_browser_url

        open_browser_url(url)
    except Exception:
        import webbrowser

        webbrowser.open(url, new=1)


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _fmt_date(iso: str) -> str:
    if not iso:
        return "-"
    return iso[:10]


class YoutubePreviewPanel(ttk.Frame):
    """通用预览区：可展示视频或频道详情；可选内嵌 LLM 分析。

    布局固定为上下两段：上半区是封面缩略图（预留未来扩展成内嵌视频播放），
    下半区是一块可切换的文本内容区——默认显示元数据，点击「LLM 分析」按钮后
    立即切换成分析结果（分析完成后自动刷新成最终文本），可用「查看元数据」
    按钮切回去。
    """

    def __init__(
        self,
        parent: tk.Widget,
        *,
        enable_analysis: bool = False,
        analysis_button_label: str = "LLM 分析优点",
        analysis_heading: str = "LLM 爆款要素分析：",
        analyze_fn: Callable[..., str] | None = None,
        get_cached_fn: Callable[[str], str | None] | None = None,
        log_fn: Callable[[str], None] | None = None,
        on_analyzed: Callable[[VideoInfo], None] | None = None,
    ) -> None:
        super().__init__(parent, padding=8)
        self._log = log_fn or (lambda _m: None)
        self._enable_analysis = enable_analysis
        self._analysis_button_label = analysis_button_label
        self._analysis_heading = analysis_heading
        self._meta_heading = "视频信息："
        self._on_analyzed = on_analyzed
        if enable_analysis:
            from gui.video_insight import analyze_video_success, cached_insight

            self._analyze_fn = analyze_fn or analyze_video_success
            self._get_cached_fn = get_cached_fn or cached_insight
        else:
            self._analyze_fn = analyze_fn
            self._get_cached_fn = get_cached_fn
        self._photo_ref: ImageTk.PhotoImage | None = None
        self._current_video: VideoInfo | None = None
        self._current_channel: ChannelInfo | None = None
        self._current_url: str = ""
        self._grid_theme = grid_theme(LIGHT)
        self._analyzing = False
        # "meta"：下半区显示元数据；"analysis"：下半区显示 LLM 分析结果。
        self._content_mode = "meta"
        self._cached_analysis_text: str | None = None
        self._build_ui()
        bind_ui_root(self)
        self.show_empty()

    def _build_ui(self) -> None:
        # 注意：tk.Label 在未显示图片时 width/height 是"字符/行数"单位而非像素，
        # 必须用固定像素尺寸的 Frame 包裹 + pack_propagate(False) 才能锁定实际像素高度，
        # 否则空标签会被撑到几千像素高，挤爆整个预览区布局。
        # === 上半区：封面（后续可扩展成内嵌视频播放）===
        self._thumb_frame = tk.Frame(self, width=_THUMB_W, height=_THUMB_H, bg="#2a2a2a")
        self._thumb_frame.pack(fill=tk.X)
        self._thumb_frame.pack_propagate(False)
        self._thumb_lbl = tk.Label(self._thumb_frame, bg="#2a2a2a")
        self._thumb_lbl.pack(fill=tk.BOTH, expand=True)

        self._title_lbl = ttk.Label(
            self, text="", wraplength=_THUMB_W, font=("", 10, "bold"), justify=tk.LEFT
        )
        self._title_lbl.pack(fill=tk.X, pady=(8, 6), anchor=tk.W)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill=tk.X, pady=(0, 6))
        self._btn_play = ttk.Button(btn_row, text="▶ 在浏览器中打开", command=self._on_play_clicked)
        self._btn_play.pack(side=tk.LEFT)

        if self._enable_analysis:
            self._btn_analyze = ttk.Button(
                btn_row, text=f"🔍 {self._analysis_button_label}", command=self._on_analyze_clicked
            )
            self._btn_analyze.pack(side=tk.LEFT, padx=(8, 0))
            self._btn_reanalyze = ttk.Button(
                btn_row, text="重新分析", command=lambda: self._on_analyze_clicked(force=True)
            )
            self._btn_reanalyze.pack(side=tk.LEFT, padx=(8, 0))
            self._btn_toggle_view = ttk.Button(
                btn_row, text="查看分析结果", command=self._toggle_content_view
            )
            self._btn_toggle_view.pack(side=tk.LEFT, padx=(8, 0))

        # === 下半区：元数据 / LLM 分析结果（二选一，可切换）===
        self._content_heading = ttk.Label(self, text=self._meta_heading, foreground="gray")
        self._content_heading.pack(fill=tk.X, anchor=tk.W, pady=(4, 2))
        text_frame = ttk.Frame(self)
        text_frame.pack(fill=tk.BOTH, expand=True)
        self._content_text = tk.Text(text_frame, wrap=tk.WORD, state=tk.DISABLED, font=("", 9))
        yscroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self._content_text.yview)
        self._content_text.configure(yscrollcommand=yscroll.set)
        self._content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _format_video_meta(self, video: VideoInfo) -> str:
        age_label = video.relative_age_label()
        published_text = _fmt_date(video.published_at) + (f"（{age_label}）" if age_label else "")
        description = (video.description or "").strip() or "（无描述）"
        return (
            f"频道：{video.channel_title}\n"
            f"发布时间：{published_text}\n"
            f"👁 观看数：{_fmt_int(video.view_count)}　👍 点赞数：{_fmt_int(video.like_count)}　"
            f"💬 评论数：{_fmt_int(video.comment_count)}\n"
            f"📈 日均播放：{_fmt_int(int(video.views_per_day()))}/天\n"
            f"\n描述：\n{description}"
        )

    def _format_channel_meta(self, channel: ChannelInfo) -> str:
        sub_text = "已隐藏" if channel.hidden_subscriber_count else _fmt_int(channel.subscriber_count)
        return (
            f"订阅人数：{sub_text}\n"
            f"总观看次数：{_fmt_int(channel.view_count)}\n"
            f"注册时间：{_fmt_date(channel.published_at)}\n"
            f"视频总数：{_fmt_int(channel.video_count)}"
        )

    def show_empty(self) -> None:
        self._current_video = None
        self._current_channel = None
        self._current_url = ""
        self._content_mode = "meta"
        self._cached_analysis_text = None
        self._thumb_lbl.configure(image="", text="点击左侧宫格预览", fg="#999999")
        self._photo_ref = None
        self._title_lbl.configure(text="")
        self._content_heading.configure(text=self._meta_heading)
        self._set_content_text("")
        self._btn_play.configure(state=tk.DISABLED)
        if self._enable_analysis:
            self._btn_analyze.configure(state=tk.DISABLED)
            self._btn_reanalyze.configure(state=tk.DISABLED)
            self._btn_toggle_view.configure(state=tk.DISABLED, text="查看分析结果")

    def show_video(self, video: VideoInfo) -> None:
        self._current_video = video
        self._current_channel = None
        self._current_url = video.watch_url
        self._content_mode = "meta"
        self._title_lbl.configure(text=video.title)
        self._content_heading.configure(text=self._meta_heading)
        self._set_content_text(self._format_video_meta(video))
        self._btn_play.configure(state=tk.NORMAL, text="▶ 在浏览器中播放")
        if self._enable_analysis:
            self._btn_analyze.configure(state=tk.NORMAL)
            self._btn_reanalyze.configure(state=tk.NORMAL)
            cached = self._get_cached_fn(video.id) if self._get_cached_fn else None
            self._cached_analysis_text = cached
            self._btn_toggle_view.configure(
                state=tk.NORMAL if cached else tk.DISABLED, text="查看分析结果"
            )
        self._thumb_lbl.configure(image="", text="加载封面…", fg="#999999")
        threading.Thread(target=self._load_thumb_bg, args=(video.thumbnail_url,), daemon=True).start()

    def show_channel(self, channel: ChannelInfo) -> None:
        self._current_video = None
        self._current_channel = channel
        self._current_url = channel.channel_url
        self._content_mode = "meta"
        self._cached_analysis_text = None
        self._title_lbl.configure(text=f"📺 {channel.title}")
        self._content_heading.configure(text="频道信息：")
        self._set_content_text(self._format_channel_meta(channel))
        self._btn_play.configure(state=tk.NORMAL, text="在浏览器中打开频道")
        if self._enable_analysis:
            self._btn_analyze.configure(state=tk.DISABLED)
            self._btn_reanalyze.configure(state=tk.DISABLED)
            self._btn_toggle_view.configure(state=tk.DISABLED, text="查看分析结果")
        self._thumb_lbl.configure(image="", text="加载头像…", fg="#999999")
        threading.Thread(
            target=self._load_thumb_bg, args=(channel.thumbnail_url,), daemon=True
        ).start()

    def _load_thumb_bg(self, url: str) -> None:
        path = download_thumbnail(url)
        img = load_local_image(path, target_w=_THUMB_W, target_h=_THUMB_H)
        schedule_on_main(self, self._apply_thumb, img)

    def _apply_thumb(self, img: Image.Image | None) -> None:
        if img is None:
            self._thumb_lbl.configure(image="", text="无预览", fg="#999999")
            self._photo_ref = None
            return
        photo = ImageTk.PhotoImage(img)
        self._photo_ref = photo
        self._thumb_lbl.configure(image=photo, text="")

    def set_on_analyzed(self, on_analyzed: Callable[[VideoInfo], None] | None) -> None:
        """设置/替换「分析成功后」回调（例如挂载方需要等宿主 Tab 建好才能绑定）。"""
        self._on_analyzed = on_analyzed

    def _on_play_clicked(self) -> None:
        if not self._current_url:
            return
        open_in_browser(self._current_url)
        self._log(f"预览区：在浏览器打开 {self._current_url}")

    def _set_content_text(self, text: str) -> None:
        self._content_text.configure(state=tk.NORMAL)
        self._content_text.delete("1.0", tk.END)
        self._content_text.insert(tk.END, text)
        self._content_text.configure(state=tk.DISABLED)

    def _toggle_content_view(self) -> None:
        if self._current_video is None:
            return
        if self._content_mode == "meta":
            if not self._cached_analysis_text:
                return
            self._content_mode = "analysis"
            self._content_heading.configure(text=self._analysis_heading)
            self._set_content_text(self._cached_analysis_text)
            self._btn_toggle_view.configure(text="查看元数据")
        else:
            self._content_mode = "meta"
            self._content_heading.configure(text=self._meta_heading)
            self._set_content_text(self._format_video_meta(self._current_video))
            self._btn_toggle_view.configure(text="查看分析结果")

    def _on_analyze_clicked(self, *, force: bool = False) -> None:
        video = self._current_video
        if not video or self._analyzing:
            return
        self._analyzing = True
        self._btn_analyze.configure(state=tk.DISABLED)
        self._btn_reanalyze.configure(state=tk.DISABLED)
        self._btn_toggle_view.configure(state=tk.DISABLED)
        # 点击即刻把下半区切到分析结果（先显示占位文案），符合「点击 LLM
        # 分析后元数据刷新成分析结果」的预期，而不是分析完才切换。
        self._content_mode = "analysis"
        self._content_heading.configure(text=self._analysis_heading)
        self._set_content_text("分析中，请稍候…（首次调用 LLM 可能需要几秒到十几秒）")

        def worker() -> None:
            try:
                text = self._analyze_fn(video, force=force, log_fn=self._log)
            except Exception as exc:  # noqa: BLE001
                text = f"⚠️ 分析失败：{exc}"
            schedule_on_main(self, self._on_analysis_done, video, text)

        threading.Thread(target=worker, daemon=True).start()

    def _on_analysis_done(self, video: VideoInfo, text: str) -> None:
        self._analyzing = False
        if self._current_video is video:
            self._cached_analysis_text = text
            if self._content_mode == "analysis":
                self._set_content_text(text)
            self._btn_analyze.configure(state=tk.NORMAL)
            self._btn_reanalyze.configure(state=tk.NORMAL)
            self._btn_toggle_view.configure(
                state=tk.NORMAL,
                text="查看元数据" if self._content_mode == "analysis" else "查看分析结果",
            )
        self._log(f"LLM 分析完成：{video.title[:40]}")

        # 失败信息不会写入磁盘缓存，因此这里能查到缓存即代表本次是成功的分析结果。
        if self._on_analyzed and self._get_cached_fn and self._get_cached_fn(video.id):
            self._on_analyzed(video)

    def apply_theme(self, theme: UiTheme) -> None:
        self._grid_theme = grid_theme(theme)
        self._content_text.configure(
            bg=theme.text_bg,
            fg=theme.fg,
            insertbackground=theme.fg,
            selectbackground=theme.select_bg,
            selectforeground=theme.select_fg,
        )


__all__ = ["YoutubePreviewPanel", "open_in_browser"]
