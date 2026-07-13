"""relaxASMR 工程 GUI（Tkinter）。"""

from __future__ import annotations

import json
import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"  # Suppress TensorFlow warnings

import sys
import threading
import shutil
import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
REAPER_SCRIPTS = REPO_ROOT / "Reaper" / "scripts"
if str(REAPER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(REAPER_SCRIPTS))

from scripts.config.paths import ensure_gui_path  # noqa: E402

ensure_gui_path()

from rain_subproject_lib import (  # noqa: E402
    REPO_ROOT as LIB_REPO_ROOT,
    build_scene_config_from_gui,
    derive_scene_id,
    ensure_shared_scripts,
)
from gui.reaper_launch import (  # noqa: E402
    default_reaper_candidates,
    default_windows_reaper_from_wsl,
    format_job_progress,
    is_wsl,
    open_reaper_project,
    render_reaper_project,
)
from gui.folder_open import open_folder  # noqa: E402
from gui.import_reload import load_module, load_scripts_module  # noqa: E402
from gui.audio_library_tab import AudioLibraryTab, wav_display_title  # noqa: E402
from gui.ui_theme import (
    apply_primary_button_style,
    apply_tk_theme,
    apply_ttk_theme,
    get_theme,
    normalize_theme,
    theme_toggle_label,
)  # noqa: E402
from gui.export_mix_preview import ExportMixPreviewGrid  # noqa: E402
from gui.tk_thread import bind_ui_root, ensure_ui_pump, schedule_on_main  # noqa: E402
from gui.job_progress import make_elapsed_ticker, parse_progress_pct  # noqa: E402
from gui.export_wav import (  # noqa: E402
    expected_export_wav_path,
    export_mp4_belongs_to_scene,
    find_export_mp4_for_scene,
    format_duration_short,
    format_mp4_export_stats_suffix,
    wav_duration_seconds,
    wav_matches_target_hours,
)
from gui.youtube_material import (  # noqa: E402
    RAIN_THUMB_TITLE,
    find_material_dir,
    loop_material_dir,
)
from scripts.config.paths import (  # noqa: E402
    base_url,
    ensure_base_url_dirs,
    ensure_rain_fx_png,
    export_dir,
    export_wav_name,
    get_scene_rpp_path,
    get_subproject_dir,
    get_thumbnail_path,
    get_scene_number,
    is_mac,
    material_dir as base_material_dir,
    material_json_path,
    material_metadata_path,
)

CONFIG_PATH = Path(__file__).resolve().parent / "user_config.json"
YT_MATERIAL_SCRIPT = LIB_REPO_ROOT / "scripts" / "video_export" / "generate_youtube_material.py"


class RelaxAsmrApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("自然之声-自动化界面")
        self.geometry("1600x980")
        self.minsize(720, 600)

        self.video_path: Path | None = None
        self.video_rel: str | None = None
        self.scene_id: str | None = None
        self.subproject_dir: Path | None = None
        self.rpp_path: Path | None = None
        self.material_dir: Path | None = None
        self.upload_mp4_custom: Path | None = None
        self._busy = False
        self._render_running = False
        self._export_running = False
        self._upload_running = False
        self.last_export_wav: Path | None = None
        self.last_export_mp4: Path | None = None
        
        self._cap = None
        self._video_loop_id = None
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        self._load_config()
        self._theme_mode = normalize_theme(self._cfg.get("theme", "light"))
        self._build_ui()
        ensure_ui_pump(self)
        bind_ui_root(self)
        bind_ui_root(self)

    def _step45_task_running(self) -> bool:
        return self._render_running or self._export_running or self._upload_running

    def _on_closing(self) -> None:
        if self._step45_task_running():
            tasks: list[str] = []
            if self._render_running:
                tasks.append("步骤 4 · 输出混音")
            if self._export_running:
                tasks.append("步骤 4 · 合成视频")
            if self._upload_running:
                tasks.append("步骤 5 · 上传 YouTube")
            detail = "\n".join(f"· {t}" for t in tasks)
            if not messagebox.askyesno(
                "确认关闭",
                f"以下任务正在执行：\n{detail}\n\n关闭窗口会中断任务。确定要关闭吗？",
                icon="warning",
            ):
                return
        self._stop_video_loop()
        if self._right_pane_resize_after_id:
            self.after_cancel(self._right_pane_resize_after_id)
            self._right_pane_resize_after_id = None
        try:
            from gui.audio_library_tab import _unpin_all
            from gui.audio_playback import force_stop_all_playback

            _unpin_all()
            force_stop_all_playback()
        except Exception:
            pass
        try:
            if os.path.exists("/tmp/relaxasmr_preview.mp4"):
                os.remove("/tmp/relaxasmr_preview.mp4")
        except Exception:
            pass
        self.destroy()

    def _format_duration_hours(self, hours: float | int | str) -> str:
        h = float(hours)
        return str(int(h)) if h == int(h) else f"{h:g}"

    def _initial_duration_str(self) -> str:
        for key in ("duration_hours", "target_duration"):
            raw = self._cfg.get(key)
            if raw is None or str(raw).strip() == "":
                continue
            try:
                return self._format_duration_hours(raw)
            except (TypeError, ValueError):
                continue
        return "3"

    def _parse_duration_hours(self) -> float:
        try:
            return float(self.duration_var.get())
        except (ValueError, tk.TclError) as exc:
            raise ValueError("成片时长必须是数字。") from exc

    def _persist_duration_hours(self, hours: float) -> None:
        h = float(hours)
        stored = int(h) if h == int(h) else h
        self._cfg["duration_hours"] = stored
        self._cfg["target_duration"] = self._format_duration_hours(h)
        self._save_config()

    def _load_config(self) -> None:
        self._cfg = {}
        if CONFIG_PATH.is_file():
            try:
                self._cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._cfg = {}

    def _save_config(self) -> None:
        try:
            CONFIG_PATH.write_text(
                json.dumps(self._cfg, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def _setup_primary_button_style(self) -> str:
        return apply_primary_button_style(ttk.Style(self))

    def _theme_tk_widgets(self) -> dict[str, tk.Widget | list[tk.Widget]]:
        library_canvases: list[tk.Widget] = []
        for tab in getattr(self, "_audio_library_tabs", {}).values():
            canvas = getattr(tab, "_canvas", None)
            if canvas is not None:
                library_canvases.append(canvas)
        video_tab = getattr(self, "video_library_tab", None)
        video_canvas = getattr(video_tab, "_canvas", None) if video_tab is not None else None
        if video_canvas is not None:
            library_canvases.append(video_canvas)
        return {
            "cover_canvas": getattr(self, "cover_thumb_canvas", None),
            "preview_canvas": getattr(self, "preview_video_canvas", None),
            "left_scroll_canvas": getattr(self, "_left_scroll_canvas", None),
            "library_canvases": library_canvases,
            "cover_title": getattr(self, "lbl_cover_title_en", None),
            "preview_title": getattr(self, "lbl_preview_title_zh", None),
            "cover_desc": getattr(self, "txt_cover_desc_en", None),
            "preview_desc": getattr(self, "txt_preview_desc_zh", None),
            "log_text": getattr(self, "log_text", None),
        }

    def _apply_theme(self, mode: str | None = None) -> None:
        self._theme_mode = normalize_theme(mode or self._theme_mode)
        palette = get_theme(self._theme_mode)
        apply_ttk_theme(ttk.Style(self), palette)
        apply_tk_theme(self, palette, self._theme_tk_widgets())
        for picker in getattr(self, "track_pickers", {}).values():
            if hasattr(picker, "apply_theme"):
                picker.apply_theme(palette)
        mix_preview = getattr(self, "mix_preview_grid", None)
        if mix_preview is not None and hasattr(mix_preview, "apply_theme"):
            mix_preview.apply_theme(palette)
        for tab in getattr(self, "_audio_library_tabs", {}).values():
            if hasattr(tab, "apply_theme"):
                tab.apply_theme(palette)
        video_tab = getattr(self, "video_library_tab", None)
        if video_tab is not None and hasattr(video_tab, "apply_theme"):
            video_tab.apply_theme(palette)
        if hasattr(self, "btn_theme_toggle"):
            self.btn_theme_toggle.configure(text=theme_toggle_label(self._theme_mode))
        self._cfg["theme"] = self._theme_mode
        self._save_config()

    def _toggle_theme(self) -> None:
        next_mode = "light" if self._theme_mode == "dark" else "dark"
        self._apply_theme(next_mode)

    def _build_ui(self) -> None:
        primary_btn = self._setup_primary_button_style()

        self.main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.left_frame = ttk.Frame(self.main_pane)
        self.right_frame = ttk.Frame(self.main_pane)
        self.main_pane.add(self.left_frame, weight=3)
        self.main_pane.add(self.right_frame, weight=2)

        self.left_notebook = ttk.Notebook(self.left_frame)
        self.left_notebook.pack(fill=tk.BOTH, expand=True)

        self.workflow_tab = ttk.Frame(self.left_notebook)
        self.left_notebook.add(self.workflow_tab, text="工作流")

        from gui.video_library_tab import VideoLibraryTab

        self.video_library_tab = VideoLibraryTab(
            self.left_notebook,
            is_uploaded=self._is_video_uploaded,
            toggle_uploaded=self._set_video_uploaded,
            on_video_select=self._select_video_from_library,
            log_fn=self._log,
        )
        self.left_notebook.add(self.video_library_tab, text="视频素材库")

        self.rain_boom_library_tab = AudioLibraryTab(
            self.left_notebook,
            layer_id="1_rain",
            track_id="1_rain_boom",
            on_selection_changed=self._on_audio_library_selection,
            log_fn=self._log,
        )
        self.left_notebook.add(self.rain_boom_library_tab, text="rain boom 素材库")

        self.impact_library_tab = AudioLibraryTab(
            self.left_notebook,
            layer_id="2_impact",
            track_id="2_impact",
            on_selection_changed=self._on_audio_library_selection,
            log_fn=self._log,
        )
        self.left_notebook.add(self.impact_library_tab, text="impact 素材库")

        self.random_library_tab = AudioLibraryTab(
            self.left_notebook,
            layer_id="3_random",
            track_id="3_random",
            on_selection_changed=self._on_audio_library_selection,
            log_fn=self._log,
        )
        self.left_notebook.add(self.random_library_tab, text="random 素材库")

        self.wildlife_library_tab = AudioLibraryTab(
            self.left_notebook,
            layer_id="4_wildlife",
            track_id="4_wildlife",
            on_selection_changed=self._on_audio_library_selection,
            log_fn=self._log,
        )
        self.left_notebook.add(self.wildlife_library_tab, text="wildlife 素材库")

        self._audio_library_tabs = {
            "1_rain_boom": self.rain_boom_library_tab,
            "2_impact": self.impact_library_tab,
            "3_random": self.random_library_tab,
            "4_wildlife": self.wildlife_library_tab,
        }

        # === 左侧工作流：步骤 1–5（小屏溢出时可垂直滚动）===
        self._setup_workflow_scroll(self.workflow_tab)

        # 1. 导入与分析
        sec1 = ttk.LabelFrame(self.left_content, text="1. 导入与分析", padding=10)
        sec1.pack(fill=tk.X, pady=(0, 10))

        row1 = ttk.Frame(sec1)
        row1.pack(fill=tk.X)
        ttk.Button(row1, text="选择 MP4…", command=self._import_video).pack(side=tk.LEFT)
        self.btn_analyze = ttk.Button(
            row1,
            text="开始分析",
            command=self._start_analysis,
            style=primary_btn,
        )
        self.btn_analyze.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_open_output = ttk.Button(row1, text="打开物料目录", command=self._open_output)
        self.btn_open_output.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_theme_toggle = ttk.Button(
            row1,
            text=theme_toggle_label(self._theme_mode),
            command=self._toggle_theme,
        )
        self.btn_theme_toggle.pack(side=tk.LEFT, padx=(8, 0))
        self.chk_overwrite_mat_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="覆盖物料", variable=self.chk_overwrite_mat_var).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        row2 = ttk.Frame(sec1)
        row2.pack(fill=tk.X, pady=(8, 0))
        self.lbl_video = ttk.Label(row2, text="未选择")
        self.lbl_video.pack(side=tk.LEFT, anchor=tk.W)

        # 2. 选择四轨音频
        sec2 = ttk.LabelFrame(self.left_content, text="2. 选择四轨声音库 (按画面推荐)", padding=10)
        sec2.pack(fill=tk.X, pady=(0, 10))

        self.pickers_notebook = ttk.Notebook(sec2)
        self.pickers_notebook.pack(fill=tk.X)

        self.track_pickers = {}
        from gui.track_picker_ui import TrackPickerUI
        for track_id in ["1_rain", "2_impact", "3_random", "4_wildlife"]:
            frame = ttk.Frame(self.pickers_notebook, padding=6)
            self.pickers_notebook.add(frame, text=track_id)
            picker = TrackPickerUI(frame, track_name=track_id, log_fn=self._log)
            picker.on_select_callback = self._on_grid_select
            picker.pack()
            self.track_pickers[track_id] = picker

        self._ensure_rain_boom_tab()
        self._select_rain_boom_tab()

        # 3. 新建 Reaper 工程
        sec3 = ttk.LabelFrame(self.left_content, text="3. 新建 Reaper 工程", padding=10)
        sec3.pack(fill=tk.X, pady=(0, 10))

        row_gen = ttk.Frame(sec3)
        row_gen.pack(fill=tk.X)

        self.btn_gen_project = ttk.Button(
            row_gen,
            text="新建Reaper工程",
            command=self._create_project,
            style=primary_btn,
        )
        self.btn_gen_project.pack(side=tk.LEFT)
        self.btn_open_reaper = ttk.Button(
            row_gen,
            text="打开Reaper工程",
            command=self._open_reaper,
        )
        self.btn_open_reaper.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(row_gen, text="成片时长(小时)").pack(side=tk.LEFT, padx=(8, 0))
        self.duration_var = tk.StringVar(value=self._initial_duration_str())
        ttk.Entry(row_gen, textvariable=self.duration_var, width=5).pack(side=tk.LEFT, padx=(8, 0))
        
        self.chk_overwrite_rpp_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row_gen, text="覆盖已有 .rpp", variable=self.chk_overwrite_rpp_var).pack(side=tk.LEFT, padx=(8, 0))

        # 4. 导出音频与合成视频
        sec_export = ttk.LabelFrame(self.left_content, text="4. 导出音频与合成视频", padding=10)
        sec_export.pack(fill=tk.X, pady=(0, 10))

        row_mix = ttk.Frame(sec_export)
        row_mix.pack(fill=tk.X)
        self.btn_render_reaper = ttk.Button(
            row_mix,
            text="一键输出混音",
            command=self._render_headless,
            style=primary_btn,
        )
        self.btn_render_reaper.pack(side=tk.LEFT)
        self.btn_open_export = ttk.Button(row_mix, text="打开混音目录", command=self._open_export_dir)
        self.btn_open_export.pack(side=tk.LEFT, padx=(8, 0))
        self.mix_preview_grid = ExportMixPreviewGrid(row_mix, log_fn=self._log)
        self.mix_preview_grid.pack(side=tk.LEFT, padx=(8, 0))

        row_export = ttk.Frame(sec_export)
        row_export.pack(fill=tk.X, pady=(10, 0))
        self.btn_export = ttk.Button(
            row_export,
            text="一键合成视频",
            command=self._export_mp4,
            style=primary_btn,
        )
        self.btn_export.pack(side=tk.LEFT)
        self.lbl_export = ttk.Label(row_export, text="待开始", wraplength=520)
        self.lbl_export.pack(side=tk.LEFT, padx=(8, 0))

        # 5. YouTube 一键上传
        sec4 = ttk.LabelFrame(self.left_content, text="5. 一键上传 YouTube", padding=10)
        sec4.pack(fill=tk.X)

        ttk.Frame(self.left_content).pack(fill=tk.BOTH, expand=True)

        row4 = ttk.Frame(sec4)
        row4.pack(fill=tk.X)
        self.btn_upload = ttk.Button(
            row4,
            text="上传到 YouTube",
            command=self._upload_youtube,
            style=primary_btn,
        )
        self.btn_upload.pack(side=tk.LEFT, padx=(0, 16))
        ttk.Label(row4, text="可见性").pack(side=tk.LEFT)
        self.privacy_var = tk.StringVar(value=self._cfg.get("youtube_privacy", "public"))
        ttk.Combobox(
            row4,
            textvariable=self.privacy_var,
            values=("public", "unlisted", "private"),
            width=10,
            state="readonly",
        ).pack(side=tk.LEFT, padx=(8, 16))
        ttk.Label(row4, text="标题/描述").pack(side=tk.LEFT)
        self.upload_lang_var = tk.StringVar(value=self._cfg.get("youtube_language", "en"))
        ttk.Combobox(
            row4,
            textvariable=self.upload_lang_var,
            values=("en", "zh"),
            width=6,
            state="readonly",
        ).pack(side=tk.LEFT, padx=(8, 16))
        self.use_leo_usa_var = tk.BooleanVar(
            value=self._cfg.get("youtube_account", "leo") == "leo_usa"
        )
        ttk.Checkbutton(row4, text="leo_usa", variable=self.use_leo_usa_var).pack(
            side=tk.LEFT
        )

        row_upload_pick = ttk.Frame(sec4)
        row_upload_pick.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(
            row_upload_pick,
            text="上传自定义视频",
            command=self._pick_upload_mp4,
        ).pack(side=tk.LEFT)
        ttk.Button(
            row_upload_pick,
            text="恢复默认",
            command=self._reset_upload_mp4_default,
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.lbl_upload = ttk.Label(sec4, text="待上传：—", wraplength=400)
        self.lbl_upload.pack(anchor=tk.W, pady=(8, 0))
        
        # === 右侧：封面预览 + 视频预览 + 日志（三等分）===
        self.right_pane = ttk.PanedWindow(self.right_frame, orient=tk.VERTICAL)
        self.right_pane.pack(fill=tk.BOTH, expand=True)

        self.cover_frame = ttk.LabelFrame(self.right_pane, text="封面预览", padding=10)
        self.lbl_cover_video_name = ttk.Label(
            self.cover_frame,
            text="—",
            wraplength=480,
            foreground="gray",
        )
        self.lbl_cover_video_name.pack(anchor=tk.W, pady=(0, 6))
        self.cover_body = ttk.Frame(self.cover_frame)
        self.cover_body.pack(fill=tk.BOTH, expand=True)
        self.cover_body.columnconfigure(0, weight=0, minsize=213)
        self.cover_body.columnconfigure(1, weight=1)
        self.cover_body.rowconfigure(0, weight=1)

        self._cover_slot_w, self._cover_slot_h = 213, 120
        self.cover_thumb_canvas = tk.Canvas(
            self.cover_body,
            width=self._cover_slot_w,
            height=self._cover_slot_h,
            highlightthickness=0,
            bd=0,
        )
        self.cover_thumb_canvas.grid(row=0, column=0, sticky="nw", padx=(0, 10))

        cover_meta = ttk.Frame(self.cover_body)
        cover_meta.grid(row=0, column=1, sticky="nsew")
        cover_meta.columnconfigure(0, weight=1)
        cover_meta.rowconfigure(1, weight=1)

        self.lbl_cover_title_en = tk.Label(
            cover_meta,
            text="",
            anchor="nw",
            justify=tk.LEFT,
            wraplength=320,
            font=("", 11, "bold"),
        )
        self.lbl_cover_title_en.grid(row=0, column=0, sticky="new")

        self.txt_cover_desc_en = tk.Text(
            cover_meta,
            height=6,
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=0,
            state=tk.DISABLED,
            font=("", 10),
        )
        self.txt_cover_desc_en.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        self.preview_frame = ttk.LabelFrame(self.right_pane, text="视频预览", padding=10)
        self.lbl_preview_video_name = ttk.Label(
            self.preview_frame,
            text="—",
            wraplength=480,
            foreground="gray",
        )
        self.lbl_preview_video_name.pack(anchor=tk.W, pady=(0, 6))
        self.preview_body = ttk.Frame(self.preview_frame)
        self.preview_body.pack(fill=tk.BOTH, expand=True)
        self.preview_body.columnconfigure(0, weight=0, minsize=213)
        self.preview_body.columnconfigure(1, weight=1)
        self.preview_body.rowconfigure(0, weight=1)

        self._preview_slot_w, self._preview_slot_h = 213, 120
        self.preview_video_canvas = tk.Canvas(
            self.preview_body,
            width=self._preview_slot_w,
            height=self._preview_slot_h,
            highlightthickness=0,
            bd=0,
        )
        self.preview_video_canvas.grid(row=0, column=0, sticky="nw", padx=(0, 10))

        preview_meta = ttk.Frame(self.preview_body)
        preview_meta.grid(row=0, column=1, sticky="nsew")
        preview_meta.columnconfigure(0, weight=1)
        preview_meta.rowconfigure(1, weight=1)

        self.lbl_preview_title_zh = tk.Label(
            preview_meta,
            text="",
            anchor="nw",
            justify=tk.LEFT,
            wraplength=320,
            font=("", 11, "bold"),
        )
        self.lbl_preview_title_zh.grid(row=0, column=0, sticky="new")

        self.txt_preview_desc_zh = tk.Text(
            preview_meta,
            height=6,
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=0,
            state=tk.DISABLED,
            font=("", 10),
        )
        self.txt_preview_desc_zh.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        sec_log = ttk.LabelFrame(self.right_pane, text="日志", padding=8)
        self.log_text = tk.Text(sec_log, height=14, wrap=tk.WORD, state=tk.DISABLED)
        scroll = ttk.Scrollbar(sec_log, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.right_pane.add(self.cover_frame, weight=1)
        self.right_pane.add(self.preview_frame, weight=1)
        self.right_pane.add(sec_log, weight=1)
        self.right_pane.bind("<Configure>", self._on_right_pane_configure)

        self._cover_img = None
        self._preview_img = None
        self._right_pane_resize_after_id: str | None = None
        self._right_pane_last_h = 0
        self._equalize_retry_count = 0
        self.after_idle(self._equalize_right_pane_once)
        self.after_idle(self._init_preview_panel)
        self.after_idle(self._restore_audio_library_selections)

        self.left_notebook.bind("<<NotebookTabChanged>>", self._on_left_tab_changed)

        self.after_idle(self._update_left_scrollbar_visibility)
        self.after_idle(self._restore_last_video_deferred)
        self.after_idle(self._log_startup_info)

        last_material = self._cfg.get("last_material_dir")
        if last_material:
            p = Path(last_material)
            if p.is_dir():
                self.material_dir = p
        self._apply_theme(self._theme_mode)

    def _log_startup_info(self) -> None:
        if is_wsl():
            self._log("WSL 环境：打开/渲染工程将调用 Windows 版 Reaper")
        elif is_mac():
            self._log("macOS 环境：使用本机 Reaper；素材默认挂载于 /Volumes/192.168.3.128/…")
        self._log(f"仓库根目录：{LIB_REPO_ROOT}")
        self._log(f"素材 baseURL：{base_url()}")

    def _restore_last_video_deferred(self) -> None:
        last_video = self._cfg.get("last_video")
        if not last_video:
            return
        p = Path(last_video)
        if not p.is_file():
            return
        self._set_video(p, from_import=False, defer_heavy=True)

    def _setup_workflow_scroll(self, parent: ttk.Frame) -> None:
        """工作流左侧：内容不足时不显示滚动条；小屏溢出时显示。"""
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self._left_scroll_canvas = tk.Canvas(container, highlightthickness=0, borderwidth=0)
        self._left_scroll_vbar = ttk.Scrollbar(
            container, orient=tk.VERTICAL, command=self._left_scroll_canvas.yview
        )
        self._left_scroll_canvas.configure(yscrollcommand=self._on_left_scroll_yview)
        self._left_scroll_canvas.grid(row=0, column=0, sticky="nsew")
        self._left_scroll_vbar.grid(row=0, column=1, sticky="ns")
        self._left_scroll_vbar.grid_remove()

        self.left_content = ttk.Frame(self._left_scroll_canvas, padding=10)
        self._left_scroll_window = self._left_scroll_canvas.create_window(
            (0, 0), window=self.left_content, anchor=tk.NW
        )

        self.left_content.bind("<Configure>", self._on_left_content_configure)
        self._left_scroll_canvas.bind("<Configure>", self._on_left_scroll_canvas_configure)
        self._left_scroll_canvas.bind("<Enter>", self._bind_left_scroll_wheel)
        self._left_scroll_canvas.bind("<Leave>", self._unbind_left_scroll_wheel)
        self.left_content.bind("<Enter>", self._bind_left_scroll_wheel)
        self.left_content.bind("<Leave>", self._unbind_left_scroll_wheel)

    def _on_left_scroll_yview(self, first: str, last: str) -> None:
        self._left_scroll_vbar.set(first, last)
        self._update_left_scrollbar_visibility()

    def _on_left_content_configure(self, _event=None) -> None:
        self._left_scroll_canvas.configure(scrollregion=self._left_scroll_canvas.bbox("all"))
        self._update_left_scrollbar_visibility()

    def _on_left_scroll_canvas_configure(self, event=None) -> None:
        if event is not None:
            self._left_scroll_canvas.itemconfigure(
                self._left_scroll_window, width=event.width
            )
        self._update_left_scrollbar_visibility()

    def _update_left_scrollbar_visibility(self) -> None:
        if not hasattr(self, "_left_scroll_canvas"):
            return
        canvas = self._left_scroll_canvas
        vbar = self._left_scroll_vbar
        canvas.update_idletasks()
        bbox = canvas.bbox("all")
        if not bbox:
            vbar.grid_remove()
            return
        content_h = bbox[3] - bbox[1]
        view_h = canvas.winfo_height()
        # 内容能完整放下时不显示滚动条（大屏 / 窗口较高时通常如此）
        if content_h > view_h + 2:
            vbar.grid()
        else:
            vbar.grid_remove()
            canvas.yview_moveto(0)

    def _bind_left_scroll_wheel(self, _event=None) -> None:
        if not self._left_scroll_vbar.winfo_ismapped():
            return
        self._left_scroll_canvas.bind_all("<MouseWheel>", self._on_left_scroll_wheel)
        self._left_scroll_canvas.bind_all("<Button-4>", self._on_left_scroll_wheel)
        self._left_scroll_canvas.bind_all("<Button-5>", self._on_left_scroll_wheel)

    def _unbind_left_scroll_wheel(self, _event=None) -> None:
        self._left_scroll_canvas.unbind_all("<MouseWheel>")
        self._left_scroll_canvas.unbind_all("<Button-4>")
        self._left_scroll_canvas.unbind_all("<Button-5>")

    def _on_left_scroll_wheel(self, event) -> None:
        if not self._left_scroll_vbar.winfo_ismapped():
            return
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            delta = -1 * (event.delta // 120) if event.delta else 0
        if delta:
            self._left_scroll_canvas.yview_scroll(delta, "units")

    def _uploaded_ids_cfg(self) -> dict:
        ids = self._cfg.get("uploaded_ids")
        if not isinstance(ids, dict):
            ids = {}
            self._cfg["uploaded_ids"] = ids
        return ids

    def _is_video_uploaded(self, scene_num: str) -> bool:
        from gui.upload_status import is_uploaded_cfg_entry

        return is_uploaded_cfg_entry(self._uploaded_ids_cfg().get(str(scene_num)))

    def _upload_entry_mp4(self, scene_num: str) -> Path | None:
        from gui.upload_status import mp4_path_from_upload_entry

        raw = mp4_path_from_upload_entry(self._uploaded_ids_cfg().get(str(scene_num)))
        if not raw:
            return None
        p = Path(raw)
        return p.resolve() if p.is_file() else None

    def _resolve_uploaded_mp4_path(
        self,
        scene_num: str,
        *,
        current: Path | None = None,
    ) -> Path | None:
        saved = self._upload_entry_mp4(scene_num)
        if saved:
            return saved
        if current and current.is_file():
            return current.resolve()
        for sid, data in self._export_outputs_cfg().items():
            if self._scene_num(sid) != str(scene_num) or not isinstance(data, dict):
                continue
            raw = data.get("mp4")
            if not raw:
                continue
            p = Path(raw)
            if p.is_file():
                return p.resolve()
        return None

    def _maybe_upgrade_uploaded_entry(self, scene_num: str) -> None:
        """将 uploaded_ids 中 legacy ``true`` 升级为带 mp4 路径的对象。"""
        ids = self._uploaded_ids_cfg()
        key = str(scene_num)
        if ids.get(key) is not True:
            return
        mp4 = self._resolve_uploaded_mp4_path(key, current=self._resolve_upload_mp4())
        if mp4:
            ids[key] = {"mp4": str(mp4)}
            self._save_config()

    def _set_video_uploaded(
        self,
        scene_num: str,
        uploaded: bool,
        *,
        mp4: Path | None = None,
        url: str | None = None,
    ) -> None:
        ids = self._uploaded_ids_cfg()
        key = str(scene_num)
        if uploaded:
            entry: dict[str, str] | bool = True
            resolved = mp4 if mp4 and mp4.is_file() else None
            if resolved is None:
                resolved = self._resolve_uploaded_mp4_path(key, current=self._resolve_upload_mp4())
            if resolved:
                entry = {"mp4": str(resolved.resolve())}
                if url:
                    entry["url"] = url
            ids[key] = entry
        else:
            ids.pop(key, None)
        self._save_config()
        if hasattr(self, "lbl_upload"):
            self._refresh_upload_label()

    def _mark_scene_uploaded(
        self,
        scene_id: str | None = None,
        *,
        mp4: Path | None = None,
        url: str | None = None,
    ) -> None:
        sid = scene_id or self.scene_id
        if not sid:
            return
        num = get_scene_number(sid)
        self._set_video_uploaded(num, True, mp4=mp4, url=url)
        if hasattr(self, "video_library_tab"):
            self.video_library_tab.mark_uploaded(num, True)

    def _audio_library_selection_cfg(self) -> dict:
        sel = self._cfg.get("audio_library_selection")
        if not isinstance(sel, dict):
            sel = {}
            self._cfg["audio_library_selection"] = sel
        return sel

    def _save_audio_library_selection(self, track_id: str, paths: list[Path]) -> None:
        cfg = self._audio_library_selection_cfg()
        cfg[track_id] = [str(p) for p in paths]
        self._save_config()

    def _track_picker_selection_cfg(self) -> dict:
        sel = self._cfg.get("track_picker_selection")
        if not isinstance(sel, dict):
            sel = {}
            self._cfg["track_picker_selection"] = sel
        return sel

    def _save_track_picker_selection(self, track_key: str, path: Path | None) -> None:
        cfg = self._track_picker_selection_cfg()
        if path and path.is_file():
            cfg[track_key] = str(path.resolve())
        else:
            cfg.pop(track_key, None)
        self._save_config()

    def _picker_by_track_name(self, track_name: str):
        for picker in self.track_pickers.values():
            if picker.track_name == track_name:
                return picker
        return None

    def _apply_saved_track_picker_selection(self, track_key: str, picker) -> bool:
        raw = self._track_picker_selection_cfg().get(track_key)
        if not raw:
            return False
        p = Path(raw)
        if not p.is_file():
            return False
        if hasattr(picker, "select_wav"):
            return picker.select_wav(p, notify=False)
        return False

    def _prepare_scatter_pickers_for_project(self) -> None:
        """生成工程前：素材库 → 步骤 2 同步，并恢复上次点选。"""
        from gui.core_controller import SCATTER_LAYER_IDS

        for tid in SCATTER_LAYER_IDS:
            tab = self._audio_library_tabs.get(tid)
            if tab:
                self._sync_track_picker_from_library(tid, tab.get_selected())

    def _restore_audio_library_selections(self) -> None:
        cfg = self._audio_library_selection_cfg()
        for track_id, tab in self._audio_library_tabs.items():
            raw = cfg.get(track_id, [])
            if not isinstance(raw, list):
                continue
            paths = [Path(p) for p in raw if p and Path(p).is_file()]
            if paths:
                tab.set_selected(paths, notify=False)
                self._sync_track_picker_from_library(track_id, paths)

    def _ensure_rain_boom_tab(self):
        from gui.track_picker_ui import TrackPickerUI

        boom = self.track_pickers.get("1_rain_boom")
        if not boom:
            frame = ttk.Frame(self.pickers_notebook, padding=6)
            boom = TrackPickerUI(frame, track_name="1_rain_boom", log_fn=self._log)
            boom.on_select_callback = self._on_grid_select
            boom.pack()
            self.track_pickers["1_rain_boom"] = boom
        else:
            frame = boom.master

        target_idx = 0
        try:
            current_idx = self.pickers_notebook.index(frame)
        except tk.TclError:
            current_idx = -1

        if current_idx < 0:
            self.pickers_notebook.insert(target_idx, frame, text="1_rain_boom")
        elif current_idx != target_idx:
            self.pickers_notebook.insert(target_idx, frame)

        return boom

    def _select_rain_boom_tab(self) -> None:
        boom = self.track_pickers.get("1_rain_boom")
        if not boom:
            return
        try:
            self.pickers_notebook.select(boom.master)
        except tk.TclError:
            pass

    def _sync_track_picker_from_library(self, track_id: str, wavs: list[Path]) -> None:
        from gui.core_controller import SCATTER_LAYER_IDS

        if track_id == "1_rain_boom":
            self._ensure_rain_boom_tab()
        picker = self.track_pickers.get(track_id)
        if not picker:
            return
        cands = [
            {"wav": str(w), "name": wav_display_title(w), "score": 100}
            for w in wavs[:9]
        ]
        if not cands:
            picker.set_candidates([])
            picker.clear_selection()
            return
        picker.set_candidates(cands)
        if track_id == "1_rain_boom":
            picker.set_title(
                f"rain boom 已选 {len(cands)} 个" if cands else "rain boom 素材库未选"
            )
        else:
            picker.set_title(f"素材库已选 {len(cands)} 个")

        if self._apply_saved_track_picker_selection(track_id, picker):
            pass

    def _on_audio_library_selection(self, track_id: str, wavs: list[Path]) -> None:
        self._save_audio_library_selection(track_id, wavs)
        self._sync_track_picker_from_library(track_id, wavs)

    def _on_left_tab_changed(self, _event=None) -> None:
        self._unbind_left_scroll_wheel()
        if hasattr(self, "mix_preview_grid"):
            self.mix_preview_grid.stop_playback()
        for tab in self._audio_library_tabs.values():
            tab.stop_playback()
        try:
            tab = self.left_notebook.nametowidget(self.left_notebook.select())
        except tk.TclError:
            return
        if tab is self.video_library_tab:
            self.video_library_tab.on_tab_selected()
        elif tab in self._audio_library_tabs.values():
            tab.on_tab_selected()
        elif tab is self.workflow_tab:
            self.after_idle(self._update_left_scrollbar_visibility)

    def _subproject_rpp_path(self, scene_id: str | None = None) -> Path | None:
        sid = scene_id or self.scene_id
        if not sid:
            return None
        rpp = get_scene_rpp_path(sid)
        return rpp if rpp.is_file() else None

    def _set_rpp(self, rpp: Path) -> None:
        self.rpp_path = rpp.resolve()
        self._cfg["last_rpp"] = str(self.rpp_path)
        self._save_config()

    def _pane_thumb_size(self, frame: ttk.LabelFrame) -> tuple[int, int]:
        """LabelFrame 内左栏固定 16:9 占位尺寸。"""
        frame.update_idletasks()
        frame_h = frame.winfo_height()
        if frame_h > 1:
            # LabelFrame 标题 + 上方视频文件名标签预留
            h = max(frame_h - 48, 100)
            return max(int(h * 16 / 9), 160), h
        _, cell_h = self._preview_cell_size()
        h = max(cell_h, 120)
        return max(int(h * 16 / 9), 160), h

    def _cover_thumb_size(self) -> tuple[int, int]:
        if hasattr(self, "cover_frame"):
            return self._pane_thumb_size(self.cover_frame)
        _, cell_h = self._preview_cell_size()
        h = max(cell_h, 120)
        return max(int(h * 16 / 9), 160), h

    def _preview_thumb_size(self) -> tuple[int, int]:
        if hasattr(self, "preview_frame"):
            return self._pane_thumb_size(self.preview_frame)
        return self._cover_thumb_size()

    def _apply_cover_slot_geometry(self, slot_w: int, slot_h: int) -> None:
        if (
            getattr(self, "_cover_slot_w", None) == slot_w
            and getattr(self, "_cover_slot_h", None) == slot_h
        ):
            return
        self._cover_slot_w = slot_w
        self._cover_slot_h = slot_h
        if hasattr(self, "cover_thumb_canvas"):
            self.cover_thumb_canvas.configure(width=slot_w, height=slot_h)
        if hasattr(self, "cover_body"):
            self.cover_body.columnconfigure(0, minsize=slot_w)

    def _apply_preview_slot_geometry(self, slot_w: int, slot_h: int) -> None:
        if (
            getattr(self, "_preview_slot_w", None) == slot_w
            and getattr(self, "_preview_slot_h", None) == slot_h
        ):
            return
        self._preview_slot_w = slot_w
        self._preview_slot_h = slot_h
        if hasattr(self, "preview_video_canvas"):
            self.preview_video_canvas.configure(width=slot_w, height=slot_h)
        if hasattr(self, "preview_body"):
            self.preview_body.columnconfigure(0, minsize=slot_w)

    def _show_preview_placeholder(self, text: str) -> None:
        if not hasattr(self, "preview_video_canvas"):
            return
        slot_w, slot_h = self._preview_thumb_size()
        self._apply_preview_slot_geometry(slot_w, slot_h)
        self.preview_video_canvas.delete("all")
        self.preview_video_canvas.create_text(
            slot_w // 2,
            slot_h // 2,
            text=text,
            anchor=tk.CENTER,
            width=max(slot_w - 8, 80),
        )

    def _preview_cell_size(self) -> tuple[int, int]:
        """右侧每个预览格的最大缩略图尺寸（约 1/3 高度）。"""
        if not hasattr(self, "right_pane"):
            return (480, 160)
        self.right_pane.update_idletasks()
        w = max(self.right_pane.winfo_width() - 32, 160)
        h = max(self.right_pane.winfo_height() // 3 - 44, 72)
        return (w, h)

    def _equalize_right_pane_once(self, _event=None) -> None:
        """启动时均分右侧三区；不在用户拖动窗口时反复强制 sashpos。"""
        if not hasattr(self, "right_pane"):
            return
        self.right_pane.update_idletasks()
        h = self.right_pane.winfo_height()
        if h <= 2:
            if self._equalize_retry_count < 20:
                self._equalize_retry_count += 1
                self.after(50, self._equalize_right_pane_once)
            return
        third = max(h // 3, 80)
        try:
            self.right_pane.sashpos(0, third)
            self.right_pane.sashpos(1, 2 * third)
        except tk.TclError:
            pass
        self._right_pane_last_h = h

    def _on_right_pane_configure(self, _event=None) -> None:
        """窗口缩放时防抖刷新预览布局，避免 Configure → sashpos → Configure 死循环。"""
        if self._right_pane_resize_after_id:
            self.after_cancel(self._right_pane_resize_after_id)
        self._right_pane_resize_after_id = self.after(180, self._on_right_pane_resize_settled)

    def _on_right_pane_resize_settled(self) -> None:
        self._right_pane_resize_after_id = None
        if not hasattr(self, "right_pane"):
            return
        h = self.right_pane.winfo_height()
        if abs(h - self._right_pane_last_h) < 6:
            return
        self._right_pane_last_h = h
        self._refresh_preview_layout()
        self._update_cover_preview()

    def _init_preview_panel(self) -> None:
        if not self.video_path or not self.video_path.is_file():
            self._show_preview_placeholder("无预览")
        self._update_preview_metadata()

    def _log(self, msg: str) -> None:
        if msg.startswith("PROGRESS ") or (
            msg.startswith("Elapsed:") and "Remaining:" in msg
        ):
            return

        def append() -> None:
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        schedule_on_main(self, append)

    def _export_outputs_cfg(self) -> dict:
        out = self._cfg.get("export_outputs")
        if not isinstance(out, dict):
            out = {}
            self._cfg["export_outputs"] = out
        return out

    def _save_scene_export_path(self, scene_id: str, kind: str, path: Path) -> None:
        resolved = path.resolve()
        outputs = self._export_outputs_cfg()
        scene = outputs.setdefault(scene_id, {})
        if not isinstance(scene, dict):
            scene = {}
            outputs[scene_id] = scene
        scene[kind] = str(resolved)
        if kind == "wav":
            self.last_export_wav = resolved
        elif kind == "mp4":
            self.last_export_mp4 = resolved
            self._cfg["last_export_mp4"] = str(resolved)
        self._save_config()

    def _get_scene_export_path(self, scene_id: str, kind: str) -> Path | None:
        outputs = self._cfg.get("export_outputs", {})
        if isinstance(outputs, dict):
            scene = outputs.get(scene_id, {})
            if isinstance(scene, dict):
                raw = scene.get(kind)
                if raw:
                    p = Path(raw)
                    if p.is_file():
                        if kind == "mp4" and not export_mp4_belongs_to_scene(
                            p, scene_id, hours=self._target_duration_hours()
                        ):
                            return None
                        return p.resolve()
        return None

    def _target_duration_hours(self) -> float:
        try:
            return self._parse_duration_hours()
        except ValueError:
            raw = self._cfg.get("duration_hours", self._cfg.get("target_duration", 3))
            try:
                return float(raw)
            except (TypeError, ValueError):
                return 3.0

    def _resolve_valid_export_mp4(
        self, scene_id: str, hours: float | None = None
    ) -> Path | None:
        """仅当 export 下存在同序号、时长符合目标的成片 MP4 时视为有效。"""
        h = self._target_duration_hours() if hours is None else float(hours)
        saved = self._get_scene_export_path(scene_id, "mp4")
        if saved and export_mp4_belongs_to_scene(saved, scene_id, hours=h):
            if wav_matches_target_hours(saved, h):
                return saved.resolve()
        latest = find_export_mp4_for_scene(scene_id, hours=h)
        if latest and wav_matches_target_hours(latest, h):
            return latest.resolve()
        return None

    def _confirm_overwrite(self, title: str, message: str) -> bool:
        return messagebox.askyesno(title, message, icon="warning")

    def _resolve_valid_export_wav(
        self, scene_id: str, hours: float | None = None
    ) -> Path | None:
        """仅当 WAV 实际时长接近目标成片时长时视为有效成品。"""
        h = self._target_duration_hours() if hours is None else float(hours)
        expected = expected_export_wav_path(scene_id, h)
        if wav_matches_target_hours(expected, h):
            return expected.resolve()

        saved = self._get_scene_export_path(scene_id, "wav")
        if saved and wav_matches_target_hours(saved, h):
            return saved.resolve()
        return None

    def _format_export_wav_status(
        self, path: Path | None, hours: float | None = None
    ) -> str:
        if not path or not path.is_file():
            return "待开始"
        h = self._target_duration_hours() if hours is None else float(hours)
        if not wav_matches_target_hours(path, h):
            return "待开始"
        return self._format_export_status(path)

    def _clear_invalid_export_wav(self, scene_id: str, hours: float | None = None) -> None:
        h = self._target_duration_hours() if hours is None else float(hours)
        outputs = self._export_outputs_cfg()
        scene = outputs.get(scene_id)
        if not isinstance(scene, dict):
            return
        raw = scene.get("wav")
        if not raw:
            return
        p = Path(raw)
        if not p.is_file() or not wav_matches_target_hours(p, h):
            scene.pop("wav", None)
            self._save_config()

    def _scene_num(self, scene_id: str) -> str:
        import re
        match = re.search(r"\d+", scene_id)
        return match.group() if match else scene_id

    def _find_latest_wav_for_scene(self, scene_id: str) -> Path | None:
        num = self._scene_num(scene_id)
        candidates: list[Path] = []
        for d in (export_dir(), LIB_REPO_ROOT / "Reaper" / "Projects" / "Rain"):
            if d.is_dir():
                candidates.extend(d.glob(f"*{num}*.wav"))
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _clear_invalid_export_mp4(self, scene_id: str, hours: float | None = None) -> None:
        h = self._target_duration_hours() if hours is None else float(hours)
        outputs = self._export_outputs_cfg()
        scene = outputs.get(scene_id)
        if not isinstance(scene, dict):
            return
        raw = scene.get("mp4")
        if not raw:
            return
        p = Path(raw)
        if (
            not p.is_file()
            or not export_mp4_belongs_to_scene(p, scene_id, hours=h)
            or not wav_matches_target_hours(p, h)
        ):
            scene.pop("mp4", None)
            if self._cfg.get("last_export_mp4") == raw:
                self._cfg["last_export_mp4"] = ""
            self._save_config()

    def _find_latest_mp4_for_scene(self, scene_id: str) -> Path | None:
        return find_export_mp4_for_scene(scene_id, hours=self._target_duration_hours())

    def _default_upload_mp4(self) -> Path | None:
        """步骤 5 默认上传：baseURL/export 下与步骤 1 同序号的成片 mp4。"""
        if not self.scene_id:
            return None
        return self._resolve_valid_export_mp4(self.scene_id)

    def _resolve_upload_mp4(self) -> Path | None:
        if self.upload_mp4_custom and self.upload_mp4_custom.is_file():
            return self.upload_mp4_custom.resolve()
        return self._default_upload_mp4()

    def _format_media_rel_path(self, path: Path) -> str:
        from gui.upload_status import format_media_rel_path

        return format_media_rel_path(path, export_root=export_dir(), base_root=base_url())

    def _format_upload_label(self, mp4: Path | None) -> str:
        from gui.upload_status import format_step5_upload_label

        if not mp4 or not mp4.is_file():
            return "待上传：—"
        try:
            scene_num = get_scene_number(derive_scene_id(mp4))
        except ValueError:
            scene_num = None
        custom = bool(
            self.upload_mp4_custom
            and mp4.resolve() == self.upload_mp4_custom.resolve()
        )
        if scene_num and self._is_video_uploaded(scene_num):
            self._maybe_upgrade_uploaded_entry(scene_num)
            display = self._resolve_uploaded_mp4_path(scene_num, current=mp4) or mp4
            return format_step5_upload_label(
                uploaded=True,
                rel_path=self._format_media_rel_path(display),
                custom=custom,
            )
        return format_step5_upload_label(
            uploaded=False,
            rel_path=self._format_media_rel_path(mp4),
            custom=custom,
        )

    def _refresh_upload_label(self) -> None:
        if hasattr(self, "lbl_upload"):
            self.lbl_upload.configure(text=self._format_upload_label(self._resolve_upload_mp4()))

    def _format_transfer_progress(self, elapsed: float, pct: int) -> str:
        from gui.upload_progress import format_transfer_progress

        return format_transfer_progress(elapsed, pct)

    def _make_upload_progress_updater(
        self,
    ) -> tuple[Callable[[int], None], Callable[[], None]]:
        """上传进度：主线程定时刷新 Elapsed/Remaining，后台线程仅更新百分比。"""
        return make_elapsed_ticker(
            self,
            lambda text: self.lbl_upload.configure(text=text),
            format_status=self._format_transfer_progress,
        )

    def _pick_upload_mp4(self) -> None:
        exp = export_dir()
        initial = str(exp) if exp.is_dir() else self._video_dialog_initialdir()
        path = filedialog.askopenfilename(
            title="选择 export 目录下的上传视频",
            initialdir=initial,
            filetypes=[("MP4 视频", "*.mp4"), ("所有文件", "*.*")],
        )
        if not path:
            return
        picked = Path(path).resolve()
        if exp.is_dir():
            try:
                picked.relative_to(exp.resolve())
            except ValueError:
                messagebox.showwarning("提示", f"请选择 export 目录下的 MP4：\n{exp}")
                return
        self.upload_mp4_custom = picked
        self._refresh_upload_label()
        self._log(f"上传视频（自定义）：{picked}")

    def _reset_upload_mp4_default(self) -> None:
        self.upload_mp4_custom = None
        self._refresh_upload_label()
        self._log("上传视频已恢复为 export 默认同序号成片")

    def _find_loop_video_for_scene(self, scene_id: str) -> Path | None:
        if self.video_path and self.scene_id == scene_id and self.video_path.is_file():
            return self.video_path
        num = self._scene_num(scene_id)
        bu = base_url()
        if not bu.is_dir():
            return None
        candidates = sorted(bu.glob(f"MVI_{num}*.mp4"), key=lambda p: p.name.lower())
        candidates += sorted(bu.glob(f"mvi_{num}*.mp4"), key=lambda p: p.name.lower())
        if not candidates:
            candidates = sorted(bu.glob(f"*{num}*loop*.mp4"), key=lambda p: p.name.lower())
        return candidates[0] if candidates else None

    def _loop_video_for_upload(self, scene_id: str) -> Path | None:
        """上传前自动补全物料/封面：在 baseURL 根目录按同序号查找 loop MP4。"""
        return self._find_loop_video_for_scene(scene_id)

    def _generate_cover_via_analyze(
        self,
        loop_video: Path,
        scene_id: str,
        *,
        force_refresh: bool = False,
    ) -> Path:
        analyze_script = LIB_REPO_ROOT / "scripts" / "video_analysis" / "analyze.py"
        vst_mod = load_module(analyze_script, "relaxasmr_video_analyze")
        ensure_base_url_dirs()
        ensure_rain_fx_png()
        out_dir = base_material_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        vst_mod.analyze_video(
            loop_video,
            out_dir,
            on_progress=self._log,
            force_refresh=force_refresh,
            skip_clip=True,
        )
        return get_thumbnail_path(scene_id)

    def _ensure_thumbnail_for_upload(self, scene_id: str) -> Path:
        thumb = get_thumbnail_path(scene_id)
        if thumb.is_file():
            return thumb

        loop_video = self._loop_video_for_upload(scene_id)
        if not loop_video:
            raise FileNotFoundError("NO_LOOP_VIDEO")

        self._log(f"封面不存在，自动执行分析生成：{thumb.name}")
        self._log(f"baseURL loop：{loop_video.name}")
        self._generate_cover_via_analyze(loop_video, scene_id, force_refresh=False)
        if not thumb.is_file():
            self._generate_cover_via_analyze(loop_video, scene_id, force_refresh=True)
        if not thumb.is_file():
            raise FileNotFoundError(f"分析完成但仍未找到封面：{thumb.name}")

        schedule_on_main(self, self._update_cover_preview)
        return thumb

    def _run_material_analysis_blocking(
        self,
        loop_video: Path,
        scene_id: str,
        *,
        force_refresh: bool = False,
    ) -> None:
        """阻塞式生成物料（供上传前自动补全；逻辑同「开始分析」）。"""
        from gui.core_controller import (
            clip_analysis_from_matches,
            load_cached_rain_tabs,
            reconcile_clip_vlm,
            save_clip_matches,
        )

        analyze_script = LIB_REPO_ROOT / "scripts" / "video_analysis" / "analyze.py"
        vst_mod = load_module(analyze_script, "relaxasmr_video_analyze")

        ensure_base_url_dirs()
        ensure_rain_fx_png()
        out_dir = base_material_dir()
        out_dir.mkdir(parents=True, exist_ok=True)

        from scripts.config.paths import clear_scene_material, get_snapshot_raw_path

        if force_refresh:
            clear_scene_material(scene_id, on_progress=self._log)
            cached = None
        else:
            cached = load_cached_rain_tabs(scene_id)

        clip_analysis: dict = {}
        frame_jpg = get_snapshot_raw_path(scene_id)

        skip_clip_vlm = cached is not None and not cached.get("partial")

        if skip_clip_vlm:
            self._log("CLIP/VLM 已存在，跳过解析。")
            clip_analysis = clip_analysis_from_matches(Path(cached["clip_json"]))
        elif cached and cached.get("partial"):
            self._log("CLIP 已存在，跳过 CLIP；继续 VLM…")
            clip_analysis = clip_analysis_from_matches(Path(cached["clip_json"]))
            vst_mod.analyze_video(
                loop_video, out_dir, on_progress=self._log, force_refresh=False, skip_clip=True
            )
            frame_jpg = get_snapshot_raw_path(scene_id)
        else:
            clip_data = vst_mod.analyze_video(
                loop_video,
                out_dir,
                on_progress=self._log,
                force_refresh=force_refresh,
                skip_clip=False,
            )
            clip_analysis = clip_data.get("clip_analysis", {})
            frame_jpg = Path(clip_data["frame_jpg"]) if clip_data.get("frame_jpg") else frame_jpg
            save_clip_matches(scene_id, clip_analysis, vlm_reconciled=False, log_fn=self._log)

        if not skip_clip_vlm and frame_jpg and frame_jpg.is_file():
            from scripts.video_analysis.analyze import analyze_vlm_frame

            vlm_res = analyze_vlm_frame(frame_jpg, on_progress=self._log)
            reconcile_clip_vlm(scene_id, clip_analysis, vlm_res, self._log)

        existing = material_metadata_path(scene_id)
        if existing and not force_refresh:
            self._log(f"物料已存在，跳过: {existing.name}")
        else:
            yt_mod = load_module(YT_MATERIAL_SCRIPT, "relaxasmr_generate_youtube_material")
            yt_mod.generate_material(
                loop_video,
                output_dir=out_dir,
                preset_key=clip_analysis.get("l2", {}).get("key", "forest_rain"),
                copy_style="forest_rain",
                thumb_title=RAIN_THUMB_TITLE,
                thumb_subtitle_place_only=True,
                duration_override_s=float(self.duration_var.get()) * 3600,
                scene_id=scene_id,
                force_refresh_visual=force_refresh,
                on_progress=self._log,
            )

        thumb = get_thumbnail_path(scene_id)
        if not thumb.is_file():
            self._log(f"封面缺失，补生成: {thumb.name}")
            self._generate_cover_via_analyze(loop_video, scene_id, force_refresh=False)
            if not thumb.is_file():
                self._generate_cover_via_analyze(loop_video, scene_id, force_refresh=True)

    def _ensure_material_for_upload(self, scene_id: str) -> Path:
        existing = material_metadata_path(scene_id)
        if existing:
            return existing
        loop_video = self._loop_video_for_upload(scene_id)
        if not loop_video:
            raise FileNotFoundError("NO_LOOP_VIDEO")
        self._log(f"物料不存在，自动执行「开始分析」：{scene_id}")
        self._log(f"baseURL loop：{loop_video.name}")
        self._run_material_analysis_blocking(loop_video, scene_id, force_refresh=False)
        existing = material_metadata_path(scene_id)
        if not existing:
            raise FileNotFoundError(
                f"分析完成但仍未找到物料：{material_json_path(scene_id).name}"
            )
        return existing

    def _format_export_status(self, path: Path | None) -> str:
        if not path or not path.is_file():
            return "待开始"
        try:
            rel = path.relative_to(export_dir())
            base = f"已完成 · export/{rel}"
        except ValueError:
            try:
                rel = path.relative_to(base_url())
                base = f"已完成 · {rel}"
            except ValueError:
                base = f"已完成 · {path.name}"
        return base + format_mp4_export_stats_suffix(path)

    def _format_export_mp4_status(
        self,
        path: Path | None,
        *,
        scene_id: str | None = None,
        hours: float | None = None,
    ) -> str:
        if not path or not path.is_file():
            return "待开始"
        sid = scene_id or self.scene_id
        h = self._target_duration_hours() if hours is None else float(hours)
        if not sid or not export_mp4_belongs_to_scene(path, sid, hours=h):
            return "待开始"
        if not wav_matches_target_hours(path, h):
            return "待开始"
        return self._format_export_status(path)

    def _refresh_step4_outputs(self, scene_id: str | None = None) -> None:
        sid = scene_id or self.scene_id
        if not sid:
            self.last_export_wav = None
            self.last_export_mp4 = None
            self._set_render_ui(running=False, status="待开始", wav_path=None)
            self._set_export_ui(running=False, status="待开始")
            if hasattr(self, "lbl_upload"):
                self.lbl_upload.configure(text="待上传：—")
            return

        wav = self._resolve_valid_export_wav(sid)
        self._clear_invalid_export_wav(sid)
        self._clear_invalid_export_mp4(sid)
        mp4 = self._resolve_valid_export_mp4(sid)
        if wav:
            self._save_scene_export_path(sid, "wav", wav)
        else:
            self.last_export_wav = None
        if mp4:
            self._save_scene_export_path(sid, "mp4", mp4)
        else:
            self.last_export_mp4 = None
            if self._cfg.get("last_export_mp4"):
                self._cfg["last_export_mp4"] = ""

        self._set_render_ui(
            running=False,
            status=self._format_export_wav_status(wav),
            wav_path=wav,
        )
        self._set_export_ui(
            running=False,
            status=self._format_export_mp4_status(mp4, scene_id=sid),
        )
        self._refresh_upload_label()
        self._save_config()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        if hasattr(self, "btn_gen_project"):
            self.btn_gen_project.configure(state=state)
        if hasattr(self, 'btn_analyze'): self.btn_analyze.configure(state=state)
        if hasattr(self, 'btn_upload'): self.btn_upload.configure(state=state)
        if hasattr(self, 'btn_export') and not getattr(self, "_export_running", False):
            self.btn_export.configure(state=state)
        if hasattr(self, 'btn_render_reaper') and not getattr(self, "_render_running", False):
            self.btn_render_reaper.configure(state=state)

    def _set_render_ui(
        self,
        *,
        running: bool,
        status: str | None = None,
        wav_path: Path | None = None,
    ) -> None:
        self._render_running = running
        self.btn_render_reaper.configure(state=tk.DISABLED if running else tk.NORMAL)
        if status is not None and hasattr(self, "mix_preview_grid"):
            self.mix_preview_grid.set_status(
                status,
                wav_path=wav_path,
                running=running,
            )

    def _set_export_ui(self, *, running: bool, status: str | None = None) -> None:
        self._export_running = running
        self.btn_export.configure(state=tk.DISABLED if running else tk.NORMAL)
        if status is not None:
            self.lbl_export.configure(text=status)

    def _refresh_material_label(self) -> None:
        if self.material_dir and self.material_dir.is_dir():
            try:
                rel = self.material_dir.relative_to(LIB_REPO_ROOT)
            except ValueError:
                rel = self.material_dir
            pass #(text=f"物料：{rel}/")
            return
        if self.scene_id:
            found = find_material_dir(self.scene_id, LIB_REPO_ROOT)
            if found:
                self.material_dir = found
                try:
                    rel = found.relative_to(LIB_REPO_ROOT)
                except ValueError:
                    rel = found
                pass #(text=f"物料：{rel}/")
                return
        pass #(text="物料：—")

    def _on_grid_select(self, track_name: str) -> None:
        """1_rain_clip / 1_rain_vlm / 1_rain_boom 互斥（一致时为 1_rain）。"""
        from gui.core_controller import is_rain_loop_exclusive_track_name

        if is_rain_loop_exclusive_track_name(track_name):
            for picker in self.track_pickers.values():
                other = picker.track_name
                if other != track_name and is_rain_loop_exclusive_track_name(other):
                    picker.clear_selection()
                    self._save_track_picker_selection(other, None)

        picker = self._picker_by_track_name(track_name)
        if picker:
            self._save_track_picker_selection(track_name, picker.get_selected())

    def _add_picker_tab(self, track_name: str, matches: list[dict], out_dir: Path) -> TrackPickerUI:
        """Helper to add new track picker tabs."""
        from gui.track_picker_ui import TrackPickerUI
        frame = ttk.Frame(self.pickers_notebook, padding=6)
        self.pickers_notebook.add(frame, text=track_name)
        picker = TrackPickerUI(frame, track_name=track_name, log_fn=self._log)
        picker.on_select_callback = self._on_grid_select
        picker.pack()
        self.track_pickers[track_name] = picker
        picker.load_candidates_from_data(matches, out_dir)
        return picker

    def _remove_vlm_tab(self) -> None:
        vlm_picker = self.track_pickers.get("1_rain_vlm")
        if not vlm_picker:
            return
        self.pickers_notebook.forget(vlm_picker.master)
        vlm_picker.master.destroy()
        del self.track_pickers["1_rain_vlm"]

    def _ensure_vlm_tab(self, after_picker) -> "TrackPickerUI":
        from gui.track_picker_ui import TrackPickerUI

        vlm_picker = self.track_pickers.get("1_rain_vlm")
        if vlm_picker:
            return vlm_picker
        frame = ttk.Frame(self.pickers_notebook, padding=6)
        idx = self.pickers_notebook.index(after_picker.master)
        self.pickers_notebook.insert(idx + 1, frame, text="1_rain_vlm")
        vlm_picker = TrackPickerUI(frame, track_name="1_rain_vlm", log_fn=self._log)
        vlm_picker.on_select_callback = self._on_grid_select
        vlm_picker.pack()
        self.track_pickers["1_rain_vlm"] = vlm_picker
        return vlm_picker

    def _apply_rain_tabs(self, result: dict) -> None:
        """根据 CLIP/VLM  reconcile 结果更新 1_rain 选项卡。"""
        picker1 = self.track_pickers.get("1_rain")
        if not picker1:
            return

        rain_tab = result["rain_tab"]
        self.pickers_notebook.tab(picker1.master, text=rain_tab)
        picker1.track_name = rain_tab
        picker1.on_select_callback = self._on_grid_select
        picker1.set_title(result["clip_title"])
        picker1.load_candidates(result["clip_json"])
        self._apply_saved_track_picker_selection(picker1.track_name, picker1)

        if result.get("show_vlm_tab") and result.get("vlm_json"):
            vlm_picker = self._ensure_vlm_tab(picker1)
            vlm_picker.set_title(result["vlm_title"])
            vlm_picker.load_candidates(result["vlm_json"])
            self._apply_saved_track_picker_selection(vlm_picker.track_name, vlm_picker)
        else:
            self._remove_vlm_tab()

        self._ensure_rain_boom_tab()
        boom_tab = self._audio_library_tabs.get("1_rain_boom")
        if boom_tab:
            self._sync_track_picker_from_library("1_rain_boom", boom_tab.get_selected())
        self._select_rain_boom_tab()

    def _generate_loop_material(self, loop_video: Path, sub_dir: Path, scene: str, duration_hours: float) -> Path:
        """根据 loop 视频生成 YouTube 物料（缩略图 + *_material.json）。"""
        yt_mod = load_module(YT_MATERIAL_SCRIPT, "relaxasmr_generate_youtube_material")
        out_dir = loop_material_dir(sub_dir, loop_video)
        out_dir.parent.mkdir(parents=True, exist_ok=True)
        self._log("—— 生成 YouTube 物料（基于 loop 视频）——")
        return yt_mod.generate_material(
            loop_video,
            output_dir=out_dir,
            preset_key=scene,
            copy_style="forest_rain",
            thumb_title=RAIN_THUMB_TITLE,
            thumb_subtitle_place_only=True,
            duration_override_s=duration_hours * 3600,
            scene_id=scene,
            on_progress=self._log,
        )

    def _video_resolution_label(self, video: Path) -> str:
        from gui.video_library_tab import read_video_quality

        quality = read_video_quality(video)
        return f"  {quality}" if quality else ""

    def _format_video_label(self, scene: str, video: Path, *, include_resolution: bool = True) -> str:
        suffix = self._video_resolution_label(video) if include_resolution else ""
        return f"[{scene}] {video}{suffix}"

    def _set_video(self, video: Path, *, from_import: bool, defer_heavy: bool = False) -> None:
        try:
            scene = derive_scene_id(video)
        except ValueError as exc:
            messagebox.showerror("导入失败", str(exc))
            return

        self.video_path = video
        self.video_rel = str(video)
        prev_scene = self.scene_id
        self.scene_id = scene
        if prev_scene != scene:
            self.upload_mp4_custom = None
        self._update_preview_video_names(video)
        self.lbl_video.configure(
            text=self._format_video_label(scene, video, include_resolution=not defer_heavy)
        )
        # self.lbl_scene.configure(text=f"场景 ID：{scene}")
        self._cfg["last_video"] = str(video)
        self._cfg["last_video_dir"] = str(video.parent)
        self._save_config()
        if from_import:
            self._log(f"已选定视频：{video}")

        import re
        stem = video.stem
        match = re.search(r'\d+', stem)
        num = match.group() if match else stem

        # 1. 自动关联 Reaper 工程（Rain/<scene>.rpp）
        rpp = self._subproject_rpp_path(scene)
        if rpp:
            self._set_rpp(rpp)
        else:
            self.rpp_path = None
            
        # 2. 自动关联物料（baseURL/material/）
        out_dir = base_material_dir()
        if out_dir.is_dir():
            material_md = out_dir / f"{scene}_material.md"
            if material_md.is_file():
                self.material_dir = out_dir
            else:
                self.material_dir = out_dir
        else:
            self.material_dir = None
        self._refresh_material_label()

        if defer_heavy:
            self.after(80, self._finish_set_video_heavy)
            return

        self._finish_set_video_heavy(from_import=from_import)

    def _finish_set_video_heavy(self, from_import: bool = False) -> None:
        if not self.video_path or not self.scene_id:
            return
        scene = self.scene_id
        video = self.video_path

        def apply_resolution_label(quality: str) -> None:
            if self.video_path != video or self.scene_id != scene:
                return
            suffix = f"  {quality}" if quality else ""
            self.lbl_video.configure(text=f"[{scene}] {video}{suffix}")

        def load_resolution() -> None:
            from gui.video_library_tab import read_video_quality

            quality = read_video_quality(video)
            schedule_on_main(self, lambda q=quality: apply_resolution_label(q))

        threading.Thread(target=load_resolution, daemon=True).start()

        # 3. 恢复步骤 4 上次成功的混音 / 合成路径
        self._refresh_step4_outputs(scene)

        self._save_config()
        self._update_cover_preview()
        self._update_preview(video)
        out_dir = base_material_dir()
        self._load_existing_analysis(out_dir, scene)

    def _material_dir_for_video(self) -> Path:
        return base_material_dir()

    def _cover_path(self) -> Path | None:
        if not self.scene_id:
            return None
        path = get_thumbnail_path(self.scene_id)
        return path if path.is_file() else None

    def _load_material_meta_fields(self) -> tuple[str, str, str, str]:
        title_en = desc_en = title_zh = desc_zh = ""
        if self.scene_id:
            from scripts.video_upload.material_store import load_material_metadata

            meta_path = material_metadata_path(self.scene_id)
            if meta_path:
                try:
                    meta = load_material_metadata(meta_path)
                    title_en = (meta.get("title_en") or "").strip()
                    desc_en = (meta.get("description_en") or "").strip()
                    title_zh = (meta.get("title_zh") or "").strip()
                    desc_zh = (meta.get("description_zh") or "").strip()
                except Exception as exc:
                    title_en = f"物料读取失败: {exc}"
        return title_en, desc_en, title_zh, desc_zh

    def _update_preview_video_names(self, video: Path | None = None) -> None:
        """封面/视频预览上方显示对应视频文件名（非物料标题）。"""
        name = video.name if video and video.name else "—"
        if hasattr(self, "lbl_cover_video_name"):
            self.lbl_cover_video_name.configure(text=name)
        if hasattr(self, "lbl_preview_video_name"):
            self.lbl_preview_video_name.configure(text=name)

    def _update_cover_metadata(self) -> None:
        if not hasattr(self, "lbl_cover_title_en"):
            return
        title_en, desc_en, _, _ = self._load_material_meta_fields()
        wrap = max(
            getattr(self, "cover_body", self).winfo_width() - getattr(self, "_cover_slot_w", 213) - 24,
            160,
        )
        self.lbl_cover_title_en.configure(
            text=title_en or "（无 English Title）",
            wraplength=wrap,
        )
        self.txt_cover_desc_en.configure(state=tk.NORMAL)
        self.txt_cover_desc_en.delete("1.0", tk.END)
        self.txt_cover_desc_en.insert("1.0", desc_en or "（无 English Description）")
        self.txt_cover_desc_en.configure(state=tk.DISABLED)
        self._update_preview_metadata()

    def _update_preview_metadata(self) -> None:
        if not hasattr(self, "lbl_preview_title_zh"):
            return
        _, _, title_zh, desc_zh = self._load_material_meta_fields()
        wrap = max(
            getattr(self, "preview_body", self).winfo_width() - getattr(self, "_preview_slot_w", 213) - 24,
            160,
        )
        self.lbl_preview_title_zh.configure(
            text=title_zh or "（无中文标题）",
            wraplength=wrap,
        )
        self.txt_preview_desc_zh.configure(state=tk.NORMAL)
        self.txt_preview_desc_zh.delete("1.0", tk.END)
        self.txt_preview_desc_zh.insert("1.0", desc_zh or "（无中文说明）")
        self.txt_preview_desc_zh.configure(state=tk.DISABLED)

    def _update_cover_preview(self) -> None:
        if not hasattr(self, "cover_thumb_canvas"):
            return
        self._update_preview_video_names(self.video_path)
        slot_w, slot_h = self._cover_thumb_size()
        self._apply_cover_slot_geometry(slot_w, slot_h)
        self.cover_thumb_canvas.delete("all")

        path = self._cover_path()
        if not path:
            self.cover_thumb_canvas.create_text(
                slot_w // 2,
                slot_h // 2,
                text="无预览",
                anchor=tk.CENTER,
            )
            self._cover_img = None
            self._update_cover_metadata()
            return
        try:
            img = Image.open(path)
            img.thumbnail((slot_w, slot_h), Image.Resampling.LANCZOS)
            self._cover_img = ImageTk.PhotoImage(img)
            self.cover_thumb_canvas.create_image(
                slot_w // 2,
                slot_h // 2,
                anchor=tk.CENTER,
                image=self._cover_img,
            )
        except Exception as exc:
            self.cover_thumb_canvas.create_text(
                slot_w // 2,
                slot_h // 2,
                text=f"封面加载失败: {exc}",
                anchor=tk.CENTER,
                width=slot_w - 8,
            )
            self._cover_img = None
        self._update_cover_metadata()

    def _load_existing_analysis(self, out_dir: Path | None, scene_id: str) -> None:
        from gui.core_controller import load_cached_rain_tabs

        mat = out_dir if out_dir else base_material_dir()
        if not mat.is_dir():
            self._update_cover_preview()
            return

        self.material_dir = mat

        picker1 = getattr(self, "track_pickers", {}).get("1_rain")
        if not picker1:
            return

        cached = load_cached_rain_tabs(scene_id)
        if cached:
            self._log(f"找到之前的分析结果: {Path(cached['clip_json']).name}")
            self._apply_rain_tabs(cached)
        else:
            picker1.lbl_status.configure(text="未找到数据文件")
            picker1._clear_grid()
            self._remove_vlm_tab()
            self.pickers_notebook.tab(picker1.master, text="1_rain")
            picker1.track_name = "1_rain"
            self._ensure_rain_boom_tab()
            boom_tab = self._audio_library_tabs.get("1_rain_boom")
            if boom_tab:
                self._sync_track_picker_from_library("1_rain_boom", boom_tab.get_selected())
            self._select_rain_boom_tab()

        self._update_cover_preview()

    def _stop_video_loop(self):
        if self._video_loop_id is not None:
            self.after_cancel(self._video_loop_id)
            self._video_loop_id = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _refresh_preview_layout(self) -> None:
        if self._cap is None:
            if not self.video_path or not self.video_path.is_file():
                self._show_preview_placeholder("无预览")
            self._update_preview_metadata()
            return
        slot_w, slot_h = self._preview_thumb_size()
        self._apply_preview_slot_geometry(slot_w, slot_h)

    def _update_preview(self, video_path: Path | None) -> None:
        if not hasattr(self, "preview_video_canvas"):
            return

        self._stop_video_loop()
        self._update_preview_video_names(video_path)

        if not video_path or not video_path.is_file():
            self._preview_img = None
            self._show_preview_placeholder("无预览")
            self._update_preview_metadata()
            return

        self._show_preview_placeholder("加载视频预览中...")
        self._update_preview_metadata()

        def copy_and_play() -> None:
            try:
                import tempfile
                tmp_path = os.path.join(tempfile.gettempdir(), "relaxasmr_preview.mp4")
                shutil.copy2(video_path, tmp_path)
                self.after(0, lambda: self._start_video_loop(tmp_path))
            except Exception as exc:
                self.after(0, lambda: self._show_preview_placeholder(f"视频复制失败: {exc}"))

        threading.Thread(target=copy_and_play, daemon=True).start()

    def _start_video_loop(self, tmp_path: str):
        import cv2

        self._cap = cv2.VideoCapture(tmp_path)
        if not self._cap.isOpened():
            self._show_preview_placeholder("无法打开临时视频文件进行循环播放")
            return

        self._play_next_frame()

    def _play_next_frame(self):
        if self._cap is None:
            return

        import cv2

        ret, frame = self._cap.read()
        if not ret:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._cap.read()

        if ret:
            try:
                slot_w, slot_h = self._preview_thumb_size()
                self._apply_preview_slot_geometry(slot_w, slot_h)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                img.thumbnail((slot_w, slot_h), Image.Resampling.LANCZOS)
                self._preview_img = ImageTk.PhotoImage(img)
                self.preview_video_canvas.delete("all")
                self.preview_video_canvas.create_image(
                    slot_w // 2,
                    slot_h // 2,
                    anchor=tk.CENTER,
                    image=self._preview_img,
                )
            except Exception:
                pass

        self._video_loop_id = self.after(33, self._play_next_frame)

    def _video_dialog_initialdir(self) -> str:
        saved = self._cfg.get("last_video_dir")
        if saved and Path(saved).is_dir():
            return saved
        bu = base_url()
        if bu.is_dir():
            return str(bu)
        return str(LIB_REPO_ROOT)

    def _import_video(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 Loop 视频",
            initialdir=self._video_dialog_initialdir(),
            filetypes=[("MP4 视频", "*.mp4"), ("所有文件", "*.*")],
        )
        if path:
            picked = Path(path)
            self._cfg["last_video_dir"] = str(picked.parent)
            self._save_config()
            self._set_video(picked, from_import=True)

    def _select_video_from_library(self, video: Path) -> None:
        """素材库双击：等同步骤 1「选择 MP4」。"""
        if not video.is_file():
            messagebox.showerror("导入失败", f"视频不存在：{video}")
            return
        self._cfg["last_video_dir"] = str(video.parent)
        self._save_config()
        self._set_video(video, from_import=True)
        self.left_notebook.select(self.workflow_tab)

    def _start_analysis(self) -> None:
        if self._busy:
            return
        if not self.video_path:
            from tkinter import messagebox
            messagebox.showwarning("提示", "请先导入 loop 视频。")
            return
            
        loop_video = self.video_path
        force_refresh = self.chk_overwrite_mat_var.get()
        self._set_busy(True)
        self._log("—— 开始执行分析与物料生成 ——")

        def worker(*, force_refresh: bool = force_refresh) -> None:
            try:
                import threading
                import shutil
                from gui.app import LIB_REPO_ROOT, load_module, load_scripts_module, YT_MATERIAL_SCRIPT, RAIN_THUMB_TITLE
                
                analyze_script = LIB_REPO_ROOT / "scripts" / "video_analysis" / "analyze.py"
                vst_mod = load_module(analyze_script, "relaxasmr_video_analyze")
                
                scene_id = self.scene_id or getattr(self, 'derive_scene_id', lambda x: x.stem)(loop_video)
                import re
                match = re.search(r'\d+', scene_id)
                num = match.group() if match else scene_id
                
                ensure_base_url_dirs()
                ensure_rain_fx_png()

                self._log("—— 1. 准备物料目录 ——")
                out_dir = base_material_dir()
                out_dir.mkdir(parents=True, exist_ok=True)
                
                self._log("—— 2. 自动分析画面 ——")
                from gui.core_controller import (
                    clip_analysis_from_matches,
                    load_cached_rain_tabs,
                    reconcile_clip_vlm,
                    save_clip_matches,
                )
                from scripts.config.paths import clear_scene_material, get_snapshot_raw_path, material_metadata_path

                if force_refresh:
                    self._log("勾选「覆盖物料」：清除旧 snapshot / 封面 / CLIP / VLM / visual_scene / md…")
                    clear_scene_material(scene_id, on_progress=self._log)
                    cached = None
                else:
                    cached = load_cached_rain_tabs(scene_id)

                clip_analysis: dict = {}
                frame_jpg: Path | None = get_snapshot_raw_path(scene_id)
                skip_clip_vlm = cached is not None and not cached.get("partial")
                rain_tab_result: dict | None = None

                if skip_clip_vlm:
                    self._log("CLIP/VLM 已存在，跳过解析，直接加载。")

                    def load_cached_ui() -> None:
                        self.material_dir = out_dir
                        self._refresh_material_label()
                        self._update_cover_preview()
                        self._apply_rain_tabs(cached)
                        self._log("步骤 2 九宫格已从缓存加载。")

                    self.after(0, load_cached_ui)
                    clip_analysis = clip_analysis_from_matches(Path(cached["clip_json"]))
                elif cached and cached.get("partial"):
                    self._log("CLIP 已存在，跳过 CLIP；继续 VLM…")
                    clip_json = Path(cached["clip_json"])
                    clip_analysis = clip_analysis_from_matches(clip_json)

                    vst_mod.analyze_video(
                        loop_video,
                        out_dir,
                        on_progress=self._log,
                        force_refresh=False,
                        skip_clip=True,
                    )
                    frame_jpg = get_snapshot_raw_path(scene_id)

                    def load_partial_clip_ui() -> None:
                        self.material_dir = out_dir
                        self._refresh_material_label()
                        self._update_cover_preview()
                        self._apply_rain_tabs(cached)
                        self._log("CLIP 阶段已从缓存加载。")

                    self.after(0, load_partial_clip_ui)
                else:
                    clip_data = vst_mod.analyze_video(
                        loop_video,
                        out_dir,
                        on_progress=self._log,
                        force_refresh=force_refresh,
                        skip_clip=False,
                    )
                    clip_analysis = clip_data.get("clip_analysis", {})
                    frame_jpg = Path(clip_data["frame_jpg"]) if clip_data.get("frame_jpg") else frame_jpg

                    clip_json, clip_title, clip_matches = save_clip_matches(
                        scene_id, clip_analysis, vlm_reconciled=False, log_fn=self._log
                    )
                    rain_tab_result = {
                        "rain_tab": "1_rain_clip",
                        "clip_json": clip_json,
                        "clip_title": clip_title,
                        "show_vlm_tab": False,
                        "vlm_json": None,
                        "vlm_title": "",
                    }

                    def update_clip_ui() -> None:
                        self.material_dir = out_dir
                        self._refresh_material_label()
                        self._update_cover_preview()
                        self._apply_rain_tabs(rain_tab_result)
                        if clip_matches:
                            self._log("CLIP 阶段结束，九宫格已就绪。")
                        else:
                            self._log("CLIP 阶段结束。")

                    self.after(0, update_clip_ui)

                if skip_clip_vlm:
                    pass
                elif frame_jpg and frame_jpg.is_file():
                    from scripts.video_analysis.analyze import analyze_vlm_frame

                    vlm_res = analyze_vlm_frame(frame_jpg, on_progress=self._log)
                    rain_tab_result = reconcile_clip_vlm(
                        scene_id, clip_analysis, vlm_res, self._log
                    )

                    def update_vlm_ui() -> None:
                        self._apply_rain_tabs(rain_tab_result)

                    self.after(0, update_vlm_ui)
                elif not skip_clip_vlm:
                    self._log("未找到首帧图片，跳过 VLM 分析。")

                clip_data = {"clip_analysis": clip_analysis}

                self._log("—— 3. 生成 YouTube 物料 ——")
                existing = material_metadata_path(scene_id)
                if existing and not force_refresh:
                    self._log(f"物料已存在，跳过: {existing.name}")
                else:
                    yt_mod = load_module(YT_MATERIAL_SCRIPT, "relaxasmr_generate_youtube_material")
                    yt_mod.generate_material(
                        loop_video,
                        output_dir=out_dir,
                        preset_key=clip_data.get("clip_analysis", {}).get("l2", {}).get("key", "forest_rain"),
                        copy_style="forest_rain",
                        thumb_title=RAIN_THUMB_TITLE,
                        thumb_subtitle_place_only=True,
                        duration_override_s=float(self.duration_var.get()) * 3600,
                        scene_id=scene_id,
                        force_refresh_visual=force_refresh,
                        on_progress=self._log,
                    )
                    self.after(0, self._update_cover_preview)
            except Exception as exc:
                def done_err(err: BaseException = exc) -> None:
                    self._log(f"错误：{err}")
                    from tkinter import messagebox
                    messagebox.showerror("分析失败", str(err))
                self.after(0, done_err)
            finally:
                self.after(0, lambda: self._set_busy(False))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _create_project(self) -> None:
        if self._busy:
            return
        if not self.video_path:
            from tkinter import messagebox
            messagebox.showwarning("提示", "请先导入 loop 视频。")
            return
            
        try:
            duration = self._parse_duration_hours()
        except ValueError as exc:
            from tkinter import messagebox
            messagebox.showerror("参数错误", str(exc))
            return

        self._persist_duration_hours(duration)
        from gui.core_controller import collect_selected_tracks_for_reaper

        self._prepare_scatter_pickers_for_project()
        selected_tracks = collect_selected_tracks_for_reaper(
            self.track_pickers if hasattr(self, "track_pickers") else {},
            log_fn=self._log,
        )

        loop_video = self.video_path
        scene_id = self.scene_id or derive_scene_id(loop_video)
        rpp_path = get_scene_rpp_path(scene_id)
        if self.chk_overwrite_rpp_var.get() and rpp_path.is_file():
            if not self._confirm_overwrite(
                "确认覆盖 Reaper 工程",
                f"将覆盖已有工程文件：\n{rpp_path}\n\n是否继续？",
            ):
                return

        self._set_busy(True)
        self._log("—— 开始生成子工程 ——")

        def worker() -> None:
            try:
                from gui.app import LIB_REPO_ROOT, load_module
                gen_sub_script = LIB_REPO_ROOT / "Reaper" / "scripts" / "generate_subproject.py"
                gen_sub = load_module(gen_sub_script, "generate_subproject")

                scene_id = self.scene_id or getattr(self, 'derive_scene_id', lambda x: x.stem)(loop_video)
                self._log("—— 3. 新建 Reaper 工程 ——")

                rain_dir = get_subproject_dir(scene_id)
                rpp_path = get_scene_rpp_path(scene_id)

                if rpp_path.exists() and not self.chk_overwrite_rpp_var.get():
                    self._log(f"已存在 {rpp_path.name} 且未勾选覆盖，跳过生成。")
                    self.after(0, lambda: self._set_rpp(rpp_path))
                    self.after(0, lambda: messagebox.showinfo("跳过", "工程已存在，跳过覆盖。"))
                    return

                cfg = build_scene_config_from_gui(
                    loop_video,
                    scene_id=scene_id,
                    duration_hours=duration,
                    selected_tracks=selected_tracks,
                    log_fn=self._log,
                )

                ensure_shared_scripts()
                gen_sub.stage_rain_fx_assets(rain_dir)
                rpp_path.write_text(
                    gen_sub.build_rpp(cfg, LIB_REPO_ROOT, rain_dir, "auto"),
                    encoding="utf-8",
                )

                self._log(f"Reaper 工程已生成：{rpp_path.name}")

                def done_ok() -> None:
                    self._set_rpp(rpp_path)
                    from tkinter import messagebox
                    messagebox.showinfo("完成", f"工程已生成：{rpp_path.name}")
                self.after(0, done_ok)
            except Exception as exc:
                def done_err(err: BaseException = exc) -> None:
                    self._log(f"错误：{err}")
                    from tkinter import messagebox
                    messagebox.showerror("工程生成失败", str(err))
                    import traceback
                    traceback.print_exc()
                self.after(0, done_err)
            finally:
                self.after(0, lambda: self._set_busy(False))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _render_headless(self) -> None:
        if not self.scene_id:
            messagebox.showwarning("提示", "未找到当前场景 ID！")
            return

        rpp_path = self._subproject_rpp_path()
        if not rpp_path:
            messagebox.showwarning("提示", "未找到生成的 RPP 工程文件，请先生成！")
            return

        try:
            duration = self._parse_duration_hours()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        self._persist_duration_hours(duration)
        wav_name = export_wav_name(self.scene_id, duration)
        wav_path = export_dir() / wav_name
        existing_wav = self._resolve_valid_export_wav(self.scene_id, duration)
        if existing_wav:
            if not self._confirm_overwrite(
                "确认覆盖混音",
                f"已存在合格混音（约 {duration:g}h）：\n{existing_wav}\n\n重新输出将覆盖该文件。是否继续？",
            ):
                return
        elif wav_path.is_file():
            actual = wav_duration_seconds(wav_path)
            hint = format_duration_short(actual) if actual is not None else "未知"
            self._log(
                f"将覆盖不合格成品: {wav_name}（当前约 {hint}，目标 {duration:g}h）"
            )
        self._set_render_ui(running=True, status="Elapsed: 00:00:00  Remaining: …")
        self._log(f"—— 开始输出混音: {wav_name} ——")

        render_tail = {"value": False}

        def format_render_status(elapsed: float, pct: int) -> str:
            return format_job_progress(elapsed, pct, tail=render_tail["value"])

        set_render_pct, stop_render_progress = make_elapsed_ticker(
            self,
            lambda text: self._set_render_ui(running=True, status=text),
            format_status=format_render_status,
        )

        def worker() -> None:
            try:
                exe = (self._cfg.get("reaper_exe") or "").strip() or None
                self._log(f"渲染工程: {rpp_path.name}（Entire Project · {duration:g}h）")

                def on_pct(pct: int) -> None:
                    set_render_pct(pct)

                def on_tail(tail: bool) -> None:
                    render_tail["value"] = tail

                render_reaper_project(
                    rpp_path,
                    reaper_exe=exe,
                    output_wav=wav_path,
                    duration_hours=duration,
                    on_pct=on_pct,
                    on_tail=on_tail,
                )
                if not wav_path.is_file():
                    raise FileNotFoundError(f"渲染结束但未找到输出文件: {wav_path.name}")
                if not wav_matches_target_hours(wav_path, duration):
                    actual = wav_duration_seconds(wav_path)
                    hint = format_duration_short(actual) if actual is not None else "未知"
                    raise RuntimeError(
                        f"输出时长不符：{wav_path.name} 约 {hint}，期望 {duration:g} 小时"
                    )
                result_wav = wav_path
                self._log(f"混音完成: {result_wav.name}")

                def done_ok() -> None:
                    stop_render_progress()
                    if self.scene_id:
                        self._save_scene_export_path(self.scene_id, "wav", result_wav)
                    self._set_render_ui(
                        running=False,
                        status=self._format_export_wav_status(result_wav, duration),
                        wav_path=result_wav,
                    )
                    messagebox.showinfo("成功", f"{result_wav.name} 渲染完成！")

                schedule_on_main(self, done_ok)
            except Exception as exc:
                def done_err(err: BaseException = exc) -> None:
                    stop_render_progress()
                    self._log(f"渲染失败: {err}")
                    self._set_render_ui(running=False, status="失败")
                    messagebox.showerror("渲染失败", str(err))

                schedule_on_main(self, done_err)

        threading.Thread(target=worker, daemon=True).start()

    def _open_reaper(self) -> None:
        if not self.scene_id:
            messagebox.showwarning("提示", "请先选择场景。")
            return

        rpp = self._subproject_rpp_path()
        if rpp:
            self._set_rpp(rpp)

        if not self.rpp_path or not self.rpp_path.is_file():
            messagebox.showwarning("提示", "请先生成 Reaper 工程。")
            return
        exe = (self._cfg.get("reaper_exe") or "").strip() or None
        try:
            open_reaper_project(self.rpp_path, reaper_exe=exe)
            self._log(f"已打开：{self.rpp_path}")
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def _open_material(self) -> None:
        if not self.scene_id:
            messagebox.showwarning("提示", "请先导入视频并生成子工程。")
            return
        target = self.material_dir
        if not target or not target.is_dir():
            target = find_material_dir(self.scene_id, LIB_REPO_ROOT)
        if not target or not target.is_dir():
            root = base_material_dir()
            messagebox.showwarning(
                "提示",
                f"尚未找到物料目录。\n\n请先「一键分析并生成」，或确认目录存在：\n{root}",
            )
            return
        try:
            open_folder(target)
            self.material_dir = target
            self._refresh_material_label()
            self._log(f"已打开物料目录：{target}")
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))



    def _open_rpp_dir(self) -> None:
        target = LIB_REPO_ROOT / "Reaper" / "Projects" / "Rain"
        try:
            open_folder(target)
            self._log(f"已打开工程目录：{target}")
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def _open_export_dir(self) -> None:
        target = export_dir()
        target.mkdir(parents=True, exist_ok=True)
        try:
            open_folder(target)
            self._log(f"已打开混音目录：{target}")
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def _open_output(self) -> None:
        target = base_material_dir()
        target.mkdir(parents=True, exist_ok=True)
        try:
            open_folder(target)
            self.material_dir = target
            self._refresh_material_label()
            self._log(f"已打开物料目录：{target}")
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def _export_mp4(self) -> None:
        if getattr(self, "_export_running", False):
            return

        if not self.scene_id:
            messagebox.showwarning("提示", "请先选择场景并生成工程。")
            return

        if not self.video_path or not self.video_path.is_file():
            messagebox.showwarning("提示", "未找到原始 loop 视频，请重新选择视频！")
            return
        import re
        match = re.search(r'\d+', self.scene_id)
        num = match.group() if match else self.scene_id

        try:
            duration = self._parse_duration_hours()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        saved_wav = self._resolve_valid_export_wav(self.scene_id, duration)
        if saved_wav:
            audio_file = saved_wav
        else:
            messagebox.showwarning(
                "提示",
                f"未找到时长符合 {duration:g}h 的混音文件。\n"
                f"请先「一键输出混音」生成 {export_wav_name(self.scene_id, duration)}。",
            )
            return

        existing_mp4 = self._resolve_valid_export_mp4(self.scene_id, duration)
        if existing_mp4:
            if not self._confirm_overwrite(
                "确认覆盖视频",
                f"已存在合格成片（约 {duration:g}h）：\n{existing_mp4}\n\n重新合成将覆盖该文件。是否继续？",
            ):
                return

        vid_file = self.video_path

        script = LIB_REPO_ROOT / "scripts" / "video_export" / "export_mp4.sh"
        import sys

        def _line_buffered_bash(script_path: str, args: list[str]) -> list[str]:
            cmd = ["bash", script_path, *args]
            if shutil.which("stdbuf"):
                cmd = ["stdbuf", "-oL", "-eL", *cmd]
            return cmd

        encoder = "auto" if sys.platform == "darwin" else "nvenc"
        export_args = ["--encoder", encoder]
        if sys.platform == "win32":
            def to_wsl(p: Path) -> str:
                s = str(p).replace("\\", "/")
                if s.startswith("//wsl.localhost/Ubuntu"):
                    return s.replace("//wsl.localhost/Ubuntu", "")
                if s.startswith("//wsl$/Ubuntu"):
                    return s.replace("//wsl$/Ubuntu", "")
                if ":" in s:
                    d, r = s.split(":", 1)
                    return f"/mnt/{d.lower()}{r}"
                return s

            cmd = [
                "wsl",
                *_line_buffered_bash(
                    to_wsl(script),
                    ["-v", to_wsl(vid_file), "-a", to_wsl(audio_file), *export_args],
                ),
            ]
        else:
            cmd = _line_buffered_bash(
                str(script),
                ["-v", str(vid_file.resolve()), "-a", str(audio_file.resolve()), *export_args],
            )

        self._set_export_ui(running=True, status="Elapsed: 00:00:00  Remaining: …")
        self._log("—— 开始合成视频 (export_mp4) ——")
        self._log(f"音频：{audio_file.name}")
        self._log(f"视频：{vid_file.name}")

        export_tail = {"value": False}

        def format_export_status(elapsed: float, pct: int) -> str:
            return format_job_progress(
                elapsed,
                pct,
                tail=export_tail["value"] or pct >= 99,
            )

        set_export_pct, stop_export_progress = make_elapsed_ticker(
            self,
            lambda text: self._set_export_ui(running=True, status=text),
            format_status=format_export_status,
        )

        def worker() -> None:
            import subprocess
            output_mp4: Path | None = None
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert proc.stdout is not None
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        if proc.poll() is not None:
                            break
                        continue
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("==> Done:"):
                        raw = line.split(":", 1)[1].strip()
                        if raw:
                            output_mp4 = Path(raw)
                    elif line.startswith("PROGRESS "):
                        status = line.removeprefix("PROGRESS ").strip()
                        pct = parse_progress_pct(status)
                        if pct is not None:
                            export_tail["value"] = pct >= 99 or "99%+" in status
                            set_export_pct(pct)
                    else:
                        self._log(line)
                proc.wait()
                if proc.returncode == 0:
                    if (not output_mp4 or not output_mp4.is_file()) and self.scene_id:
                        output_mp4 = self._find_latest_mp4_for_scene(self.scene_id)

                    def done_ok() -> None:
                        stop_export_progress()
                        if output_mp4 and output_mp4.is_file() and self.scene_id:
                            self._save_scene_export_path(self.scene_id, "mp4", output_mp4)
                        self._set_export_ui(
                            running=False,
                            status=self._format_export_status(output_mp4),
                        )
                        self._set_video(self.video_path, from_import=False)
                        messagebox.showinfo(
                            "合成成功",
                            f"长视频已导出：\n{output_mp4}" if output_mp4 else "长视频导出完成！",
                        )
                    schedule_on_main(self, done_ok)
                else:
                    def done_err() -> None:
                        stop_export_progress()
                        self._set_export_ui(running=False, status="失败")
                        messagebox.showerror("合成失败", f"export_mp4.sh 返回错误码 {proc.returncode}")
                    schedule_on_main(self, done_err)
            except Exception as exc:
                def done_err2(err: BaseException = exc) -> None:
                    stop_export_progress()
                    self._set_export_ui(running=False, status="失败")
                    messagebox.showerror("运行失败", str(err))
                schedule_on_main(self, done_err2)

        threading.Thread(target=worker, daemon=True).start()

    def _upload_youtube(self) -> None:
        if self._busy:
            return

        upload_mp4 = self._resolve_upload_mp4()
        if not upload_mp4 or not upload_mp4.is_file():
            messagebox.showwarning(
                "提示",
                "未找到待上传视频。\n请先完成步骤 4 合成 export 成片，或点击「上传自定义视频」选择 export 目录下的 MP4。",
            )
            return

        try:
            upload_scene_id = derive_scene_id(upload_mp4)
        except ValueError as exc:
            messagebox.showerror("无法识别场景", str(exc))
            return

        account = "leo_usa" if self.use_leo_usa_var.get() else "leo"
        privacy = self.privacy_var.get()
        language = self.upload_lang_var.get()
        self._cfg["youtube_privacy"] = privacy
        self._cfg["youtube_language"] = language
        self._cfg["youtube_account"] = account
        self._save_config()

        try:
            up_mod = load_scripts_module("video_upload.youtube_upload")
            creds_path, _, _ = up_mod.resolve_account_paths(account)
        except Exception as exc:
            messagebox.showerror("账号配置错误", str(exc))
            return

        if not creds_path.is_file():
            messagebox.showerror(
                "缺少凭据",
                f"请将 Google OAuth 客户端 JSON 放到：\n{creds_path}\n\n见 scripts/video_upload/README.md",
            )
            return

        needs_autogen = (
            material_metadata_path(upload_scene_id) is None
            or not get_thumbnail_path(upload_scene_id).is_file()
        )
        if needs_autogen and not self._loop_video_for_upload(upload_scene_id):
            num = self._scene_num(upload_scene_id)
            messagebox.showwarning(
                "提示",
                f"未找到 {upload_scene_id} 的物料/封面，且 baseURL 下没有同序号 loop MP4。\n"
                f"请在 baseURL 放置 MVI_{num}*.mp4 后再上传。",
            )
            return

        self._set_busy(True)
        self._upload_running = True
        self._log("—— 开始上传到 YouTube ——")
        self._log(f"账号：{account}")
        self._log(f"场景：{upload_scene_id}")
        self._log(f"视频：{upload_mp4}")
        self._log("首次上传需在浏览器完成 OAuth 授权")
        self.lbl_upload.configure(text=self._format_transfer_progress(0.0, 0))
        on_upload_progress, stop_upload_progress = self._make_upload_progress_updater()

        def worker() -> None:
            try:
                md_path = self._ensure_material_for_upload(upload_scene_id)
                self._ensure_thumbnail_for_upload(upload_scene_id)
                up_mod = load_scripts_module("video_upload.youtube_upload")
                record = up_mod.upload_from_material(
                    md_path,
                    language=language,
                    privacy_status=privacy,
                    account=account,
                    override_video_path=upload_mp4,
                    on_log=self._log,
                    on_progress=on_upload_progress,
                )

                def done_ok() -> None:
                    stop_upload_progress()
                    url = record["url"]
                    self._cfg["last_upload_url"] = url
                    self._mark_scene_uploaded(upload_scene_id, mp4=upload_mp4, url=url)
                    self._refresh_upload_label()
                    messagebox.showinfo("上传完成", f"视频已上传：\n{url}\n\n可见性：{privacy}")

                schedule_on_main(self, done_ok)
            except Exception as exc:
                def done_err(err: BaseException = exc) -> None:
                    stop_upload_progress()
                    self._log(f"错误：{err}")
                    self._refresh_upload_label()
                    if "NO_LOOP_VIDEO" in str(err):
                        num = self._scene_num(upload_scene_id)
                        messagebox.showwarning(
                            "提示",
                            f"baseURL 下未找到 MVI_{num}*.mp4，无法自动生成物料/封面。",
                        )
                    else:
                        messagebox.showerror("上传失败", str(err))

                schedule_on_main(self, done_err)
            finally:
                def clear_upload_busy() -> None:
                    self._upload_running = False
                    self._set_busy(False)

                schedule_on_main(self, clear_upload_busy)

        threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    app = RelaxAsmrApp()
    app.mainloop()


if __name__ == "__main__":
    main()
