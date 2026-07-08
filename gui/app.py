"""relaxASMR 工程 GUI（Tkinter）。"""

from __future__ import annotations

import json
import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"  # Suppress TensorFlow warnings

import sys
import threading
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
)
from gui.folder_open import open_folder  # noqa: E402
from gui.import_reload import load_module, load_scripts_module  # noqa: E402
from gui.rain_vst_ui import RainVstSection  # noqa: E402
from gui.youtube_material import (  # noqa: E402
    RAIN_THUMB_TITLE,
    find_material_dir,
    loop_material_dir,
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

        self._load_config()
        self._build_ui()

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
        pad = {"padx": 10, "pady": 6}
        
        self.main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.left_frame = ttk.Frame(self.main_pane)
        self.right_frame = ttk.Frame(self.main_pane)
        self.main_pane.add(self.left_frame, weight=3)
        self.main_pane.add(self.right_frame, weight=2)
        
        self.notebook = ttk.Notebook(self.left_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        tab_workflow = ttk.Frame(self.notebook)
        self.notebook.add(tab_workflow, text="自动化工作流")

        tab_vst = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab_vst, text="Rain VST 独立分析")

        root = ttk.Frame(tab_workflow, padding=10)
        root.pack(fill=tk.BOTH, expand=True)
        
        self.rain_vst = RainVstSection(tab_vst, log_fn=self._log, busy_guard=self)
        self.rain_vst.pack(fill=tk.X)

        # --- 1. 导入视频 ---
        sec1 = ttk.LabelFrame(root, text="1. 导入 Loop 视频", padding=10)
        sec1.pack(fill=tk.X, **pad)

        row1 = ttk.Frame(sec1)
        row1.pack(fill=tk.X)
        ttk.Button(row1, text="选择 MP4…", command=self._import_video).pack(side=tk.LEFT)
        self.lbl_video = ttk.Label(row1, text="未选择视频", wraplength=640)
        self.lbl_video.pack(side=tk.LEFT, padx=(12, 0), fill=tk.X, expand=True)

        self.lbl_scene = ttk.Label(sec1, text="场景 ID：—")
        self.lbl_scene.pack(anchor=tk.W, pady=(6, 0))

        # --- 2. 新建 Reaper 工程 (自动分析+物料+建轨) ---
        sec2 = ttk.LabelFrame(root, text="2. 新建 Reaper 工程 (自动分析+物料+建轨)", padding=10)
        sec2.pack(fill=tk.X, **pad)

        row2 = ttk.Frame(sec2)
        row2.pack(fill=tk.X)
        ttk.Label(row2, text="成片时长 (h)").pack(side=tk.LEFT)
        self.duration_var = tk.StringVar(value=str(self._cfg.get("duration_hours", 3)))
        ttk.Spinbox(row2, from_=1, to=12, increment=0.5, width=6, textvariable=self.duration_var).pack(
            side=tk.LEFT, padx=(8, 16)
        )
        self.overwrite_rpp_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="覆盖 RPP", variable=self.overwrite_rpp_var).pack(side=tk.LEFT, padx=(0, 8))
        self.overwrite_mat_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="覆盖物料", variable=self.overwrite_mat_var).pack(side=tk.LEFT, padx=(0, 16))
        self.btn_create = ttk.Button(row2, text="一键分析并生成", command=self._create_project)
        self.btn_create.pack(side=tk.LEFT)
        self.btn_open_material = ttk.Button(row2, text="打开物料目录", command=self._open_material)
        self.btn_open_material.pack(side=tk.LEFT, padx=(8, 0))

        self.lbl_sub = ttk.Label(sec2, text="子工程：—", wraplength=760)
        self.lbl_sub.pack(anchor=tk.W, pady=(8, 0))
        self.lbl_material = ttk.Label(sec2, text="物料：—", wraplength=760)
        self.lbl_material.pack(anchor=tk.W, pady=(4, 0))

        # --- 3. 打开 Reaper ---
        sec3 = ttk.LabelFrame(root, text="3. 打开 Reaper 工程", padding=10)
        sec3.pack(fill=tk.X, **pad)

        row3 = ttk.Frame(sec3)
        row3.pack(fill=tk.X)
        self.btn_open = ttk.Button(row3, text="在 Reaper 中打开", command=self._open_reaper)
        self.btn_open.pack(side=tk.LEFT)
        self.btn_open_rpp_dir = ttk.Button(row3, text="打开工程目录", command=self._open_rpp_dir)
        self.btn_open_rpp_dir.pack(side=tk.LEFT, padx=(8, 0))

        row3b = ttk.Frame(sec3)
        row3b.pack(fill=tk.X, pady=(8, 0))
        reaper_label = "Reaper 可执行文件（WSL 填 Windows 路径）" if is_wsl() else "Reaper 可执行文件（可选）"
        ttk.Label(row3b, text=reaper_label).pack(side=tk.LEFT)
        default_exe = self._cfg.get("reaper_exe", "")
        if not default_exe:
            if is_wsl():
                default_exe = default_windows_reaper_from_wsl() or ""
            else:
                cands = default_reaper_candidates()
                if cands:
                    default_exe = str(cands[0])
        self.reaper_exe_var = tk.StringVar(value=default_exe)
        ttk.Entry(row3b, textvariable=self.reaper_exe_var, width=56).pack(
            side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True
        )

        self.lbl_rpp = ttk.Label(sec3, text="工程：—", wraplength=760)
        self.lbl_rpp.pack(anchor=tk.W, pady=(8, 0))

        # --- 4. 合成视频 (导出 MP4) ---
        sec_export = ttk.LabelFrame(root, text="4. 合成视频 (导出 MP4)", padding=10)
        sec_export.pack(fill=tk.X, **pad)

        row_export = ttk.Frame(sec_export)
        row_export.pack(fill=tk.X)
        self.btn_export = ttk.Button(row_export, text="开始合成 (export_mp4)", command=self._export_mp4)
        self.btn_export.pack(side=tk.LEFT)
        self.btn_open_output = ttk.Button(row_export, text="打开输出目录", command=self._open_output)
        self.btn_open_output.pack(side=tk.LEFT, padx=(8, 0))
        self.lbl_export = ttk.Label(sec_export, text="合成进度：待开始", wraplength=760)
        self.lbl_export.pack(anchor=tk.W, pady=(8, 0))

        # --- 5. 一键上传 YouTube ---
        sec4 = ttk.LabelFrame(root, text="5. 一键上传 YouTube", padding=10)
        sec4.pack(fill=tk.X, **pad)

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
        


        self.lbl_upload = ttk.Label(sec4, text="待上传：—", wraplength=760)
        self.lbl_upload.pack(anchor=tk.W, pady=(8, 0))

        # --- 预览区 ---
        self.preview_frame = ttk.LabelFrame(root, text="画面快照预览", padding=10)
        self.preview_frame.pack(fill=tk.BOTH, expand=True, **pad)
        self.lbl_preview = ttk.Label(self.preview_frame, text="无预览")
        self.lbl_preview.pack(anchor=tk.CENTER)

        # --- 日志 (全局可见) ---
        sec_log = ttk.LabelFrame(self.right_frame, text="日志", padding=8)
        sec_log.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(sec_log, height=14, wrap=tk.WORD, state=tk.DISABLED)
        scroll = ttk.Scrollbar(sec_log, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

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

    def _log(self, msg: str) -> None:
        def append() -> None:
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)

        self.after(0, append)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.btn_create.configure(state=state)
        self.btn_upload.configure(state=state)
        if hasattr(self, 'btn_export'):
            self.btn_export.configure(state=state)

    def _refresh_material_label(self) -> None:
        if self.material_dir and self.material_dir.is_dir():
            try:
                rel = self.material_dir.relative_to(LIB_REPO_ROOT)
            except ValueError:
                rel = self.material_dir
            self.lbl_material.configure(text=f"物料：{rel}/")
            return
        if self.scene_id:
            found = find_material_dir(self.scene_id, LIB_REPO_ROOT)
            if found:
                self.material_dir = found
                try:
                    rel = found.relative_to(LIB_REPO_ROOT)
                except ValueError:
                    rel = found
                self.lbl_material.configure(text=f"物料：{rel}/")
                return
        self.lbl_material.configure(text="物料：—")

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
        self.lbl_video.configure(text=str(video))
        self.lbl_scene.configure(text=f"场景 ID：{scene}")
        self._cfg["last_video"] = str(video)
        self._cfg["last_video_dir"] = str(video.parent)
        self._save_config()
        if from_import:
            self._log(f"已选定视频：{video}")

        import re
        stem = video.stem
        match = re.search(r'\d+', stem)
        num = match.group() if match else stem

        # 1. 自动关联 Reaper 工程
        rpp = LIB_REPO_ROOT / "Reaper" / "Projects" / "Rain" / f"{scene}.rpp"
        if rpp.is_file():
            self._set_rpp(rpp)
            self.lbl_sub.configure(text=f"工程：{rpp.relative_to(LIB_REPO_ROOT)}")
        else:
            self.lbl_sub.configure(text="工程：—")
            self.rpp_path = None
            
        # 2. 自动关联物料
        out_dir = None
        output_dirs = list(video.parent.glob("output*"))
        if output_dirs and output_dirs[0].is_dir():
            out_dir = output_dirs[0]
            
        if out_dir:
            material_md = out_dir / f"MVI_{num}_material.md"
            if material_md.is_file():
                self.material_dir = out_dir
            else:
                self.material_dir = None
        else:
            self.material_dir = None
        self._refresh_material_label()
        
        # 3. 自动关联导出的 MP4
        exported_mp4 = None
        mp4_candidates = []
        if out_dir:
            mp4_candidates.extend(out_dir.glob(f"*{num}*.mp4"))
            
        rpp_dir = LIB_REPO_ROOT / "Reaper" / "Projects" / "Rain"
        mp4_candidates.extend(rpp_dir.glob(f"*{num}*.mp4"))
        
        mp4_candidates = [p for p in mp4_candidates if p.name != video.name]
        if mp4_candidates:
            # 根据修改时间倒序，取最新生成的 MP4
            mp4_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            exported_mp4 = mp4_candidates[0]
                
        if exported_mp4:
            self.lbl_export.configure(text=f"合成进度：已完成 ({exported_mp4.name})")
            self.lbl_upload.configure(text=f"待上传：{exported_mp4}")
            self._cfg["last_export_mp4"] = str(exported_mp4)
        else:
            self.lbl_export.configure(text="合成进度：待开始")
            self.lbl_upload.configure(text="待上传：—")
            self._cfg["last_export_mp4"] = ""

        self._save_config()
        self._update_preview(self.video_path)

    def _update_preview(self, video_path: Path | None) -> None:
        if not hasattr(self, "lbl_preview"):
            return
        if not video_path or not video_path.is_file():
            self.lbl_preview.configure(image="", text="无预览")
            self._preview_img = None
            return
            
        import re
        stem = video_path.stem
        match = re.search(r'\d+', stem)
        num = match.group() if match else stem
        
        snapshot_jpg = None
        output_dirs = list(video_path.parent.glob("output*"))
        if output_dirs and output_dirs[0].is_dir():
            jpgs = list(output_dirs[0].glob(f"*{num}*.jpg"))
            if jpgs:
                snapshot_jpg = jpgs[0]
                
        if not snapshot_jpg or not snapshot_jpg.is_file():
            self.lbl_preview.configure(image="", text="未找到该视频的分析快照")
            self._preview_img = None
            return
            
        try:
            img = Image.open(snapshot_jpg)
            img.thumbnail((480, 270), Image.Resampling.LANCZOS)
            self._preview_img = ImageTk.PhotoImage(img)
            self.lbl_preview.configure(image=self._preview_img, text="")
        except Exception as e:
            self.lbl_preview.configure(image="", text=f"预览加载失败: {e}")
            self._preview_img = None

    def _video_dialog_initialdir(self) -> str:
        saved = self._cfg.get("last_video_dir")
        if saved and Path(saved).is_dir():
            return saved
        assets = LIB_REPO_ROOT / "assets" / "loop_video"
        if assets.is_dir():
            return str(assets)
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

    def _create_project(self) -> None:
        if self._busy:
            return
        if not self.video_path:
            messagebox.showwarning("提示", "请先导入 loop 视频。")
            return
        try:
            duration = float(self.duration_var.get())
        except ValueError:
            messagebox.showerror("参数错误", "成片时长必须是数字。")
            return

        loop_video = self.video_path
        self._set_busy(True)
        self._log("—— 开始创建子工程 ——")

        def worker() -> None:
            material_out: Path | None = None
            try:
                import shutil
                import tempfile
                
                rain_vst_script = LIB_REPO_ROOT / "scripts" / "rain_vst" / "analyze.py"
                vst_mod = load_module(rain_vst_script, "relaxasmr_rain_vst_analyze")
                
                gen_sub_script = LIB_REPO_ROOT / "Reaper" / "scripts" / "generate_subproject.py"
                gen_sub = load_module(gen_sub_script, "generate_subproject")
                
                scene_id = self.scene_id or derive_scene_id(loop_video)
                
                self._log("—— 1. 自动分析画面 ——")
                vst_output_dir = LIB_REPO_ROOT / "assets" / "sound_effect" / "rain_sound" / "1_rain" / "vst_params"
                out_dir, scene_cn, _, _ = vst_mod.analyze_video(loop_video, vst_output_dir, on_progress=self._log)
                
                import re
                match = re.search(r'\d+', scene_id)
                num = match.group() if match else scene_id

                self._log("—— 2. 预生成 YouTube 物料 ——")
                output_dirs = list(loop_video.parent.glob("output*"))
                out_dir = output_dirs[0] if output_dirs and output_dirs[0].is_dir() else loop_video.parent / "output"
                out_dir.mkdir(parents=True, exist_ok=True)
                
                target_md_path = out_dir / f"MVI_{num}_material.md"
                if target_md_path.is_file() and not self.overwrite_mat_var.get():
                    self._log(f"物料已存在且未勾选覆盖，跳过生成。")
                else:
                    yt_mod = load_module(YT_MATERIAL_SCRIPT, "relaxasmr_generate_youtube_material")
                    yt_mod.generate_material(
                        loop_video,
                        output_dir=out_dir,
                        preset_key=scene_cn,
                        copy_style="forest_rain",
                        thumb_title=RAIN_THUMB_TITLE,
                        thumb_subtitle_place_only=True,
                        duration_override_s=duration * 3600,
                        on_progress=self._log,
                    )
                    # generate_material 默认生成 youtube.md，重命名为目标格式
                    if (out_dir / "youtube.md").is_file():
                        (out_dir / "youtube.md").rename(target_md_path)
                        
                material_out = target_md_path

                self._log("—— 3. 新建 Reaper 工程 ——")
                cfg = {
                    "scene_id": scene_id,
                    "project_name": f"Rain · {scene_id}",
                    "series": "rain_sleep",
                    "duration_hours": duration,
                    "loop_layers": [
                        {"track": 1, "id": "1_rain", "name": "小雨主雨势", "vol": 1.0, "paths": []},
                        {"track": 3, "id": "3_environment", "name": "环境空间", "vol": 0.26, "paths": []},
                        {"track": 4, "id": "4_water", "name": "水体/滴水", "vol": 0.18, "paths": []},
                        {"track": 6, "id": "6_human", "name": "留白（待选）", "vol": 0.0, "paths": []},
                    ],
                    "scatter_layers": [
                        {"track": 2, "id": "2_impact", "name": "近景滴答打叶", "vol": 1.0, "paths": []},
                        {"track": 5, "id": "5_wildlife", "name": "远景鸟鸣", "vol": 1.0, "paths": []},
                    ]
                }
                target_audio = None
                if out_dir.is_dir():
                    wavs = [w for w in out_dir.glob(f"*{num}*clip*.wav") if w.is_file()]
                    if wavs:
                        target_audio = wavs[0]
                
                if target_audio:
                    self._log(f"找到默认音频：{target_audio}")
                    try:
                        cfg["loop_layers"][0]["paths"].append(str(target_audio.relative_to(LIB_REPO_ROOT)))
                    except ValueError:
                        cfg["loop_layers"][0]["paths"].append(str(target_audio))
                else:
                    self._log(f"未在 {out_dir.name} 找到包含 {num} 和 clip 的 wav 音频，轨道将留空")
                
                rpp = LIB_REPO_ROOT / "Reaper" / "Projects" / "Rain" / f"{scene_id}.rpp"
                if rpp.is_file() and not self.overwrite_rpp_var.get():
                    self._log(f"工程文件 {rpp.name} 已存在且未勾选覆盖，跳过生成。")
                else:
                    rpp.write_text(gen_sub.build_rpp(cfg, LIB_REPO_ROOT, rpp.parent, "auto"), encoding="utf-8")

                def done_ok() -> None:
                    self._set_rpp(rpp)
                    self.lbl_sub.configure(text=f"工程：{rpp.relative_to(LIB_REPO_ROOT)}")
                    self.material_dir = out_dir
                    self._cfg["last_material_dir"] = str(out_dir)
                    self._refresh_material_label()
                    self._cfg["duration_hours"] = duration
                    self._save_config()
                    self._update_preview(self.video_path)
                    try:
                        mat_show = material_out.relative_to(LIB_REPO_ROOT)
                    except ValueError:
                        mat_show = material_out
                    messagebox.showinfo(
                        "完成",
                        f"工程已生成：\n{rpp.relative_to(LIB_REPO_ROOT)}\n\n"
                        f"物料：\n{mat_show}\n",
                    )

                self.after(0, done_ok)
            except Exception as exc:
                def done_err(err: BaseException = exc) -> None:
                    self._log(f"错误：{err}")
                    messagebox.showerror("创建失败", str(err))

                self.after(0, done_err)
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _set_rpp(self, rpp: Path) -> None:
        self.rpp_path = rpp.resolve()
        try:
            rel = self.rpp_path.relative_to(LIB_REPO_ROOT)
        except ValueError:
            rel = self.rpp_path
        self.lbl_rpp.configure(text=f"工程：{rel}")
        self._cfg["last_rpp"] = str(self.rpp_path)
        self._save_config()

    def _open_reaper(self) -> None:
        if not self.scene_id:
            messagebox.showwarning("提示", "请先选择场景。")
            return
            
        auto_rpp = LIB_REPO_ROOT / "Reaper" / "Projects" / "Rain" / f"{self.scene_id}.rpp"
        if auto_rpp.is_file():
            self._set_rpp(auto_rpp)
            
        if not self.rpp_path or not self.rpp_path.is_file():
            messagebox.showwarning("提示", "请先生成 Reaper 工程。")
            return
        exe = self.reaper_exe_var.get().strip() or None
        self._cfg["reaper_exe"] = exe or ""
        self._save_config()
        try:
            open_reaper_project(self.rpp_path, reaper_exe=exe)
            self._log(f"已打开：{self.rpp_path.name}")
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
            root = (
                LIB_REPO_ROOT
                / "Reaper"
                / "Projects"
                / "Rain"
                / "subprojects"
                / self.scene_id
                / "output"
                / "material"
            )
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
        target = LIB_REPO_ROOT / "Reaper" / "Projects" / "Rain"
        try:
            open_folder(target)
            self._log(f"已打开输出目录：{target}")
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def _export_mp4(self) -> None:
        if self._busy:
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
        
        target_dir = LIB_REPO_ROOT / "Reaper" / "Projects" / "Rain"
        wavs = list(target_dir.glob(f"*{num}*.wav"))
        if not wavs:
            messagebox.showwarning("提示", f"未找到包含 {num} 的音频文件。\n请先在 Reaper 中手动导出！")
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

        self._set_busy(True)
        self._log("—— 开始合成视频 (export_mp4) ——")
        self._log(f"音频：{audio_file.name}")
        self._log(f"视频：{vid_file.name}")
        self.lbl_export.configure(text="合成进度：正在运行...")
        
        def worker() -> None:
            import subprocess
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                for line in iter(proc.stdout.readline, ''):
                    if line:
                        line = line.strip()
                        if line:
                            self._log(line)
                proc.wait()
                if proc.returncode == 0:
                    def done_ok() -> None:
                        self._set_video(self.video_path, from_import=False)
                        messagebox.showinfo("合成成功", "长视频导出完成，已保存在 output 目录下！")
                    self.after(0, done_ok)
                else:
                    def done_err() -> None:
                        self.lbl_export.configure(text="合成进度：失败")
                        messagebox.showerror("合成失败", f"export_mp4.sh 返回错误码 {proc.returncode}")
                    self.after(0, done_err)
            except Exception as exc:
                def done_err2(e=exc) -> None:
                    self.lbl_export.configure(text="合成进度：失败")
                    messagebox.showerror("运行失败", str(e))
                self.after(0, done_err2)
            finally:
                self.after(0, lambda: self._set_busy(False))
                
        import threading
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
