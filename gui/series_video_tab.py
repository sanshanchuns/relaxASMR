"""「系列视频」Tab：种子图 → 同系列图片 → 每图一段 5s loop 视频。

左栏三列（横向 PanedWindow）：

    ┌── 种子图 ──┬──── 系列图 ────┬──── 对应视频 ────┐
    │ 导入 / 文生图│ 系列图纵向列表  │ 与左侧逐行对齐   │
    │ + 待选候选  │               │                 │
    └────────────┴───────────────┴─────────────────┘

种子图有两条入口：外部文件导入，或用 prompt 文生出多张候选再挑一张定稿。
第二、三列滚动联动，所以「第 N 张系列图」和「它的视频」永远在同一行。

耗时操作（文生图、图生图、图生视频）全部放后台线程，通过 ``schedule_on_main``
回主线程更新界面；``_busy`` 保证同时只跑一个批量任务，``_cancel`` 用于中途停止。
出图 / 出视频前都会走 ``instructions/`` 下规范的机器校验，不通过不会调用模型。
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from gui.agy_quota_panel import AgyQuotaPanel
from gui.tk_thread import bind_ui_root, schedule_on_main
from gui.ui_theme import LIGHT, UiTheme, grid_theme, paint_widget_bg
from gui.video_quota_panel import VideoQuotaPanel
from scripts.config.paths import base_url, series_dir, series_video_dir
from scripts.series_video import video_gen
from scripts.series_video.image_gen import (
    classify_batch_seed,
    generate_seed_candidates,
    generate_series_images,
    regenerate_image,
)
from scripts.series_video.acceptance import accept_video
from scripts.series_video.prompt_rules import validate_video_prompt
from scripts.series_video.review import (
    format_seed_analysis,
    format_series_image_review,
    gate_still_for_video,
)
from scripts.series_video.series import default_series_id, list_series, series_label
from scripts.series_video.store import (
    BatchMeta,
    SeedCandidate,
    SeriesItem,
    adopt_orphan_images,
    adopt_seed_candidate,
    clear_batch_seed,
    create_batch,
    create_empty_batch,
    delete_item_video,
    series_video_name,
    set_batch_seed,
    latest_batch,
    list_batches,
)
from scripts.series_video.video_prompt_gen import generate_video_prompt_for_item

CELL_W = 208
CELL_H = 117
CELL_PAD = 5
LABEL_H = 18
SEED_W = 260
SEED_H = 146
CAND_W = SEED_W - 16
CAND_H = 90
# 关键字 / 限定词输入框宽度
KEYWORD_ENTRY_WIDTH = 16
CAND_COLS = 1
# 系列视频来源：下拉显示名 → video_gen provider id
VIDEO_SOURCE_CHOICES: tuple[tuple[str, str], ...] = (
    ("jimeng_web", "jimeng_web"),
    ("elevenLabs_web", "elevenlabs_web"),
)
DEFAULT_VIDEO_SOURCE = "jimeng_web"
# 宫格右上角关闭钮约为默认尺寸的 25%
_CLOSE_BTN_FONT = ("", 6)
_CLOSE_BTN_WIDTH = 1
_CLOSE_BTN_HEIGHT = 1

_IMAGE_FILETYPES = [
    ("图片", "*.png *.jpg *.jpeg *.webp"),
    ("所有文件", "*.*"),
]


def _corner_close_button(parent: tk.Widget, *, command: Callable[[], None]) -> tk.Button:
    return tk.Button(
        parent,
        text="✕",
        font=_CLOSE_BTN_FONT,
        width=_CLOSE_BTN_WIDTH,
        height=_CLOSE_BTN_HEIGHT,
        relief=tk.FLAT,
        bd=0,
        padx=0,
        pady=0,
        command=command,
    )


def _load_thumb(path: Path, *, w: int, h: int) -> Image.Image | None:
    try:
        img = Image.open(path).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    img.thumbnail((w, h), Image.Resampling.LANCZOS)
    return img


def _video_thumb(path: Path, *, w: int, h: int) -> Image.Image | None:
    try:
        import cv2

        if not path.is_file() or path.stat().st_size < 1024:
            return None
        cap = cv2.VideoCapture(str(path))
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img.thumbnail((w, h), Image.Resampling.LANCZOS)
        return img
    except Exception:  # noqa: BLE001
        return None


#: 评审结论 → 单元格标题上的一个字符。评审是软闸门，没跑成（skip）不打标记。
_VERDICT_MARK = {"pass": " ✓", "revise": " ⚠", "reject": " ✗"}


def _review_mark(review: dict | None) -> str:
    return _VERDICT_MARK.get(str((review or {}).get("verdict") or ""), "")


def _acceptance_tag(item: SeriesItem) -> str:
    """视频格的副标题：provider + 客观运动量 + 评审结论。"""
    parts = [item.video_provider or "mp4"]
    if item.video_motion:
        parts.append(f"运动 {item.video_motion:g}")
    mark = _review_mark(item.video_review).strip()
    if mark:
        parts.append(mark)
    return " · ".join(parts)


class _ScrollColumn:
    """一列可纵向滚动的宫格；多个实例可共用同一个滚动位置。"""

    def __init__(self, parent: tk.Widget, title: str) -> None:
        self.frame = ttk.LabelFrame(parent, text=title, padding=6)
        self.canvas = tk.Canvas(self.frame, highlightthickness=0, bd=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # tk.Frame 才能在宫格间隙接收滚轮事件（ttk.Frame 空白区不响应）
        self.host = tk.Frame(self.canvas, bd=0, highlightthickness=0)
        self.window = self.canvas.create_window((0, 0), window=self.host, anchor=tk.NW)
        self.host.bind("<Configure>", lambda _e: self.sync_scrollregion())
        self.canvas.bind(
            "<Configure>",
            lambda e: (self.canvas.itemconfigure(self.window, width=e.width), self.sync_scrollregion()),
        )

    def bind_mousewheel(self, handler) -> None:
        """绑定列内所有空白/间隙区域的滚轮，避免只有宫格上才能滚。"""
        seqs = ("<MouseWheel>", "<Button-4>", "<Button-5>")
        for widget in (self.frame, self.canvas, self.host):
            for seq in seqs:
                widget.bind(seq, handler, add="+")

    def sync_scrollregion(self) -> None:
        self.canvas.update_idletasks()
        w = max(self.host.winfo_reqwidth(), self.canvas.winfo_width(), 1)
        h = max(self.host.winfo_reqheight(), 1)
        self.canvas.configure(scrollregion=(0, 0, w, h))

    def clear(self) -> None:
        for child in self.host.winfo_children():
            child.destroy()


class SeriesVideoTab(ttk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        *,
        log_fn: Callable[[str], None] | None = None,
        on_preview_image: Callable[..., None] | None = None,
        on_preview_series: Callable[..., None] | None = None,
        on_preview_video: Callable[..., None] | None = None,
        on_preview_empty: Callable[[str], None] | None = None,
        on_stop_playback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent, padding=8)
        self._log = log_fn or (lambda _m: None)
        self._on_preview_image = on_preview_image or (lambda *_a, **_k: None)
        self._on_preview_series = on_preview_series or (lambda *_a, **_k: None)
        self._on_preview_video = on_preview_video or (lambda *_a, **_k: None)
        self._on_preview_empty = on_preview_empty or (lambda _m: None)
        self._on_stop_playback = on_stop_playback or (lambda: None)
        self._meta: BatchMeta | None = None
        self._ui_theme = LIGHT
        self._grid_theme = grid_theme(LIGHT)
        self._muted_labels: list[ttk.Label] = []
        self._photo_refs: list[ImageTk.PhotoImage] = []
        self._img_cells: dict[str, dict] = {}
        self._vid_cells: dict[str, dict] = {}
        self._seed_photo: ImageTk.PhotoImage | None = None
        self._cand_photos: list[ImageTk.PhotoImage] = []
        self._cand_cells: dict[str, dict] = {}
        self._preview_cand_name: str | None = None
        self._selected_seed = False
        self._selected_image_key: str | None = None
        self._selected_video_key: str | None = None
        self._video_prompt_busy: set[str] = set()
        self._busy = False
        self._cancel = threading.Event()
        self._loaded_once = False
        self._seed_analysis_busy = False
        self._provider_hint_var = tk.StringVar(value="")
        self._build_ui()
        bind_ui_root(self)

    # ============================================================== UI
    def _build_ui(self) -> None:
        self._build_toolbar()

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self._body_pane = body
        self._body_pane_equalize_attempts = 0

        # --- 第一列：种子图（导入 / 文生候选）---
        self.col_seed = ttk.LabelFrame(body, text="① 种子图", padding=8)
        body.add(self.col_seed, weight=1)
        self._build_seed_column()

        # --- 第二列：系列图 ---
        self.col_images = _ScrollColumn(body, "② 系列图")
        body.add(self.col_images.frame, weight=1)

        # --- 第三列：对应视频（滚动条贴本列右侧，与系列图联动）---
        videos_host = ttk.Frame(body)
        body.add(videos_host, weight=1)

        self.col_videos = _ScrollColumn(videos_host, "③ 对应视频（5s loop）")
        self._shared_scroll = ttk.Scrollbar(
            videos_host, orient=tk.VERTICAL, command=self._yview_both
        )
        self._shared_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.col_videos.frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.col_images.canvas.configure(yscrollcommand=self._shared_scroll.set)
        for col in (self.col_images, self.col_videos):
            col.bind_mousewheel(self._on_mousewheel)
            col.canvas.configure(bg=self._ui_theme.canvas_bg)
            col.host.configure(bg=self._ui_theme.canvas_bg)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            videos_host.bind(seq, self._on_mousewheel, add="+")
        self._videos_host = videos_host

        body.bind("<Map>", self._equalize_body_pane_once, add="+")
        self.after_idle(self._equalize_body_pane_once)

    def _build_seed_column(self) -> None:
        """第一列：种子图预览 + 待选候选宫格（操作控件在顶部操作区）。"""
        self.seed_frame = tk.Frame(self.col_seed, bd=0)
        self.seed_frame.pack(pady=(0, 8))
        self.seed_canvas = tk.Canvas(
            self.seed_frame,
            width=SEED_W,
            height=SEED_H,
            highlightthickness=1,
            bd=0,
            bg=self._ui_theme.canvas_bg,
            highlightbackground=self._grid_theme.border_default,
        )
        self.seed_canvas.pack()
        self.seed_canvas.bind("<Button-1>", lambda _e: self._preview_seed_or_candidate())
        self.btn_clear_seed = _corner_close_button(self.seed_frame, command=self._clear_seed)
        self.lbl_seed_info = ttk.Label(
            self.col_seed,
            text="未选择种子图",
            wraplength=SEED_W,
            foreground=self._grid_theme.fg_muted,
        )
        self.lbl_seed_info.pack(anchor=tk.W)
        self._muted_labels.append(self.lbl_seed_info)

        ttk.Separator(self.col_seed, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        ttk.Label(self.col_seed, text="待选种子图（单击预览 · 双击定稿）").pack(anchor=tk.W)
        cand_wrap = ttk.Frame(self.col_seed)
        cand_wrap.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.cand_canvas = tk.Canvas(
            cand_wrap,
            highlightthickness=0,
            bd=0,
            height=220,
            bg=self._ui_theme.canvas_bg,
        )
        self.cand_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.cand_host = tk.Frame(self.cand_canvas, bg=self._ui_theme.canvas_bg)
        self._cand_window = self.cand_canvas.create_window(
            (0, 0), window=self.cand_host, anchor=tk.NW
        )
        cand_sb = ttk.Scrollbar(
            cand_wrap, orient=tk.VERTICAL, command=self.cand_canvas.yview
        )
        cand_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.cand_canvas.configure(yscrollcommand=cand_sb.set)
        self.cand_host.bind(
            "<Configure>",
            lambda _e: self.cand_canvas.configure(
                scrollregion=self.cand_canvas.bbox("all")
            ),
        )
        self.cand_host.grid_columnconfigure(0, weight=1)
        self.cand_canvas.bind(
            "<Configure>",
            lambda e: self.cand_canvas.itemconfigure(self._cand_window, width=e.width),
        )
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.cand_canvas.bind(seq, self._on_cand_mousewheel, add="+")
            self.cand_host.bind(seq, self._on_cand_mousewheel, add="+")

        lbl_series_hint = ttk.Label(
            self.col_seed,
            text=(
                "主题：雨 + 打击物 + ASMR 感\n"
                "出图：时间 + 主体 + 场景 + 风格\n"
                "出视频：6 步公式 · 480p/5s loop"
            ),
            wraplength=SEED_W,
            foreground=self._grid_theme.fg_muted,
            justify=tk.LEFT,
        )
        lbl_series_hint.pack(anchor=tk.W, pady=(6, 0))
        self._muted_labels.append(lbl_series_hint)

    def _equalize_body_pane_once(self, _event=None) -> None:
        """三列默认等宽；用户之后可拖动 sash 手动调整。"""
        self.update_idletasks()
        w = self._body_pane.winfo_width()
        if w <= 1:
            if self._body_pane_equalize_attempts < 10:
                self._body_pane_equalize_attempts += 1
                self.after(80, self._equalize_body_pane_once)
            return
        third = max(w // 3, 100)
        try:
            self._body_pane.sashpos(0, third)
            self._body_pane.sashpos(1, 2 * third)
        except tk.TclError:
            pass

    def _build_toolbar(self) -> None:
        # 顶部：额度左右并排 + 操作区单独一行
        top = ttk.Frame(self)
        top.pack(fill=tk.X, pady=(0, 6))
        top.columnconfigure(0, weight=1, uniform="quota")
        top.columnconfigure(1, weight=1, uniform="quota")
        top.rowconfigure(0, weight=0)
        top.rowconfigure(1, weight=0)

        row_img_quota = ttk.LabelFrame(top, text="生图模型额度")
        row_img_quota.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=(0, 4))
        self.agy_panel = AgyQuotaPanel(row_img_quota, log_fn=self._log)
        self.agy_panel.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        row_vid_quota = ttk.LabelFrame(top, text="生视频模型额度")
        row_vid_quota.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=(0, 4))
        self.video_quota_panel = VideoQuotaPanel(row_vid_quota, log_fn=self._log)
        self.video_quota_panel.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        row_ops = ttk.LabelFrame(top, text="操作区")
        row_ops.grid(row=1, column=0, columnspan=2, sticky="ew")
        ops = ttk.Frame(row_ops)
        ops.pack(fill=tk.X, padx=4, pady=4)

        # 第一行：批次（种子 / 系列图 / 视频共用）
        row_batch = ttk.Frame(ops)
        row_batch.pack(fill=tk.X)
        ttk.Label(row_batch, text="批次：").pack(side=tk.LEFT)
        self.batch_var = tk.StringVar()
        self.cmb_batch = ttk.Combobox(
            row_batch, textvariable=self.batch_var, width=18, state="readonly"
        )
        self.cmb_batch.pack(side=tk.LEFT)
        self.cmb_batch.bind("<<ComboboxSelected>>", self._on_batch_selected)

        # 子系列：整批的调子，种子图定稿后由 batch.json 锁定，这里只在出候选时选
        ttk.Label(row_batch, text="  子系列：").pack(side=tk.LEFT)
        self._series_labels = {s.label: s.id for s in list_series()}
        self.series_var = tk.StringVar()
        self.cmb_series = ttk.Combobox(
            row_batch,
            textvariable=self.series_var,
            width=12,
            state="readonly",
            values=list(self._series_labels),
        )
        self.cmb_series.pack(side=tk.LEFT)
        self.lbl_series_locked = ttk.Label(row_batch, text="")
        self.lbl_series_locked.pack(side=tk.LEFT, padx=(6, 0))

        # 第二行：种子图 | 灵感词 → 张数 → 生成种子图 → 选择种子图
        row_seed = ttk.Frame(ops)
        row_seed.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row_seed, text="种子图 |").pack(side=tk.LEFT)
        ttk.Label(row_seed, text="灵感词").pack(side=tk.LEFT, padx=(4, 2))
        self.seed_idea_var = tk.StringVar()
        self._seed_idea_entry = ttk.Entry(
            row_seed, textvariable=self.seed_idea_var, width=KEYWORD_ENTRY_WIDTH
        )
        self._seed_idea_entry.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(row_seed, text="张数").pack(side=tk.LEFT)
        self.seed_count_var = tk.IntVar(value=3)
        ttk.Spinbox(
            row_seed, from_=1, to=12, width=3, textvariable=self.seed_count_var
        ).pack(side=tk.LEFT, padx=(4, 8))
        self.btn_gen_seeds = ttk.Button(
            row_seed, text="生成种子图", command=self._start_generate_seeds
        )
        self.btn_gen_seeds.pack(side=tk.LEFT)
        self.btn_pick_seed = ttk.Button(
            row_seed, text="选择种子图…", command=self._pick_seed
        )
        self.btn_pick_seed.pack(side=tk.LEFT, padx=(4, 0))

        row_img = ttk.Frame(ops)
        row_img.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row_img, text="系列图 |").pack(side=tk.LEFT)
        ttk.Label(row_img, text="限定词").pack(side=tk.LEFT, padx=(4, 2))
        self.series_constraints_var = tk.StringVar()
        self._series_constraints_entry = ttk.Entry(
            row_img, textvariable=self.series_constraints_var, width=KEYWORD_ENTRY_WIDTH
        )
        self._series_constraints_entry.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(row_img, text="张数").pack(side=tk.LEFT)
        self.count_var = tk.IntVar(value=3)
        ttk.Spinbox(row_img, from_=1, to=20, width=3, textvariable=self.count_var).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        self.btn_gen_images = ttk.Button(
            row_img, text="生成系列图", command=self._start_generate_images
        )
        self.btn_gen_images.pack(side=tk.LEFT, padx=(8, 0))

        row_vid = ttk.Frame(ops)
        row_vid.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row_vid, text="系列视频 |").pack(side=tk.LEFT)
        ttk.Label(row_vid, text="来源").pack(side=tk.LEFT, padx=(4, 4))
        self.provider_var = tk.StringVar()
        self.cmb_provider = ttk.Combobox(
            row_vid,
            textvariable=self.provider_var,
            width=16,
            state="readonly",
            values=[label for label, _ in VIDEO_SOURCE_CHOICES],
        )
        self.cmb_provider.pack(side=tk.LEFT)
        self.cmb_provider.bind(
            "<<ComboboxSelected>>", lambda _e: self._update_provider_hint()
        )
        self.btn_gen_videos = ttk.Button(
            row_vid, text="生成视频", command=self._start_generate_video_for_selection
        )
        self.btn_gen_videos.pack(side=tk.LEFT, padx=(8, 0))
        lbl_video_hint = ttk.Label(
            row_vid,
            text="（需先单击选中一张系列图）",
            foreground=self._grid_theme.fg_muted,
        )
        lbl_video_hint.pack(side=tk.LEFT, padx=(8, 0))
        self._muted_labels.append(lbl_video_hint)

        row_login = ttk.Frame(ops)
        row_login.pack(fill=tk.X, pady=(6, 0))
        self.btn_jimeng_login = ttk.Button(
            row_login, text="即梦登录", command=self._start_jimeng_login
        )
        self.btn_jimeng_login.pack(side=tk.LEFT)
        self.btn_el_web_login = ttk.Button(
            row_login, text="ElevenLabs 登录（网页）", command=self._start_el_web_login
        )
        self.btn_el_web_login.pack(side=tk.LEFT, padx=(8, 0))
        lbl_http_hint = ttk.Label(
            row_login,
            text="HTTP token：python -m elevenlabs_http login",
            foreground=self._grid_theme.fg_muted,
        )
        lbl_http_hint.pack(side=tk.LEFT, padx=(8, 0))
        self._muted_labels.append(lbl_http_hint)

        # 视频来源可用性（含 jimeng_web import）延到首次进入本 Tab 再查。

    # -------------------------------------------------------- 滚动联动
    def _yview_both(self, *args) -> None:
        self.col_images.canvas.yview(*args)
        self.col_videos.canvas.yview(*args)

    def _on_mousewheel(self, event) -> None:
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            delta = -1 * (event.delta // 120) if event.delta else 0
        if delta:
            self.col_images.canvas.yview_scroll(delta, "units")
            self.col_videos.canvas.yview_scroll(delta, "units")

    # ========================================================== provider
    def _provider_id_from_label(self, label: str) -> str:
        for display, pid in VIDEO_SOURCE_CHOICES:
            if display == label:
                return pid
        return ""

    def _reload_providers(self) -> None:
        labels = [label for label, _ in VIDEO_SOURCE_CHOICES]
        self.cmb_provider.configure(values=labels)
        if self.provider_var.get() not in labels:
            self.provider_var.set(DEFAULT_VIDEO_SOURCE)
        self._update_provider_hint()

    def _current_provider(self):
        pid = self._provider_id_from_label(self.provider_var.get())
        if not pid:
            return None
        try:
            return video_gen.get_provider(pid)
        except video_gen.VideoProviderError:
            return None

    def _update_provider_hint(self) -> None:
        p = self._current_provider()
        if p is None:
            self._provider_hint_var.set("未选择来源")
            return
        try:
            ok, reason = p.available()
        except Exception as exc:  # noqa: BLE001
            ok, reason = False, str(exc)
        mark = "可用" if ok else "不可用"
        # 可用时只显示简短标记；不可用时保留原因方便排查。
        self._provider_hint_var.set(mark if ok else f"{mark} · {reason}")

    def _start_jimeng_login(self) -> None:
        if self._busy:
            return

        def job() -> None:
            try:
                from scripts.config.paths import ensure_cli_path

                ensure_cli_path()
                from jimeng_web.client import JimengWebClient

                st = JimengWebClient().interactive_login(
                    log=lambda m: schedule_on_main(self, self._log, m)
                )
                schedule_on_main(
                    self,
                    self._log,
                    f"[即梦] 登录完成：{st.detail}",
                )
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._log, f"[即梦] 登录失败：{exc}")
            schedule_on_main(self, self._reload_providers)
            if hasattr(self, "video_quota_panel"):
                schedule_on_main(self, self.video_quota_panel.reload)

        self._run_bg(job)

    def _start_el_web_login(self) -> None:
        if self._busy:
            return

        def job() -> None:
            try:
                from scripts.config.paths import ensure_cli_path

                ensure_cli_path()
                from elevenlabs_web.client import ElevenLabsWebUiClient

                st = ElevenLabsWebUiClient().interactive_login(
                    log=lambda m: schedule_on_main(self, self._log, m)
                )
                schedule_on_main(
                    self,
                    self._log,
                    f"[ElevenLabs-Web] 登录完成：{st.detail}",
                )
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._log, f"[ElevenLabs-Web] 登录失败：{exc}")
            schedule_on_main(self, self._reload_providers)
            if hasattr(self, "video_quota_panel"):
                schedule_on_main(self, self.video_quota_panel.reload)

        self._run_bg(job)

    # ============================================================ 批次
    def on_tab_selected(self) -> None:
        first_time = not self._loaded_once
        self._reload_providers()
        self.refresh(force=first_time)
        if hasattr(self, "agy_panel"):
            self.agy_panel.reload()
        if hasattr(self, "video_quota_panel"):
            self.video_quota_panel.reload()
        self.after_idle(self.col_images.sync_scrollregion)
        self.after_idle(self.col_videos.sync_scrollregion)
        self.after_idle(self._equalize_body_pane_once)

    def refresh(self, *, force: bool = False) -> None:
        batches = list_batches()
        self.cmb_batch.configure(values=batches)
        if self._meta is None or force:
            meta = None
            if self.batch_var.get() in batches:
                meta = BatchMeta.load(self.batch_var.get())
            if meta is None:
                meta = latest_batch()
            self._set_meta(meta)
        self._loaded_once = True

    def _sync_series_widgets(self, meta: BatchMeta | None) -> None:
        """种子图一旦定稿，整批的子系列就锁死了，下拉框只用来显示。

        未锁定时不要动用户当前的选择 —— 切批次、任务结束都会走到这里，
        把它重置成默认值会把「我要做暴雨」这个意图悄悄改掉。
        """
        locked = bool(meta is not None and meta.has_seed)
        current = (meta.series_id if meta is not None else "") or ""
        if locked or not self.series_var.get():
            for label, sid in self._series_labels.items():
                if sid == (current or default_series_id()):
                    self.series_var.set(label)
                    break
        self.cmb_series.configure(state="disabled" if locked else "readonly")
        self.lbl_series_locked.configure(text="（已锁定）" if locked else "")

    def _set_meta(self, meta: BatchMeta | None) -> None:
        self._meta = meta
        if meta is None:
            self.batch_var.set("")
            self.seed_idea_var.set("")
            self.series_constraints_var.set("")
            self._sync_series_widgets(None)
            self._render_seed()
            self._render_candidates()
            self._render_rows()
            return
        adopt_orphan_images(meta)
        self.batch_var.set(meta.batch_id)
        if meta.seed_idea and not self.seed_idea_var.get().strip():
            self.seed_idea_var.set(meta.seed_idea)
        self.series_constraints_var.set(meta.series_constraints or "")
        self._sync_series_widgets(meta)
        self._render_seed()
        self._render_candidates()
        self._render_rows()

    def _on_batch_selected(self, _event=None) -> None:
        bid = self.batch_var.get()
        if not bid:
            return
        self._set_meta(BatchMeta.load(bid))
        self._log(f"[系列视频] 切换批次：{bid}")

    def _seed_dialog_initialdir(self) -> str:
        meta = self._meta
        if meta is not None:
            seed_dir = meta.dir / "seed_image"
            if seed_dir.is_dir():
                return str(seed_dir)
        root = series_dir()
        if root.is_dir():
            return str(root)
        try:
            bu = base_url()
            if bu.is_dir():
                return str(bu)
        except OSError:
            pass
        return str(Path.home())

    def _pick_seed(self) -> None:
        if self._busy:
            messagebox.showinfo("系列视频", "当前有任务在跑，请先等待或点「停止」。")
            return
        path = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="选择种子图片",
            initialdir=self._seed_dialog_initialdir(),
            filetypes=_IMAGE_FILETYPES,
        )
        if not path:
            return
        src = Path(path)
        meta = self._meta
        if meta is not None and meta.items:
            if not messagebox.askyesno(
                "选择种子图",
                f"当前批次 {meta.batch_id} 已有 {len(meta.items)} 张系列图。\n"
                "导入新种子图将新建批次，是否继续？",
            ):
                return
            meta = create_batch(src)
            self._log(f"[系列视频] 新建批次 {meta.batch_id}，种子图 {src.name}")
        elif meta is not None:
            set_batch_seed(meta, src)
            self._log(f"[系列视频] 已导入种子图到批次 {meta.batch_id}：{src.name}")
        else:
            meta = create_batch(src)
            self._log(f"[系列视频] 新建批次 {meta.batch_id}，种子图 {src.name}")
        self.cmb_batch.configure(values=list_batches())
        self._set_meta(meta)
        self._select_seed(preview=True)
        self._run_bg(
            lambda: classify_batch_seed(
                meta, log_fn=lambda m: schedule_on_main(self, self._log, m)
            )
        )

    def _ensure_prompt_batch(self, idea: str) -> BatchMeta:
        """复用尚未定稿的 prompt 批次；否则新建空批次。"""
        meta = self._meta
        if (
            meta is not None
            and not meta.has_seed
            and meta.seed_source == "prompt"
            and not meta.items
        ):
            if idea:
                meta.seed_idea = idea
                meta.save()
            return meta
        meta = create_empty_batch(idea=idea)
        self.cmb_batch.configure(values=list_batches())
        self._set_meta(meta)
        return meta

    # ============================================================ 渲染
    def _render_seed(self) -> None:
        self.seed_canvas.delete("all")
        self._seed_photo = None
        meta = self._meta
        if meta is None or not meta.has_seed:
            self.btn_clear_seed.place_forget()
            self.lbl_seed_info.configure(text="未选择种子图（可导入或从下方候选定稿）")
            self.seed_canvas.create_text(
                SEED_W // 2, SEED_H // 2, text="未选择", fill=self._grid_theme.fg_muted
            )
            return
        self.btn_clear_seed.place(relx=1.0, x=0, y=0, anchor=tk.NE)
        img = _load_thumb(meta.seed_path, w=SEED_W, h=SEED_H)
        if img is None:
            self.seed_canvas.create_text(
                SEED_W // 2,
                SEED_H // 2,
                text="无法加载",
                fill=self._grid_theme.fg_muted,
            )
        else:
            self._seed_photo = ImageTk.PhotoImage(img)
            self.seed_canvas.create_image(
                SEED_W // 2, SEED_H // 2, anchor=tk.CENTER, image=self._seed_photo
            )
        done = sum(1 for it in meta.items if it.video_name)
        src = "文生图定稿" if str(meta.seed_source).startswith("candidate:") else (
            "prompt 待选" if meta.seed_source == "prompt" else "外部导入"
        )
        self.lbl_seed_info.configure(
            text=(
                f"批次 {meta.batch_id} · {src}\n"
                f"子系列 {series_label(meta.series_id)}\n"
                f"系列图 {len(meta.items)} 张 · 已出视频 {done} 段\n"
                f"{meta.resolution} / {meta.aspect_ratio} / {meta.duration_sec}s"
            )
        )

    def _render_candidates(self) -> None:
        for child in self.cand_host.winfo_children():
            child.destroy()
        self._cand_photos.clear()
        self._cand_cells.clear()
        meta = self._meta
        if meta is None or not meta.seed_candidates:
            empty_lbl = ttk.Label(
                self.cand_host,
                text="还没有候选。填关键字后点「生成种子图」",
                foreground=self._grid_theme.fg_muted,
                wraplength=SEED_W - 8,
            )
            empty_lbl.grid(row=0, column=0, columnspan=CAND_COLS, padx=4, pady=4, sticky=tk.W)
            return

        adopted = ""
        if str(meta.seed_source).startswith("candidate:"):
            adopted = meta.seed_source.split(":", 1)[1]

        for i, cand in enumerate(meta.seed_candidates):
            is_adopted = cand.name == adopted
            outer = tk.Frame(
                self.cand_host,
                bd=1,
                relief=tk.SOLID,
                highlightthickness=2,
                highlightbackground=self._grid_theme.border_default,
                cursor="hand2",
                bg=self._grid_theme.cell_bg,
            )
            outer.grid(row=i, column=0, padx=3, pady=3, sticky=tk.EW)

            thumb = tk.Label(
                outer,
                bd=0,
                cursor="hand2",
                bg=self._grid_theme.cell_bg,
            )
            thumb.pack()
            path = cand.path(meta.batch_id)
            img = _load_thumb(path, w=CAND_W, h=CAND_H) if path.is_file() else None
            if img is not None:
                photo = ImageTk.PhotoImage(img)
                self._cand_photos.append(photo)
                thumb.configure(image=photo)
            else:
                thumb.configure(
                    text=cand.error[:12] or "失败",
                    width=14,
                    height=4,
                    fg="#c04040" if cand.error else self._grid_theme.fg_muted,
                )

            judged = series_label(cand.series_id) if cand.series_id else ""
            if not judged and cand.review:
                judged = "系列不符"
            cap = cand.name
            if is_adopted:
                cap += " ✓"
            if judged:
                cap += f" · {judged}"
            name_lbl = tk.Label(
                outer,
                text=cap,
                font=("", 7),
                fg=self._grid_theme.fg_default,
                bg=self._grid_theme.cell_bg,
                anchor=tk.W,
                wraplength=CAND_W + 8,
                justify=tk.LEFT,
                cursor="hand2",
            )
            name_lbl.pack(anchor=tk.W, padx=2)

            cell = {"outer": outer, "thumb": thumb, "name_lbl": name_lbl}
            self._cand_cells[cand.name] = cell
            self._bind_cand_cell(cell, cand)

        self._highlight_candidates()
        self.cand_host.update_idletasks()
        self.cand_canvas.configure(scrollregion=self.cand_canvas.bbox("all"))

    def _highlight_candidates(self) -> None:
        meta = self._meta
        adopted = ""
        if meta is not None and str(meta.seed_source).startswith("candidate:"):
            adopted = meta.seed_source.split(":", 1)[1]
        for name, cell in self._cand_cells.items():
            selected = name == adopted or name == self._preview_cand_name
            cell["outer"].configure(
                highlightbackground=(
                    self._grid_theme.border_selected
                    if selected
                    else self._grid_theme.border_default
                )
            )

    def _bind_cand_cell(self, cell: dict, cand: SeedCandidate) -> None:
        pending: dict[str, str | None] = {"id": None}

        def single(_e) -> None:
            if pending["id"]:
                cell["outer"].after_cancel(pending["id"])
            pending["id"] = cell["outer"].after(
                250, lambda c=cand: self._preview_candidate(c)
            )

        def double(_e) -> None:
            if pending["id"]:
                cell["outer"].after_cancel(pending["id"])
                pending["id"] = None
            self._adopt_candidate(cand)

        for w in (cell["outer"], cell["thumb"], cell["name_lbl"]):
            w.bind("<Button-1>", single)
            w.bind("<Double-Button-1>", double)
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                w.bind(seq, self._on_cand_mousewheel, add="+")

    def _preview_candidate(self, cand: SeedCandidate) -> None:
        if self._meta is None:
            return
        self._preview_cand_name = cand.name
        self._highlight_candidates()
        path = cand.path(self._meta.batch_id)
        if not path.is_file():
            self._on_preview_empty(cand.error or "候选图缺失")
            return
        analysis = format_seed_analysis(
            cand.review,
            series_id=cand.series_id or self._meta.series_id,
            seed_prompt=cand.prompt,
        )
        self._on_preview_image(
            path,
            title=f"候选 {cand.name} · {cand.summary}",
            prompt=analysis,
        )

    def _seed_needs_analysis(self) -> bool:
        if self._meta is None or not self._meta.has_seed:
            return False
        review = self._meta.seed_review
        if not review:
            return True
        return not (
            review.get("shot_scale")
            or review.get("composition")
            or review.get("rain_subjects")
        )

    def _seed_analysis_text(self) -> str:
        if self._meta is None:
            return ""
        return format_seed_analysis(
            self._meta.seed_review,
            series_id=self._meta.series_id,
            seed_prompt=self._meta.seed_prompt,
        )

    def _start_seed_analysis(self) -> None:
        if self._meta is None or self._seed_analysis_busy or self._busy:
            return
        meta = self._meta
        self._seed_analysis_busy = True
        self._on_preview_image(
            meta.seed_path,
            title=f"种子图 · {meta.batch_id}",
            prompt="正在 Gemini 分析…",
        )

        def job() -> None:
            try:
                classify_batch_seed(
                    meta, log_fn=lambda m: schedule_on_main(self, self._log, m)
                )
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._log, f"[种子图] Gemini 分析失败：{exc}")
            finally:
                def done() -> None:
                    self._seed_analysis_busy = False
                    self._sync_series_widgets(meta)
                    self._preview_seed()

                schedule_on_main(self, done)

        threading.Thread(target=job, daemon=True).start()

    def _adopt_candidate(self, cand: SeedCandidate) -> None:
        if self._busy:
            messagebox.showinfo("系列视频", "当前有任务在跑，请先等待或点「停止」。")
            return
        if self._meta is None:
            return
        path = cand.path(self._meta.batch_id)
        if not path.is_file():
            messagebox.showwarning("系列视频", cand.error or "这张候选图不存在，无法定稿。")
            return
        if cand.review and not cand.series_id:
            reasons = "；".join(cand.review.get("issues") or []) or "未给出理由"
            if not messagebox.askyesno(
                "系列判定不符",
                f"Gemini 认为这张图不属于任何一个子系列：\n{reasons}\n\n"
                "种子图定了整批的调子，建议重出。仍要定稿吗？",
            ):
                return
        try:
            adopt_seed_candidate(self._meta, cand)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("系列视频", f"定稿失败：{exc}")
            return
        self._log(
            f"[系列视频] 已将候选 {cand.name} 定为种子图"
            f"，本批锁定为「{series_label(self._meta.series_id)}」"
        )
        self._sync_series_widgets(self._meta)
        self._render_seed()
        self._render_candidates()
        self._preview_seed()

    def _render_rows(self) -> None:
        self._photo_refs.clear()
        self._img_cells.clear()
        self._vid_cells.clear()
        self.col_images.clear()
        self.col_videos.clear()

        meta = self._meta
        if meta is None or not meta.has_seed:
            ttk.Label(
                self.col_images.host,
                text="先导入种子图，或生成种子图候选后双击定稿",
            ).pack(padx=8, pady=8)
            self.after_idle(self._sync_columns)
            return
        if not meta.items:
            ttk.Label(
                self.col_images.host, text="还没有系列图，点工具栏「生成系列图」"
            ).pack(padx=8, pady=8)
            self.after_idle(self._sync_columns)
            return

        for item in sorted(meta.items, key=lambda it: it.index):
            self._build_image_cell(item)
            self._build_video_cell(item)
        self.after_idle(self._sync_columns)

    def _sync_columns(self) -> None:
        self.col_images.sync_scrollregion()
        self.col_videos.sync_scrollregion()

    def _make_cell(
        self, host: tk.Widget, *, caption: str, on_delete: Callable[[], None] | None = None
    ) -> dict:
        outer = tk.Frame(
            host,
            width=CELL_W + CELL_PAD,
            height=CELL_H + LABEL_H + CELL_PAD,
            cursor="hand2",
            bg=self._grid_theme.cell_bg,
        )
        outer.pack(padx=CELL_PAD, pady=CELL_PAD)
        outer.pack_propagate(False)

        border = tk.Frame(
            outer,
            bg=self._grid_theme.cell_bg,
            highlightthickness=2,
            highlightbackground=self._grid_theme.border_default,
            highlightcolor=self._grid_theme.border_hover,
        )
        border.pack(fill=tk.BOTH, expand=True)

        img_lbl = tk.Label(border, bd=0, relief=tk.FLAT, bg=self._grid_theme.cell_bg)
        img_lbl.pack(fill=tk.BOTH, expand=True, padx=1, pady=(1, 0))

        name_lbl = tk.Label(
            border,
            text=caption,
            font=("", 8),
            fg=self._grid_theme.fg_default,
            bg=self._grid_theme.cell_bg,
            anchor=tk.CENTER,
        )
        name_lbl.pack(fill=tk.X, pady=(0, 2))

        btn_del = None
        if on_delete is not None:
            btn_del = _corner_close_button(outer, command=on_delete)
            self._style_close_button(btn_del)
            btn_del.place(relx=1.0, x=-1, y=1, anchor=tk.NE)

        return {
            "outer": outer,
            "border": border,
            "img_lbl": img_lbl,
            "name_lbl": name_lbl,
            "btn_del": btn_del,
        }

    def _build_image_cell(self, item: SeriesItem) -> None:
        caption = f"{item.index:03d}{_review_mark(item.image_review)} · {item.summary or item.image_name}"
        cell = self._make_cell(
            self.col_images.host,
            caption=caption[:38],
            on_delete=lambda it=item: self._delete_item(it),
        )
        cell["item"] = item
        self._img_cells[item.image_name] = cell
        self._paint_image_cell(item)
        self._bind_cell(
            cell,
            on_click=lambda it=item: self._preview_item_image(it),
            on_double=lambda it=item: self._preview_item_image(it),
            menu_builder=lambda it=item: self._image_menu(it),
        )

    def _paint_image_cell(self, item: SeriesItem) -> None:
        cell = self._img_cells.get(item.image_name)
        if cell is None or self._meta is None:
            return
        lbl = cell["img_lbl"]
        path = item.image_path(self._meta.batch_id)
        if item.image_error and not path.is_file():
            lbl.configure(image="", text="生成失败", fg="#c04040")
            return
        thumb = _load_thumb(path, w=CELL_W, h=CELL_H)
        if thumb is None:
            lbl.configure(image="", text="图片缺失", fg=self._grid_theme.fg_muted)
        else:
            photo = ImageTk.PhotoImage(thumb)
            self._photo_refs.append(photo)
            lbl.configure(image=photo, text="")

    def _build_video_cell(self, item: SeriesItem) -> None:
        cell = self._make_cell(
            self.col_videos.host,
            caption=f"{item.index:03d}",
            on_delete=lambda it=item: self._delete_video(it),
        )
        cell["item"] = item
        self._vid_cells[item.image_name] = cell
        self._paint_video_cell(item)
        self._bind_cell(
            cell,
            on_click=lambda it=item: self._preview_item_video(it),
            on_double=lambda it=item: self._regenerate_video(it),
            menu_builder=lambda it=item: self._video_menu(it),
        )

    def _paint_video_cell(self, item: SeriesItem, *, status: str = "") -> None:
        cell = self._vid_cells.get(item.image_name)
        if cell is None:
            return
        lbl = cell["img_lbl"]
        name = cell["name_lbl"]
        if status:
            lbl.configure(image="", text=status, fg=self._grid_theme.fg_muted)
            name.configure(text=f"{item.index:03d}")
            return
        path = item.video_path(self._meta.batch_id) if self._meta else None
        if path is not None and path.is_file():
            thumb = _video_thumb(path, w=CELL_W, h=CELL_H)
            if thumb is not None:
                photo = ImageTk.PhotoImage(thumb)
                self._photo_refs.append(photo)
                lbl.configure(image=photo, text="")
            else:
                lbl.configure(image="", text="▶ 已生成", fg=self._grid_theme.fg_default)
            name.configure(text=f"{item.index:03d} · {_acceptance_tag(item)}")
        elif item.video_error:
            lbl.configure(image="", text="生成失败", fg="#c04040")
            name.configure(text=f"{item.index:03d}")
        else:
            lbl.configure(image="", text="未生成", fg=self._grid_theme.fg_muted)
            name.configure(text=f"{item.index:03d}")

    def _bind_cell(
        self,
        cell: dict,
        *,
        on_click: Callable[[], None],
        on_double: Callable[[], None],
        menu_builder: Callable[[], tk.Menu],
    ) -> None:
        pending: dict[str, str | None] = {"id": None}

        def single(_e) -> None:
            if pending["id"]:
                cell["outer"].after_cancel(pending["id"])
            pending["id"] = cell["outer"].after(250, on_click)

        def double(_e) -> None:
            if pending["id"]:
                cell["outer"].after_cancel(pending["id"])
                pending["id"] = None
            on_double()

        def popup(event) -> None:
            menu = menu_builder()
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        widgets = [cell["outer"], cell["border"], cell["img_lbl"], cell["name_lbl"]]
        for w in widgets:
            w.bind("<Button-1>", single)
            w.bind("<Double-Button-1>", double)
            w.bind("<Button-3>", popup)
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                w.bind(seq, self._on_mousewheel)

    def _highlight_seed(self, selected: bool) -> None:
        self._selected_seed = selected
        if not hasattr(self, "seed_canvas"):
            return
        self.seed_canvas.configure(
            highlightthickness=2 if selected else 1,
            highlightbackground=(
                self._grid_theme.border_selected
                if selected
                else self._grid_theme.border_default
            ),
        )

    def _highlight_images(self, key: str | None) -> None:
        self._selected_image_key = key
        for name, cell in self._img_cells.items():
            cell["border"].configure(
                highlightbackground=(
                    self._grid_theme.border_selected
                    if name == key
                    else self._grid_theme.border_default
                )
            )

    def _highlight_videos(self, key: str | None) -> None:
        self._selected_video_key = key
        for name, cell in self._vid_cells.items():
            cell["border"].configure(
                highlightbackground=(
                    self._grid_theme.border_selected
                    if name == key
                    else self._grid_theme.border_default
                )
            )

    def _clear_row_selection(self) -> None:
        self._highlight_images(None)
        self._highlight_videos(None)

    def _select_seed(self, *, preview: bool = True) -> None:
        self._highlight_seed(True)
        self._clear_row_selection()
        if preview:
            self._preview_seed()

    def _select_series_image(self, item: SeriesItem, *, preview: bool = True) -> None:
        self._highlight_seed(False)
        self._highlight_images(item.image_name)
        self._highlight_videos(None)
        if not preview or self._meta is None:
            return
        path = item.image_path(self._meta.batch_id)
        if not path.is_file():
            self._on_preview_empty(item.image_error or "图片缺失")
            return
        self._show_series_preview(item, generating=False)
        self._ensure_video_prompt_async(item)

    def _select_video(self, item: SeriesItem) -> None:
        self._highlight_seed(False)
        self._highlight_images(None)
        self._highlight_videos(item.image_name)
        video_path = item.video_path(self._meta.batch_id) if self._meta else None
        if video_path is None or not video_path.is_file():
            self._on_preview_empty("这一格还没有视频，选中系列图后点「生成视频」")
            return
        image_path = item.image_path(self._meta.batch_id)
        self._on_preview_video(
            image_path,
            video_path,
            title=f"视频 {item.index:03d} · {item.video_provider}",
            image_prompt=self._series_image_review_text(item),
            video_prompt=item.video_prompt,
        )

    # ========================================================== 右键菜单
    def _image_menu(self, item: SeriesItem) -> tk.Menu:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="预览这张图", command=lambda: self._preview_item_image(item))
        menu.add_command(
            label="重新生成这张图", command=lambda: self._start_regenerate_image(item)
        )
        menu.add_command(
            label="生成 / 重生这段视频",
            command=lambda it=item: self._regenerate_video(it),
        )
        menu.add_separator()
        menu.add_command(label="删除该项", command=lambda: self._delete_item(item))
        return menu

    def _video_menu(self, item: SeriesItem) -> tk.Menu:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="播放", command=lambda: self._preview_item_video(item))
        menu.add_command(
            label="重新生成", command=lambda it=item: self._regenerate_video(it)
        )
        return menu

    def _delete_item(self, item: SeriesItem) -> None:
        if self._meta is None or self._busy:
            return
        if not messagebox.askyesno("删除", f"删除第 {item.index:03d} 张系列图（含对应视频）？"):
            return
        img = item.image_path(self._meta.batch_id)
        vid = item.video_path(self._meta.batch_id)
        img.unlink(missing_ok=True)
        if vid is not None:
            vid.unlink(missing_ok=True)
        self._meta.items = [it for it in self._meta.items if it.index != item.index]
        self._meta.save()
        if self._selected_image_key == item.image_name:
            self._selected_image_key = None
        if self._selected_video_key == item.image_name:
            self._selected_video_key = None
        self._render_seed()
        self._render_rows()
        self._log(f"[系列视频] 已删除第 {item.index:03d} 张系列图")

    def _delete_video(self, item: SeriesItem) -> None:
        if self._meta is None or self._busy:
            return
        path = item.video_path(self._meta.batch_id)
        if path is None or not path.is_file():
            return
        if not messagebox.askyesno("删除视频", f"删除第 {item.index:03d} 段视频？"):
            return
        delete_item_video(self._meta, item)
        self._paint_video_cell(item)
        self._log(f"[系列视频] 已删除第 {item.index:03d} 段视频")

    def _clear_seed(self) -> None:
        if self._busy or self._meta is None or not self._meta.has_seed:
            return
        if not messagebox.askyesno(
            "取消定稿",
            "取消当前种子图定稿？下方候选仍保留，可重新双击选择。",
        ):
            return
        clear_batch_seed(self._meta)
        self._sync_series_widgets(self._meta)
        self._render_seed()
        self._render_candidates()
        self._render_rows()
        self._log("[系列视频] 已取消种子图定稿")

    def _on_cand_mousewheel(self, event) -> str:
        if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            self.cand_canvas.yview_scroll(1, "units")
        elif getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            self.cand_canvas.yview_scroll(-1, "units")
        return "break"

    # ============================================================ 预览
    def _preview_seed_or_candidate(self) -> None:
        if self._meta is not None and self._meta.has_seed:
            self._select_seed(preview=True)
            return
        if self._preview_cand_name and self._meta is not None:
            cand = next(
                (c for c in self._meta.seed_candidates if c.name == self._preview_cand_name),
                None,
            )
            if cand is not None:
                self._preview_candidate(cand)

    def _preview_seed(self) -> None:
        if self._meta is None or not self._meta.has_seed:
            return
        if self._seed_needs_analysis():
            self._start_seed_analysis()
            return
        self._on_preview_image(
            self._meta.seed_path,
            title=f"种子图 · {self._meta.batch_id}",
            prompt=self._seed_analysis_text(),
        )

    def _series_image_review_text(self, item: SeriesItem, *, generating: bool = False) -> str:
        if self._meta is None:
            return "（尚无 Gemini 评审）"
        text = format_series_image_review(
            item.image_review,
            series_id=self._meta.series_id,
            image_error=item.image_error,
        )
        if generating:
            text = f"{text}\n\n正在生成视频 prompt…" if text else "正在生成视频 prompt…"
        return text

    def _show_series_preview(self, item: SeriesItem, *, generating: bool = False) -> None:
        if self._meta is None:
            return
        path = item.image_path(self._meta.batch_id)
        self._on_preview_series(
            path,
            title=f"系列图 {item.index:03d} · {item.summary}",
            image_prompt=self._series_image_review_text(item, generating=generating),
            video_prompt=item.video_prompt,
            generating=generating,
        )

    def _ensure_video_prompt_async(self, item: SeriesItem) -> None:
        if self._meta is None:
            return
        key = item.image_name
        existing = (item.video_prompt or "").strip()
        # 规范改版后旧 prompt 会不合规（例如新增的「实时速度」维度），这里和
        # generate_video_prompt_for_item 用同一把尺子，预览时就顺手重生成。
        if existing and not validate_video_prompt(existing, self._meta.series_id if self._meta else ""):
            self._show_series_preview(item, generating=False)
            return
        if key in self._video_prompt_busy:
            self._show_series_preview(item, generating=True)
            return
        self._video_prompt_busy.add(key)
        self._show_series_preview(item, generating=True)
        meta = self._meta

        def job() -> None:
            try:
                generate_video_prompt_for_item(
                    meta,
                    item,
                    log_fn=lambda m: schedule_on_main(self, self._log, m),
                )
            except Exception as exc:  # noqa: BLE001
                item.video_error = str(exc)
                meta.save()
                schedule_on_main(self, self._log, f"[视频 prompt] 失败：{exc}")
            finally:
                def done() -> None:
                    self._video_prompt_busy.discard(key)
                    if self._selected_image_key == key:
                        self._show_series_preview(item, generating=False)
                        self._paint_video_cell(item)

                schedule_on_main(self, done)

        threading.Thread(target=job, daemon=True).start()

    def _preview_item_image(self, item: SeriesItem) -> None:
        self._select_series_image(item, preview=True)

    def _preview_item_video(self, item: SeriesItem) -> None:
        if self._meta is None:
            return
        self._select_video(item)

    def stop_playback(self) -> None:
        self._on_stop_playback()

    # ============================================================ 任务
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for btn in (
            self.btn_gen_images,
            self.btn_gen_videos,
            self.btn_pick_seed,
            self.btn_gen_seeds,
        ):
            btn.configure(state=state)
        # 没有「停止」按钮：新任务开始前会清掉上一轮的取消标志；
        # 若用户切走 Tab，后台线程仍会跑完当前这一张。

    def _run_bg(self, fn: Callable[[], None]) -> None:
        self._cancel.clear()
        self._set_busy(True)

        def worker() -> None:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._log, f"[系列视频] 失败：{exc}")
            finally:
                schedule_on_main(self, self._finish_task)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_task(self) -> None:
        self._set_busy(False)
        self._sync_series_widgets(self._meta)
        self._render_seed()
        self._render_candidates()
        self._render_rows()

    # ------------------------------------------------------ 种子图文生图
    def _selected_series_id(self) -> str:
        """已定稿批次以 batch.json 为准，未定稿时用下拉框选的。"""
        if self._meta is not None and self._meta.has_seed and self._meta.series_id:
            return self._meta.series_id
        return self._series_labels.get(self.series_var.get(), default_series_id())

    def _start_generate_seeds(self) -> None:
        if self._busy:
            return
        idea = self.seed_idea_var.get().strip()
        count = max(1, int(self.seed_count_var.get() or 1))
        series_id = self._selected_series_id()
        meta = self._ensure_prompt_batch(idea)
        # 未定稿的批次也记下「打算做哪个系列」，重启后不用重选；
        # 真正锁定发生在定稿那一刻，用的是候选图实际被判成什么。
        if not meta.has_seed and meta.series_id != series_id:
            meta.series_id = series_id
            meta.save()
        self._log(
            f"[系列视频] 文生图生成 {count} 张待选种子 · {series_label(series_id)}"
            + (f"（关键字：{idea}）" if idea else "（该系列主体库）")
            + " …"
        )

        def job() -> None:
            generate_seed_candidates(
                meta,
                count=count,
                idea=idea,
                series_id=series_id,
                log_fn=lambda m: schedule_on_main(self, self._log, m),
                on_item=lambda *_a: schedule_on_main(self, self._render_candidates),
                should_stop=self._cancel.is_set,
            )

        self._run_bg(job)

    # ------------------------------------------------------ 图片生成
    def _start_generate_images(self) -> None:
        if self._busy:
            return
        if self._meta is None or not self._meta.has_seed:
            messagebox.showinfo(
                "系列视频",
                "请先导入种子图，或生成种子图候选后双击定稿。",
            )
            return
        count = max(1, int(self.count_var.get() or 1))
        constraints = self.series_constraints_var.get().strip()
        meta = self._meta
        self._log(
            f"[系列视频] 开始由种子图生成 {count} 张系列图"
            + (f"（限定：{constraints}）" if constraints else "")
            + " …"
        )

        def job() -> None:
            generate_series_images(
                meta,
                count=count,
                constraints=constraints,
                log_fn=lambda m: schedule_on_main(self, self._log, m),
                on_item=lambda *_a: schedule_on_main(self, self._render_rows),
                should_stop=self._cancel.is_set,
            )

        self._run_bg(job)

    def _start_regenerate_image(self, item: SeriesItem) -> None:
        if self._busy or self._meta is None:
            return
        meta = self._meta

        def job() -> None:
            regenerate_image(meta, item, log_fn=lambda m: schedule_on_main(self, self._log, m))

        self._run_bg(job)

    # ------------------------------------------------------ 视频生成
    def _regenerate_video(self, item: SeriesItem) -> None:
        self._select_series_image(item, preview=False)
        self._start_generate_video_for_selection(force=True)

    @staticmethod
    def _provider_request_params(provider_id: str, meta: BatchMeta) -> tuple[str, int]:
        if provider_id == "jimeng_web":
            return "720p", video_gen.DEFAULT_DURATION_SEC
        if provider_id in ("elevenlabs_http", "elevenlabs_web"):
            return video_gen.DEFAULT_RESOLUTION, video_gen.DEFAULT_DURATION_SEC
        return meta.resolution or video_gen.DEFAULT_RESOLUTION, (
            meta.duration_sec or video_gen.DEFAULT_DURATION_SEC
        )

    def _start_generate_video_for_selection(self, *, force: bool = False) -> None:
        if self._busy:
            return
        meta = self._meta
        if meta is None or not self._selected_image_key:
            messagebox.showinfo("系列视频", "请先在「② 系列图」中单击选择一张系列图。")
            return
        item = meta.item_by_image(self._selected_image_key)
        if item is None:
            return
        if not item.image_path(meta.batch_id).is_file():
            messagebox.showwarning("系列视频", "选中的系列图文件缺失。")
            return

        providers = []
        provider = self._current_provider()
        if provider is not None:
            try:
                ok, reason = provider.available()
            except Exception as exc:  # noqa: BLE001
                ok, reason = False, str(exc)
            if ok:
                providers = [provider]
            else:
                messagebox.showwarning(
                    "视频来源不可用",
                    f"{self.provider_var.get()}：{reason}",
                )
                return
        if not providers:
            messagebox.showwarning(
                "视频来源不可用",
                "请选择 jimeng_web 或 elevenLabs_web，并先完成登录。",
            )
            return

        out_dir = series_video_dir(meta.batch_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / series_video_name(item.index)
        self._log(f"[系列视频] 生成 {out.name}（{self.provider_var.get()}）…")
        self._paint_video_cell(item, status="生成中 …")

        def job() -> None:
            image_path = item.image_path(meta.batch_id)
            # 旧批次系列图评审可能没查「高速静帧」；花钱提交即梦前必须再拦一次。
            try:
                still_gate = gate_still_for_video(
                    image_path,
                    meta.series_id,
                    prompt=item.prompt,
                    log_fn=lambda m: schedule_on_main(self, self._log, m),
                )
            except Exception as exc:  # noqa: BLE001
                item.video_error = f"出片前静帧闸失败：{exc}"
                meta.save()
                schedule_on_main(self, self._log, f"[系列视频] {item.video_error}")
                schedule_on_main(self, self._paint_video_cell, item)
                return
            if still_gate.blocked:
                item.image_review = still_gate.to_dict()
                item.image_error = (
                    f"高速静帧/慢镜头风险：{'；'.join(still_gate.issues) or '需重出系列图'}"
                )
                item.video_error = item.image_error
                meta.save()
                schedule_on_main(
                    self,
                    self._log,
                    f"[系列视频] 已拦截提交：{item.image_error}",
                )
                schedule_on_main(self, self._paint_video_cell, item)
                schedule_on_main(self, self._paint_image_cell, item)
                return

            try:
                prompt = generate_video_prompt_for_item(
                    meta,
                    item,
                    log_fn=lambda m: schedule_on_main(self, self._log, m),
                    force=force and not (item.video_prompt or "").strip(),
                )
            except Exception as exc:  # noqa: BLE001
                item.video_error = str(exc)
                meta.save()
                schedule_on_main(self, self._log, f"[系列视频] 视频 prompt 失败：{exc}")
                schedule_on_main(self, self._paint_video_cell, item)
                return

            last_err = ""
            for provider in providers:
                if self._cancel.is_set():
                    schedule_on_main(self, self._log, "[系列视频] 已取消")
                    schedule_on_main(self, self._paint_video_cell, item)
                    return
                resolution, duration_sec = self._provider_request_params(provider.id, meta)
                req = video_gen.VideoRequest(
                    image_path=item.image_path(meta.batch_id),
                    prompt=prompt,
                    out_path=out,
                    duration_sec=duration_sec,
                    resolution=resolution,
                    aspect_ratio=meta.aspect_ratio,
                    progress_fn=lambda pct, it=item: schedule_on_main(
                        self,
                        self._paint_video_cell,
                        it,
                        status=f"{pct}% 造梦中",
                    ),
                )
                schedule_on_main(
                    self,
                    self._log,
                    f"[系列视频] 尝试 {provider.label} → {out.name}",
                )
                try:
                    provider.generate(
                        req,
                        log_fn=lambda m: schedule_on_main(self, self._log, m),
                    )
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
                    schedule_on_main(
                        self,
                        self._log,
                        f"[系列视频] {provider.label} 失败：{exc}",
                    )
                    continue

                item.video_name = out.name
                item.video_prompt = prompt
                item.video_provider = provider.id
                item.video_error = ""
                meta.save()
                schedule_on_main(self, self._paint_video_cell, item, status="验收中 …")
                schedule_on_main(self, self._log, f"[系列视频] 完成：{out}")
                # 产物验收：先客观测运动量（拦慢镜头），过了再让 Gemini 看抽帧。
                # 不合格只标记不删文件 —— 视频是花钱买的，留给人自己看一眼再定。
                try:
                    accept_video(
                        meta,
                        item,
                        out,
                        log_fn=lambda m: schedule_on_main(self, self._log, m),
                    )
                except Exception as exc:  # noqa: BLE001 - 验收挂了不影响已生成的视频
                    schedule_on_main(self, self._log, f"[视频验收] 跳过：{exc}")
                schedule_on_main(self, self._paint_video_cell, item)
                schedule_on_main(self, self._preview_item_video, item)
                return

            item.video_error = last_err or f"{self.provider_var.get()} 生成失败"
            meta.save()
            schedule_on_main(self, self._paint_video_cell, item)
            schedule_on_main(self, self._log, f"[系列视频] 失败：{item.video_error}")

        self._run_bg(job)

    def _style_close_button(self, btn: tk.Button) -> None:
        colors = self._grid_theme
        btn.configure(
            bg=colors.cell_bg,
            fg=colors.fg_muted,
            activebackground=colors.cell_bg,
            activeforeground=colors.fg_hover,
            highlightbackground=colors.border_default,
        )

    # ============================================================ 主题
    def apply_theme(self, theme: UiTheme) -> None:
        self._ui_theme = theme
        self._grid_theme = grid_theme(theme)
        for lbl in self._muted_labels:
            lbl.configure(foreground=self._grid_theme.fg_muted)
        for canvas in (
            self.seed_canvas,
            self.cand_canvas,
            self.col_images.canvas,
            self.col_videos.canvas,
        ):
            canvas.configure(bg=theme.canvas_bg)
        self.seed_canvas.configure(highlightbackground=self._grid_theme.border_default)
        self._highlight_seed(self._selected_seed)
        self._highlight_images(self._selected_image_key)
        self._highlight_videos(self._selected_video_key)
        paint_widget_bg(theme.canvas_bg, self.cand_host, self.seed_frame)
        for col in (self.col_images, self.col_videos):
            col.host.configure(bg=theme.canvas_bg)
        self._style_close_button(self.btn_clear_seed)
        for cell in list(self._img_cells.values()) + list(self._vid_cells.values()):
            widgets = [
                cell["outer"],
                cell["border"],
                cell["img_lbl"],
                cell["name_lbl"],
            ]
            paint_widget_bg(self._grid_theme.cell_bg, *widgets)
            cell["name_lbl"].configure(fg=self._grid_theme.fg_default)
            btn_del = cell.get("btn_del")
            if btn_del is not None:
                self._style_close_button(btn_del)
        for cell in self._cand_cells.values():
            paint_widget_bg(
                self._grid_theme.cell_bg,
                cell["outer"],
                cell["thumb"],
                cell["name_lbl"],
            )
            cell["name_lbl"].configure(fg=self._grid_theme.fg_default)
        self._render_seed()
        if self._meta is not None:
            for item in self._meta.items:
                self._paint_image_cell(item)
                self._paint_video_cell(item)
        self._highlight_seed(self._selected_seed)
        self._highlight_images(self._selected_image_key)
        self._highlight_videos(self._selected_video_key)


__all__ = ["SeriesVideoTab"]
