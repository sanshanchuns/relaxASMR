"""relaxASMR 工程 GUI（Tkinter）。"""

from __future__ import annotations

import json
import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"  # Suppress TensorFlow warnings

import sys
import threading
import shutil
import cv2
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
REAPER_SCRIPTS = REPO_ROOT / "Reaper" / "scripts"
if str(REAPER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(REAPER_SCRIPTS))

from rain_subproject_lib import (  # noqa: E402
    REPO_ROOT as LIB_REPO_ROOT,
    create_from_video,
    derive_scene_id,
    ensure_video_in_assets,
)
from gui.reaper_launch import (  # noqa: E402
    default_reaper_candidates,
    default_windows_reaper_from_wsl,
    is_wsl,
    open_reaper_project,
    render_reaper_project,
)
from gui.folder_open import open_folder  # noqa: E402
from gui.import_reload import load_module, load_scripts_module  # noqa: E402
from gui.rain_vst_ui import RainVstSection  # noqa: E402
from gui.video_library_tab import VideoLibraryTab  # noqa: E402
from gui.youtube_material import (  # noqa: E402
    RAIN_THUMB_TITLE,
    find_material_dir,
    loop_material_dir,
)
from scripts.paths import (  # noqa: E402
    audio_layer_dir,
    base_url,
    ensure_base_url_dirs,
    ensure_rain_fx_png,
    export_dir,
    export_wav_name,
    get_scene_config_path,
    get_scene_rpp_path,
    get_subproject_dir,
    resolve_scene_config_path,
    get_thumbnail_path,
    get_scene_number,
    material_dir as base_material_dir,
)

CONFIG_PATH = Path(__file__).resolve().parent / "user_config.json"
YT_MATERIAL_SCRIPT = LIB_REPO_ROOT / "scripts" / "video_export" / "generate_youtube_material.py"


class RelaxAsmrApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("relaxASMR · Rain 子工程")
        self.geometry("1600x900")
        self.minsize(720, 520)

        self.video_path: Path | None = None
        self.video_rel: str | None = None
        self.scene_id: str | None = None
        self.subproject_dir: Path | None = None
        self.rpp_path: Path | None = None
        self.material_dir: Path | None = None
        self.custom_video_path: Path | None = None
        self._busy = False
        self._render_running = False
        self._export_running = False
        self.last_export_wav: Path | None = None
        self.last_export_mp4: Path | None = None
        
        self._cap = None
        self._video_loop_id = None
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        self._load_config()
        self._build_ui()

    def _on_closing(self) -> None:
        self._stop_video_loop()
        try:
            if os.path.exists("/tmp/relaxasmr_preview.mp4"):
                os.remove("/tmp/relaxasmr_preview.mp4")
        except Exception:
            pass
        self.destroy()

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

    def _build_ui(self) -> None:
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

        self.video_library_tab = VideoLibraryTab(
            self.left_notebook,
            is_uploaded=self._is_video_uploaded,
            toggle_uploaded=self._set_video_uploaded,
            log_fn=self._log,
        )
        self.left_notebook.add(self.video_library_tab, text="素材库")

        # === 左侧工作流：步骤 1–5 自上而下 ===
        self.left_content = ttk.Frame(self.workflow_tab, padding=10)
        self.left_content.pack(fill=tk.BOTH, expand=True, anchor=tk.N)

        # 1. 导入与分析
        sec1 = ttk.LabelFrame(self.left_content, text="1. 导入与分析", padding=10)
        sec1.pack(fill=tk.X, pady=(0, 10))

        row1 = ttk.Frame(sec1)
        row1.pack(fill=tk.X)
        ttk.Button(row1, text="选择 MP4…", command=self._import_video).pack(side=tk.LEFT)
        self.btn_analyze = ttk.Button(row1, text="开始分析", command=self._start_analysis)
        self.btn_analyze.pack(side=tk.LEFT, padx=(8, 0))
        self.chk_overwrite_mat_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row1, text="覆盖物料", variable=self.chk_overwrite_mat_var).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        row2 = ttk.Frame(sec1)
        row2.pack(fill=tk.X, pady=(8, 0))
        self.lbl_video = ttk.Label(row2, text="未选择", wraplength=400)
        self.lbl_video.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 2. 选择四轨音频
        sec2 = ttk.LabelFrame(self.left_content, text="2. 选择四轨音频 (按画面推荐)", padding=10)
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

        # 3. 新建 Reaper 工程
        sec3 = ttk.LabelFrame(self.left_content, text="3. 新建 Reaper 工程", padding=10)
        sec3.pack(fill=tk.X, pady=(0, 10))

        row_gen = ttk.Frame(sec3)
        row_gen.pack(fill=tk.X)
        ttk.Label(row_gen, text="成片时长(小时)").pack(side=tk.LEFT)

        self.duration_var = tk.StringVar(value=self._cfg.get("target_duration", "3"))
        ttk.Entry(row_gen, textvariable=self.duration_var, width=5).pack(side=tk.LEFT, padx=8)

        self.btn_gen_project = ttk.Button(row_gen, text="生成 / 覆盖 Reaper 子工程", command=self._create_project)
        self.btn_gen_project.pack(side=tk.LEFT, padx=(8, 0))
        
        self.chk_overwrite_rpp_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row_gen, text="覆盖已有 .rpp", variable=self.chk_overwrite_rpp_var).pack(side=tk.LEFT, padx=(8, 0))

        # 4. 导出音频与合成视频
        sec_export = ttk.LabelFrame(self.left_content, text="4. 导出音频与合成视频", padding=10)
        sec_export.pack(fill=tk.X, pady=(0, 10))

        row_open = ttk.Frame(sec_export)
        row_open.pack(fill=tk.X)
        self.btn_open_reaper = ttk.Button(row_open, text="打开 Reaper 工程", command=self._open_reaper)
        self.btn_open_reaper.pack(side=tk.LEFT)
        self.btn_open_output = ttk.Button(row_open, text="打开物料目录", command=self._open_output)
        self.btn_open_output.pack(side=tk.LEFT, padx=(8, 0))

        row_mix = ttk.Frame(sec_export)
        row_mix.pack(fill=tk.X, pady=(10, 0))
        self.btn_render_reaper = ttk.Button(row_mix, text="一键输出混音", command=self._render_headless)
        self.btn_render_reaper.pack(side=tk.LEFT)
        self.lbl_render_progress = ttk.Label(row_mix, text="待开始", wraplength=360)
        self.lbl_render_progress.pack(side=tk.LEFT, padx=(8, 0))

        row_export = ttk.Frame(sec_export)
        row_export.pack(fill=tk.X, pady=(10, 0))
        self.btn_export = ttk.Button(row_export, text="一键合成视频", command=self._export_mp4)
        self.btn_export.pack(side=tk.LEFT)
        self.lbl_export = ttk.Label(row_export, text="待开始", wraplength=360)
        self.lbl_export.pack(side=tk.LEFT, padx=(8, 0))

        # 5. YouTube 一键上传
        sec4 = ttk.LabelFrame(self.left_content, text="5. 一键上传 YouTube", padding=10)
        sec4.pack(fill=tk.X)

        ttk.Frame(self.left_content).pack(fill=tk.BOTH, expand=True)

        row4 = ttk.Frame(sec4)
        row4.pack(fill=tk.X)
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
            side=tk.LEFT, padx=(0, 16)
        )
        self.btn_upload = ttk.Button(row4, text="上传到 YouTube", command=self._upload_youtube)
        self.btn_upload.pack(side=tk.LEFT)

        self.lbl_upload = ttk.Label(sec4, text="待上传：—", wraplength=400)
        self.lbl_upload.pack(anchor=tk.W, pady=(8, 0))
        
        # === 右侧：封面预览 + 视频预览 + 日志（三等分）===
        self.right_pane = ttk.PanedWindow(self.right_frame, orient=tk.VERTICAL)
        self.right_pane.pack(fill=tk.BOTH, expand=True)

        self.cover_frame = ttk.LabelFrame(self.right_pane, text="封面预览", padding=10)
        self.lbl_cover = ttk.Label(self.cover_frame, text="无封面", anchor=tk.CENTER)
        self.lbl_cover.pack(fill=tk.BOTH, expand=True)

        self.preview_frame = ttk.LabelFrame(self.right_pane, text="视频预览", padding=10)
        self.lbl_preview = ttk.Label(self.preview_frame, text="无预览", anchor=tk.CENTER)
        self.lbl_preview.pack(fill=tk.BOTH, expand=True)

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
        self._right_pane_equalize_pending = False
        self.after_idle(self._equalize_right_pane)

        self.left_notebook.bind("<<NotebookTabChanged>>", self._on_left_tab_changed)

        last_video = self._cfg.get("last_video")
        if last_video:
            p = Path(last_video)
            if p.is_file():
                self._set_video(p, from_import=False)

        last_material = self._cfg.get("last_material_dir")
        if last_material:
            p = Path(last_material)
            if p.is_dir():
                self.material_dir = p
        self._refresh_material_label()

        if is_wsl():
            self._log("WSL 环境：打开工程将调用 Windows 版 Reaper（勿用 Linux xdg-open）")
        self._log(f"仓库根目录：{LIB_REPO_ROOT}")
        self._log(f"素材 baseURL：{base_url()}")

    def _uploaded_ids_cfg(self) -> dict:
        ids = self._cfg.get("uploaded_ids")
        if not isinstance(ids, dict):
            ids = {}
            self._cfg["uploaded_ids"] = ids
        return ids

    def _is_video_uploaded(self, scene_num: str) -> bool:
        return bool(self._uploaded_ids_cfg().get(str(scene_num)))

    def _set_video_uploaded(self, scene_num: str, uploaded: bool) -> None:
        ids = self._uploaded_ids_cfg()
        key = str(scene_num)
        if uploaded:
            ids[key] = True
        else:
            ids.pop(key, None)
        self._save_config()

    def _mark_scene_uploaded(self, scene_id: str | None = None) -> None:
        sid = scene_id or self.scene_id
        if not sid:
            return
        num = get_scene_number(sid)
        self._set_video_uploaded(num, True)
        if hasattr(self, "video_library_tab"):
            self.video_library_tab.mark_uploaded(num, True)

    def _on_left_tab_changed(self, _event=None) -> None:
        try:
            tab = self.left_notebook.nametowidget(self.left_notebook.select())
        except tk.TclError:
            return
        if tab is self.video_library_tab:
            self.video_library_tab.on_tab_selected()

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

    def _preview_cell_size(self) -> tuple[int, int]:
        """右侧每个预览格的最大缩略图尺寸（约 1/3 高度）。"""
        if not hasattr(self, "right_pane"):
            return (480, 160)
        self.right_pane.update_idletasks()
        w = max(self.right_pane.winfo_width() - 32, 160)
        h = max(self.right_pane.winfo_height() // 3 - 44, 72)
        return (w, h)

    def _equalize_right_pane(self, _event=None) -> None:
        if not hasattr(self, "right_pane"):
            return
        self.right_pane.update_idletasks()
        h = self.right_pane.winfo_height()
        if h <= 2:
            self.after(50, self._equalize_right_pane)
            return
        third = max(h // 3, 80)
        try:
            self.right_pane.sashpos(0, third)
            self.right_pane.sashpos(1, 2 * third)
        except tk.TclError:
            pass

    def _on_right_pane_configure(self, _event=None) -> None:
        if self._right_pane_equalize_pending:
            return
        self._right_pane_equalize_pending = True

        def _done() -> None:
            self._right_pane_equalize_pending = False
            self._equalize_right_pane()
            if self._cover_path():
                self._update_cover_preview()

        self.after_idle(_done)

    def _log(self, msg: str) -> None:
        def append() -> None:
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.after(0, append)

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
                        return p.resolve()
        if kind == "mp4":
            legacy = self._cfg.get("last_export_mp4")
            if legacy:
                p = Path(legacy)
                if p.is_file():
                    return p.resolve()
        return None

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

    def _find_latest_mp4_for_scene(self, scene_id: str) -> Path | None:
        num = self._scene_num(scene_id)
        candidates: list[Path] = []
        for d in (export_dir(), base_material_dir(), LIB_REPO_ROOT / "Reaper" / "Projects" / "Rain"):
            if d.is_dir():
                candidates.extend(d.glob(f"*{num}*.mp4"))
        loop_name = self.video_path.name if self.video_path else None
        candidates = [p for p in candidates if p.name != loop_name]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _format_export_status(self, path: Path | None) -> str:
        if not path or not path.is_file():
            return "待开始"
        try:
            rel = path.relative_to(export_dir())
            return f"已完成 · export/{rel}"
        except ValueError:
            try:
                rel = path.relative_to(base_url())
                return f"已完成 · {rel}"
            except ValueError:
                return f"已完成 · {path.name}"

    def _refresh_step4_outputs(self, scene_id: str | None = None) -> None:
        sid = scene_id or self.scene_id
        if not sid:
            self.last_export_wav = None
            self.last_export_mp4 = None
            self._set_render_ui(running=False, status="待开始")
            self._set_export_ui(running=False, status="待开始")
            if hasattr(self, "lbl_upload"):
                self.lbl_upload.configure(text="待上传：—")
            return

        wav = self._get_scene_export_path(sid, "wav") or self._find_latest_wav_for_scene(sid)
        mp4 = self._get_scene_export_path(sid, "mp4") or self._find_latest_mp4_for_scene(sid)
        if wav:
            self._save_scene_export_path(sid, "wav", wav)
        else:
            self.last_export_wav = None
        if mp4:
            self._save_scene_export_path(sid, "mp4", mp4)
        else:
            self.last_export_mp4 = None
            self._cfg["last_export_mp4"] = ""

        self._set_render_ui(running=False, status=self._format_export_status(wav))
        self._set_export_ui(running=False, status=self._format_export_status(mp4))
        if hasattr(self, "lbl_upload"):
            self.lbl_upload.configure(text=f"待上传：{mp4}" if mp4 else "待上传：—")
        self._save_config()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        if hasattr(self, 'btn_create_proj'): self.btn_create_proj.configure(state=state)
        if hasattr(self, 'btn_analyze'): self.btn_analyze.configure(state=state)
        if hasattr(self, 'btn_upload'): self.btn_upload.configure(state=state)
        if hasattr(self, 'btn_export') and not getattr(self, "_export_running", False):
            self.btn_export.configure(state=state)
        if hasattr(self, 'btn_render_reaper') and not getattr(self, "_render_running", False):
            self.btn_render_reaper.configure(state=state)

    def _set_render_ui(self, *, running: bool, status: str | None = None) -> None:
        self._render_running = running
        self.btn_render_reaper.configure(state=tk.DISABLED if running else tk.NORMAL)
        if status is not None:
            self.lbl_render_progress.configure(text=status)

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
        """同层 clip/vlm 互斥：选中一个 tab 时清除同层另一个 tab 的选中。"""
        base = track_name.split("_vlm")[0].split("_clip")[0]
        for picker in self.track_pickers.values():
            other = picker.track_name
            other_base = other.split("_vlm")[0].split("_clip")[0]
            if other != track_name and other_base == base:
                picker.clear_selection()

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

        if result.get("show_vlm_tab") and result.get("vlm_json"):
            vlm_picker = self._ensure_vlm_tab(picker1)
            vlm_picker.set_title(result["vlm_title"])
            vlm_picker.load_candidates(result["vlm_json"])
        else:
            self._remove_vlm_tab()

    def _generate_loop_material(self, loop_video: Path, sub_dir: Path, scene: str, duration_hours: float) -> Path:
        """根据 loop 视频生成 YouTube 物料（缩略图 + youtube.md）。"""
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
            on_progress=self._log,
        )

    def _set_video(self, video: Path, *, from_import: bool) -> None:
        try:
            scene = derive_scene_id(video)
        except ValueError as exc:
            messagebox.showerror("导入失败", str(exc))
            return

        self.video_path = video
        self.video_rel = str(video)
        self.scene_id = scene
        self.lbl_video.configure(text=f"[{scene}] {video}")
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

        # 3. 恢复步骤 4 上次成功的混音 / 合成路径
        self._refresh_step4_outputs(scene)

        self._save_config()
        self._update_cover_preview()
        self._update_preview(self.video_path)
        scene_id = self.scene_id or getattr(self, 'derive_scene_id', lambda x: x.stem)(self.video_path)
        self._load_existing_analysis(out_dir, scene_id)

    def _material_dir_for_video(self) -> Path:
        return base_material_dir()

    def _cover_path(self) -> Path | None:
        if not self.scene_id:
            return None
        path = get_thumbnail_path(self.scene_id)
        return path if path.is_file() else None

    def _update_cover_preview(self) -> None:
        if not hasattr(self, "lbl_cover"):
            return
        path = self._cover_path()
        if not path:
            self.lbl_cover.configure(image="", text="无封面")
            self._cover_img = None
            return
        try:
            img = Image.open(path)
            img.thumbnail(self._preview_cell_size(), Image.Resampling.LANCZOS)
            self._cover_img = ImageTk.PhotoImage(img)
            self.lbl_cover.configure(image=self._cover_img, text="")
        except Exception as exc:
            self.lbl_cover.configure(image="", text=f"封面加载失败: {exc}")
            self._cover_img = None

    def _load_existing_analysis(self, out_dir: Path | None, scene_id: str) -> None:
        from scripts.paths import clip_matches_path, vlm_matches_path

        mat = out_dir if out_dir else base_material_dir()
        if not mat.is_dir():
            self._update_cover_preview()
            return

        self.material_dir = mat

        clip_json_path = clip_matches_path(scene_id)
        vlm_json_path = vlm_matches_path(scene_id)

        picker1 = getattr(self, "track_pickers", {}).get("1_rain")
        if not picker1:
            return

        if clip_json_path.is_file():
            self._log(f"找到之前的分析结果: {clip_json_path.name}")
            if vlm_json_path.is_file():
                self._apply_rain_tabs({
                    "rain_tab": "1_rain_clip",
                    "clip_json": clip_json_path,
                    "clip_title": "",
                    "show_vlm_tab": True,
                    "vlm_json": vlm_json_path,
                    "vlm_title": "",
                })
            else:
                self._apply_rain_tabs({
                    "rain_tab": "1_rain",
                    "clip_json": clip_json_path,
                    "clip_title": "",
                    "show_vlm_tab": False,
                    "vlm_json": None,
                    "vlm_title": "",
                })
        else:
            picker1.lbl_status.configure(text="未找到数据文件")
            picker1._clear_grid()
            self._remove_vlm_tab()
            self.pickers_notebook.tab(picker1.master, text="1_rain")
            picker1.track_name = "1_rain"

        self._update_cover_preview()

    def _stop_video_loop(self):
        if self._video_loop_id is not None:
            self.after_cancel(self._video_loop_id)
            self._video_loop_id = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _update_preview(self, video_path: Path | None) -> None:
        if not hasattr(self, "lbl_preview"):
            return

        self._stop_video_loop()

        if not video_path or not video_path.is_file():
            self.lbl_preview.configure(image="", text="无预览")
            self._preview_img = None
            return

        self.lbl_preview.configure(image="", text="加载视频预览中...")

        def copy_and_play() -> None:
            try:
                import tempfile
                tmp_path = os.path.join(tempfile.gettempdir(), "relaxasmr_preview.mp4")
                shutil.copy2(video_path, tmp_path)
                self.after(0, lambda: self._start_video_loop(tmp_path))
            except Exception as exc:
                self.after(0, lambda: self.lbl_preview.configure(text=f"视频复制失败: {exc}"))

        threading.Thread(target=copy_and_play, daemon=True).start()

    def _start_video_loop(self, tmp_path: str):
        self._cap = cv2.VideoCapture(tmp_path)
        if not self._cap.isOpened():
            self.lbl_preview.configure(text="无法打开临时视频文件进行循环播放")
            return
            
        self.lbl_preview.configure(text="")
        self._play_next_frame()
        
    def _play_next_frame(self):
        if self._cap is None:
            return
            
        ret, frame = self._cap.read()
        if not ret:
            # 循环播放
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._cap.read()
            
        if ret:
            try:
                max_w, max_h = self._preview_cell_size()
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                self._preview_img = ImageTk.PhotoImage(img)
                self.lbl_preview.configure(image=self._preview_img)
            except Exception:
                pass
                
        # 30fps 大致是 33ms 一帧
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

    def _start_analysis(self) -> None:
        if self._busy:
            return
        if not self.video_path:
            from tkinter import messagebox
            messagebox.showwarning("提示", "请先导入 loop 视频。")
            return
            
        loop_video = self.video_path
        self._set_busy(True)
        self._log("—— 开始执行分析与物料生成 ——")

        def worker() -> None:
            try:
                import threading
                import shutil
                from gui.app import LIB_REPO_ROOT, load_module, load_scripts_module, YT_MATERIAL_SCRIPT, RAIN_THUMB_TITLE
                
                rain_vst_script = LIB_REPO_ROOT / "scripts" / "video_analysis" / "analyze.py"
                vst_mod = load_module(rain_vst_script, "relaxasmr_rain_vst_analyze")
                
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
                force_refresh = getattr(self, "chk_overwrite_mat_var", tk.BooleanVar()).get()
                clip_data = vst_mod.analyze_video(
                    loop_video, out_dir, on_progress=self._log, force_refresh=force_refresh
                )

                self._log("—— 3. 生成 YouTube 物料 ——")
                target_md_path = out_dir / f"{scene_id}_material.md"
                if target_md_path.is_file() and not getattr(self, 'chk_overwrite_mat_var', tk.BooleanVar()).get():
                    self._log(f"物料已存在且未勾选覆盖，跳过生成。")
                else:
                    yt_mod = load_module(YT_MATERIAL_SCRIPT, "relaxasmr_generate_youtube_material")
                    yt_mod.generate_material(
                        loop_video, # wait, does generate_material need quadra.jpg? For now it just takes loop_video. We can leave it as is or pass quadra.
                        output_dir=out_dir,
                        preset_key=clip_data.get('clip_analysis', {}).get('l2', {}).get('key', 'forest_rain'), # use space key
                        copy_style="forest_rain",
                        thumb_title=RAIN_THUMB_TITLE,
                        thumb_subtitle_place_only=True,
                        duration_override_s=float(self.duration_var.get()) * 3600,
                        on_progress=self._log,
                    )
                    if (out_dir / "youtube.md").is_file():
                        (out_dir / "youtube.md").rename(target_md_path)
                
                clip_analysis = clip_data.get("clip_analysis", {})
                frame_jpg = clip_data.get("frame_jpg")

                def update_clip_ui() -> None:
                    from gui.core_controller import save_clip_matches

                    self.material_dir = out_dir
                    self._refresh_material_label()
                    self._update_cover_preview()

                    clip_json, clip_title, _ = save_clip_matches(scene_id, clip_analysis)
                    self._apply_rain_tabs({
                        "rain_tab": "1_rain_clip",
                        "clip_json": clip_json,
                        "clip_title": clip_title,
                        "show_vlm_tab": False,
                        "vlm_json": None,
                        "vlm_title": "",
                    })
                    self._log("CLIP 阶段结束，九宫格已就绪。")

                self.after(0, update_clip_ui)

                if frame_jpg and Path(frame_jpg).is_file():
                    from scripts.video_analysis.analyze import analyze_vlm_frame

                    vlm_res = analyze_vlm_frame(Path(frame_jpg), on_progress=self._log)

                    def update_vlm_ui() -> None:
                        from gui.core_controller import reconcile_clip_vlm

                        result = reconcile_clip_vlm(
                            scene_id, clip_analysis, vlm_res, self._log
                        )
                        self._apply_rain_tabs(result)

                    self.after(0, update_vlm_ui)
                else:
                    self._log("未找到首帧图片，跳过 VLM 分析。")
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
            duration = float(self.duration_var.get())
        except ValueError:
            from tkinter import messagebox
            messagebox.showerror("参数错误", "成片时长必须是数字。")
            return
            
        selected_tracks = {}
        if hasattr(self, "track_pickers"):
            for tid, picker in self.track_pickers.items():
                sel = picker.get_selected()
                if sel:
                    # Map 1_rain_clip and 1_rain_vlm to 1_rain
                    actual_tid = "1_rain" if tid in ("1_rain_clip", "1_rain_vlm") else tid
                    selected_tracks[actual_tid] = sel

        loop_video = self.video_path
        self._set_busy(True)
        self._log("—— 开始生成子工程 ——")

        def worker() -> None:
            try:
                from gui.app import LIB_REPO_ROOT, load_module
                gen_sub_script = LIB_REPO_ROOT / "Reaper" / "scripts" / "generate_subproject.py"
                gen_sub = load_module(gen_sub_script, "generate_subproject")
                
                from rain_subproject_lib import ensure_shared_scripts

                scene_id = self.scene_id or getattr(self, 'derive_scene_id', lambda x: x.stem)(loop_video)
                self._log("—— 3. 新建 Reaper 工程 ——")

                rain_dir = get_subproject_dir(scene_id)
                rpp_path = get_scene_rpp_path(scene_id)

                if rpp_path.exists() and not self.chk_overwrite_rpp_var.get():
                    self._log(f"已存在 {rpp_path.name} 且未勾选覆盖，跳过生成。")
                    self.after(0, lambda: self._set_rpp(rpp_path))
                    self.after(0, lambda: messagebox.showinfo("跳过", "工程已存在，跳过覆盖。"))
                    return

                config_path = get_scene_config_path(scene_id)
                if not config_path.exists():
                    legacy = resolve_scene_config_path(scene_id)
                    if legacy and legacy != config_path:
                        config_path = legacy
                if not config_path.exists():
                    self._log("未找到场景配方，正在初始化脚手架…")
                    create_from_video(
                        loop_video,
                        scene_id=scene_id,
                        duration_hours=duration,
                        skip_generate=True,
                        on_progress=self._log,
                    )
                    config_path = get_scene_config_path(scene_id)
                from gui.core_controller import update_lua_config_with_selections
                update_lua_config_with_selections(
                    config_path, scene_id, duration, selected_tracks, LIB_REPO_ROOT,
                    log_fn=self._log,
                )

                ensure_shared_scripts()
                cfg = gen_sub.load_config(config_path)
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
            duration = float(self.duration_var.get())
        except ValueError:
            messagebox.showerror("参数错误", "成片时长必须是数字。")
            return

        wav_name = export_wav_name(self.scene_id, duration)
        wav_path = export_dir() / wav_name
        self._set_render_ui(running=True, status="Elapsed: 00:00:00  Remaining: …")
        self._log(f"—— 开始输出混音: {wav_name} ——")

        def worker() -> None:
            try:
                exe = (self._cfg.get("reaper_exe") or "").strip() or None
                self._log(f"渲染工程: {rpp_path.name}")

                def on_progress(msg: str) -> None:
                    self.after(0, lambda m=msg: self._set_render_ui(running=True, status=m))

                render_reaper_project(
                    rpp_path,
                    reaper_exe=exe,
                    output_wav=wav_path,
                    duration_hours=duration,
                    on_progress=on_progress,
                )
                result_wav = wav_path if wav_path.is_file() else self._find_latest_wav_for_scene(self.scene_id)
                self._log(f"混音完成: {result_wav.name if result_wav else wav_name}")

                def done_ok() -> None:
                    if result_wav and self.scene_id:
                        self._save_scene_export_path(self.scene_id, "wav", result_wav)
                    self._set_render_ui(
                        running=False,
                        status=self._format_export_status(result_wav),
                    )
                    messagebox.showinfo(
                        "成功",
                        f"{result_wav.name if result_wav else wav_name} 渲染完成！",
                    )

                self.after(0, done_ok)
            except Exception as exc:
                def done_err(err: BaseException = exc) -> None:
                    self._log(f"渲染失败: {err}")
                    self._set_render_ui(running=False, status="失败")
                    messagebox.showerror("渲染失败", str(err))

                self.after(0, done_err)

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

        saved_wav = self._get_scene_export_path(self.scene_id, "wav")
        if saved_wav:
            audio_file = saved_wav
        else:
            target_dir = LIB_REPO_ROOT / "Reaper" / "Projects" / "Rain"
            wavs = list(target_dir.glob(f"*{num}*.wav"))
            exp_wavs = list(export_dir().glob(f"*{num}*.wav"))
            wavs = sorted(set(wavs + exp_wavs), key=lambda p: p.stat().st_mtime, reverse=True)
            if not wavs:
                messagebox.showwarning("提示", f"未找到包含 {num} 的音频文件。\n请先「一键输出混音」！")
                return
            audio_file = wavs[0]
        vid_file = self.video_path

        def to_wsl(p):
            s = str(p).replace("\\", "/")
            if s.startswith("//wsl.localhost/Ubuntu"): return s.replace("//wsl.localhost/Ubuntu", "")
            if s.startswith("//wsl$/Ubuntu"): return s.replace("//wsl$/Ubuntu", "")
            if ":" in s:
                d, r = s.split(":", 1)
                return f"/mnt/{d.lower()}{r}"
            return s

        script_wsl = to_wsl(LIB_REPO_ROOT / "scripts" / "video_export" / "export_mp4.sh")
        vid_wsl = to_wsl(vid_file)
        aud_wsl = to_wsl(audio_file)

        import sys
        if sys.platform == "win32":
            cmd = ["wsl", "bash", script_wsl, "-v", vid_wsl, "-a", aud_wsl, "--encoder", "nvenc"]
        else:
            cmd = ["bash", script_wsl, "-v", vid_wsl, "-a", aud_wsl, "--encoder", "nvenc"]

        self._set_export_ui(running=True, status="Elapsed: 00:00:00  Remaining: …")
        self._log("—— 开始合成视频 (export_mp4) ——")
        self._log(f"音频：{audio_file.name}")
        self._log(f"视频：{vid_file.name}")

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
                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        continue
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("==> Done:"):
                        raw = line.split(":", 1)[1].strip()
                        if raw:
                            output_mp4 = Path(raw)
                    if line.startswith("PROGRESS "):
                        status = line.removeprefix("PROGRESS ").strip()
                        self.after(0, lambda s=status: self._set_export_ui(running=True, status=s))
                    else:
                        self._log(line)
                proc.wait()
                if proc.returncode == 0:
                    if (not output_mp4 or not output_mp4.is_file()) and self.scene_id:
                        output_mp4 = self._find_latest_mp4_for_scene(self.scene_id)

                    def done_ok() -> None:
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
                    self.after(0, done_ok)
                else:
                    def done_err() -> None:
                        self._set_export_ui(running=False, status="失败")
                        messagebox.showerror("合成失败", f"export_mp4.sh 返回错误码 {proc.returncode}")
                    self.after(0, done_err)
            except Exception as exc:
                def done_err2(err: BaseException = exc) -> None:
                    self._set_export_ui(running=False, status="失败")
                    messagebox.showerror("运行失败", str(err))
                self.after(0, done_err2)

        threading.Thread(target=worker, daemon=True).start()

    def _upload_youtube(self) -> None:
        if self._busy:
            return
        if not self.scene_id:
            messagebox.showwarning("提示", "请先选择场景。")
            return
            
        import re
        match = re.search(r'\d+', self.scene_id)
        num = match.group() if match else self.scene_id
        rpp_dir = LIB_REPO_ROOT / "Reaper" / "Projects" / "Rain"

        md_candidates = []
        def gather_mds(d: Path):
            if not d or not d.is_dir(): return
            for pattern in [f"*{num}*_material.md", f"*{num}*youtube.md", "youtube.md", f"MVI_{num}.md", f"{num}.md"]:
                for p in d.glob(pattern):
                    if p not in md_candidates:
                        md_candidates.append(p)
                        
        gather_mds(self.material_dir)
        gather_mds(rpp_dir)
        
        if not md_candidates:
            messagebox.showwarning("提示", f"未找到包含 {num} 的物料 md 文件。")
            return
        md_path = md_candidates[0]
            
        # Find the _3h_*k.mp4 file
        mp4_candidates = []
        if self.material_dir and self.material_dir.is_dir():
            mp4_candidates.extend(self.material_dir.glob(f"*{num}*.mp4"))
        mp4_candidates.extend(rpp_dir.glob(f"*{num}*.mp4"))
        
        if self.video_path:
            mp4_candidates = [p for p in mp4_candidates if p.name != self.video_path.name]
            
        if not mp4_candidates:
            messagebox.showwarning("提示", f"未找到包含 {num} 的 mp4 视频，请先进行视频合成！")
            return
            
        # Sort to get the most recent export
        mp4_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        video_path = mp4_candidates[0]

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

        self._set_busy(True)
        self._log("—— 开始上传到 YouTube ——")
        self._log(f"账号：{account}")
        self._log(f"物料：{md_path.name}")
        self._log(f"视频：{video_path.name}")
        self._log("首次上传需在浏览器完成 OAuth 授权")

        def worker() -> None:
            try:
                up_mod = load_scripts_module("video_upload.youtube_upload")
                record = up_mod.upload_from_material(
                    md_path,
                    language=language,
                    privacy_status=privacy,
                    account=account,
                    override_video_path=video_path,
                    on_log=self._log,
                )

                def done_ok() -> None:
                    url = record["url"]
                    self._cfg["last_upload_url"] = url
                    self._save_config()
                    self._mark_scene_uploaded(self.scene_id)
                    self.lbl_upload.configure(text=f"上传：{url}")
                    messagebox.showinfo("上传完成", f"视频已上传：\n{url}\n\n可见性：{privacy}")

                self.after(0, done_ok)
            except Exception as exc:
                def done_err(err: BaseException = exc) -> None:
                    self._log(f"错误：{err}")
                    messagebox.showerror("上传失败", str(err))

                self.after(0, done_err)
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    app = RelaxAsmrApp()
    app.mainloop()


if __name__ == "__main__":
    main()
