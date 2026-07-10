"""声音库参数分析 UI 组件（baseURL/audio）。"""

from __future__ import annotations

import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Pattern to extract the base video ID (e.g. "MVI_6952") from filenames like
# "MVI_6952_loop_0.94_dur_6_fade_0.5_01.mp4".
_VIDEO_ID_RE = re.compile(r"^(MVI_\d+)")


def extract_video_id(filename: str) -> str:
    """从视频文件名中提取基础 ID（例如 ``MVI_6952``）。

    Handles filenames such as ``MVI_6952_loop_0.94_dur_6_fade_0.5_01.mp4``.
    Falls back to the stem (filename without extension) when no match is found.
    """
    m = _VIDEO_ID_RE.match(Path(filename).stem)
    return m.group(1) if m else Path(filename).stem


class SoundLibrarySection(ttk.LabelFrame):
    """可嵌入主窗口的声音库分析区域。"""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        log_fn: Callable[[str], None],
        busy_guard: object,
    ) -> None:
        super().__init__(parent, text="1.5 声音库分析", padding=10)
        self._log = log_fn
        self._guard = busy_guard  # expects ._busy and ._set_busy()
        self._selected_path: Path | None = None
        self._video_list: list[Path] = []
        self._audio_proc = None
        self._matched_wav: Path | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Row 1 — file / folder selection
        row1 = ttk.Frame(self)
        row1.pack(fill=tk.X)

        ttk.Button(row1, text="选择视频…", command=self._pick_file).pack(side=tk.LEFT)
        ttk.Button(row1, text="选择文件夹…", command=self._pick_folder).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self.lbl_selection = ttk.Label(row1, text="未选择", wraplength=540)
        self.lbl_selection.pack(side=tk.LEFT, padx=(12, 0), fill=tk.X, expand=True)

        # Row 2 — action
        row2 = ttk.Frame(self)
        row2.pack(fill=tk.X, pady=(8, 0))

        self.btn_analyze = ttk.Button(row2, text="开始分析", command=self._start_analysis)
        self.btn_analyze.pack(side=tk.LEFT)
        self.lbl_progress = ttk.Label(row2, text="")
        self.lbl_progress.pack(side=tk.LEFT, padx=(12, 0), fill=tk.X, expand=True)

        # Row 3 - Matching and Playback
        row3 = ttk.Frame(self)
        row3.pack(fill=tk.X, pady=(8, 0))
        self.lbl_match = ttk.Label(row3, text="匹配结果：—", wraplength=480)
        self.lbl_match.pack(side=tk.LEFT)
        self.btn_play = ttk.Button(row3, text="▶ 试听", state=tk.DISABLED, command=self._play_audio)
        self.btn_play.pack(side=tk.LEFT, padx=(12, 0))
        self.btn_stop = ttk.Button(row3, text="⏹ 停止", state=tk.DISABLED, command=self._stop_audio)
        self.btn_stop.pack(side=tk.LEFT, padx=(4, 0))

        # Row 4 - Preview Image
        self.lbl_preview = ttk.Label(self, text="[画面预览]")
        self.lbl_preview.pack(pady=(10, 0))

        # Restore last selection if available
        cfg = getattr(self._guard, "_cfg", {})
        saved = cfg.get("last_vst_dir")
        if saved:
            p = Path(saved)
            if p.is_dir():
                self._selected_path = p
                videos = sorted(p.rglob("*.mp4"))
                self._video_list = videos
                self.lbl_selection.configure(text=f"{p.name}/（{len(videos)} 个视频）")
            elif p.is_file():
                self._selected_path = p
                self._video_list = [p]
                vid = extract_video_id(p.name)
                self.lbl_selection.configure(text=f"{p.name}（{vid}）")

        # Restore last match if available
        last_rain = cfg.get("last_vst_match_rain")
        last_score = cfg.get("last_vst_match_score")
        last_wav = cfg.get("last_vst_match_wav")
        last_frame = cfg.get("last_vst_frame")
        
        if last_rain and last_score is not None:
            self.lbl_match.configure(text=f"最佳匹配：{last_rain}\n(相似度: {last_score:.3f})")
            
        if last_wav:
            wav_p = Path(last_wav)
            if wav_p.is_file():
                self._matched_wav = wav_p
                self.btn_play.configure(state=tk.NORMAL)
                self.btn_stop.configure(state=tk.NORMAL)
                
        if last_frame:
            frame_p = Path(last_frame)
            if frame_p.is_file():
                try:
                    from PIL import Image, ImageTk
                    img = Image.open(frame_p)
                    img.thumbnail((480, 270))
                    photo = ImageTk.PhotoImage(img)
                    self.lbl_preview.configure(image=photo, text="")
                    self.lbl_preview.image = photo  # keep ref
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # File / folder dialogs
    # ------------------------------------------------------------------

    def _initial_dir(self) -> str:
        """Return the last-used directory, falling back to assets."""
        cfg = getattr(self._guard, "_cfg", {})
        saved = cfg.get("last_vst_dir")
        if saved and Path(saved).is_dir():
            return saved
        assets = REPO_ROOT / "assets" / "loop_video"
        if assets.is_dir():
            return str(assets)
        return str(REPO_ROOT)

    def _remember_dir(self, directory: Path) -> None:
        """Persist the selected directory or file in the parent config."""
        cfg = getattr(self._guard, "_cfg", None)
        if cfg is not None:
            cfg["last_vst_dir"] = str(directory)
            save = getattr(self._guard, "_save_config", None)
            if callable(save):
                save()

    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择视频文件",
            initialdir=self._initial_dir(),
            filetypes=[("MP4 视频", "*.mp4"), ("所有文件", "*.*")],
        )
        if not path:
            return
        p = Path(path)
        self._remember_dir(p)
        self._selected_path = p
        self._video_list = [p]
        vid = extract_video_id(p.name)
        self.lbl_selection.configure(text=f"{p.name}（{vid}）")
        self._log(f"VST 分析 — 已选择视频：{p.name}")

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="选择视频文件夹",
            initialdir=self._initial_dir(),
        )
        if not folder:
            return
        d = Path(folder)
        self._remember_dir(d)
        videos = sorted(d.rglob("*.mp4"))
        if not videos:
            messagebox.showwarning("提示", f"所选文件夹中没有 .mp4 文件：\n{d}")
            return
        self._selected_path = d
        self._video_list = videos
        self.lbl_selection.configure(text=f"{d.name}/（{len(videos)} 个视频）")
        self._log(f"VST 分析 — 已选择文件夹：{d.name}/（{len(videos)} 个 MP4）")

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _progress(self, msg: str) -> None:
        """Callback forwarded to the analyzer; updates label + log."""
        self._log(msg)
        # Schedule UI update on the main thread
        root = self.winfo_toplevel()
        root.after(0, lambda: self.lbl_progress.configure(text=msg))

    def _start_analysis(self) -> None:
        if getattr(self._guard, "_busy", False):
            return
        if not self._video_list:
            messagebox.showwarning("提示", "请先选择视频文件或文件夹。")
            return

        videos = list(self._video_list)
        total = len(videos)
        self._guard._set_busy(True)  # type: ignore[union-attr]
        self.btn_analyze.configure(state=tk.DISABLED)
        self._log("—— 开始声音库分析 ——")

        def worker() -> None:
            succeeded: list[str] = []
            failed: list[tuple[str, str]] = []
            root = self.winfo_toplevel()

            try:
                from scripts.video_analysis.analyze import analyze_video
            except ImportError as exc:
                def show_err(err: BaseException = exc) -> None:
                    self._log(f"错误：无法导入 scripts.video_analysis.analyze — {err}")
                    messagebox.showerror(
                        "导入失败",
                        f"无法导入 scripts.video_analysis.analyze：\n{err}\n\n请确认依赖已安装。",
                    )
                root.after(0, show_err)
                return

            if not self._selected_path:
                return

            if self._selected_path.is_file():
                input_dir = self._selected_path.parent
            else:
                input_dir = self._selected_path
                
            if input_dir.name.startswith("output"):
                out_dir = input_dir.parent / "output_audio"
            else:
                out_dir = input_dir / "output_audio"
                
            out_dir.mkdir(parents=True, exist_ok=True)

            last_rain = None
            last_frame = None

            for idx, video in enumerate(videos, 1):
                vid = extract_video_id(video.name)
                if total > 1:
                    status = f"分析中 ({idx}/{total}): {vid}..."
                else:
                    status = f"分析中: {vid}..."
                root.after(0, lambda s=status: self.lbl_progress.configure(text=s))
                self._log(status)

                try:
                    _, _, rain_p, frame_p = analyze_video(video, out_dir, on_progress=self._progress)
                    succeeded.append(vid)
                    last_rain = rain_p
                    last_frame = frame_p
                except Exception as exc:
                    self._log(f"错误：{vid} — {exc}")
                    failed.append((vid, str(exc)))

            # Build summary
            parts: list[str] = []
            parts.append(f"分析完成：共 {total} 个视频")
            if succeeded:
                parts.append(f"成功：{len(succeeded)}")
            if failed:
                parts.append(f"失败：{len(failed)}")
                for name, err in failed:
                    parts.append(f"  · {name}: {err}")
            parts.append(f"\n输出目录：\n{out_dir}")
            summary = "\n".join(parts)

            def done_ok() -> None:
                self.lbl_progress.configure(
                    text=f"完成 — 成功 {len(succeeded)}, 失败 {len(failed)}"
                )
                self._log("—— VST 参数分析完成 ——")
                
                if last_rain and last_frame:
                    vst_dirs = list(input_dir.glob("*vst*"))
                    if vst_dirs:
                        try:
                            from scripts.video_analysis.matcher import find_best_match
                            match_res = find_best_match(last_rain, vst_dirs[0])
                            if match_res:
                                matched_path, score = match_res
                                prefix = matched_path.name.split('.')[0] + '.'
                                wav_cands = list(matched_path.parent.glob(f"{prefix}*.wav"))
                                if wav_cands:
                                    self._matched_wav = wav_cands[0]
                                else:
                                    self._matched_wav = matched_path.with_suffix(".wav")
                                
                                # display full path with line wrapping or just full path
                                self.lbl_match.configure(text=f"最佳匹配：{matched_path.resolve()}\n(相似度: {score:.3f})")
                                
                                if self._matched_wav and self._matched_wav.is_file():
                                    self.btn_play.configure(state=tk.NORMAL)
                                    self.btn_stop.configure(state=tk.NORMAL)
                                    self._guard._cfg["last_vst_match_wav"] = str(self._matched_wav.resolve())
                                else:
                                    self._log("警告：未找到对应的 .wav 文件供试听。")
                                    self._guard._cfg["last_vst_match_wav"] = ""
                                
                                self._guard._cfg["last_vst_match_rain"] = str(matched_path.resolve())
                                self._guard._cfg["last_vst_match_score"] = score
                                self._log(f"最佳匹配：{matched_path.resolve()} (得分: {score:.3f})")
                        except Exception as e:
                            self._log(f"匹配预设失败: {e}")
                    
                    try:
                        from PIL import Image, ImageTk
                        img = Image.open(last_frame)
                        img.thumbnail((480, 270))
                        photo = ImageTk.PhotoImage(img)
                        self.lbl_preview.configure(image=photo, text="")
                        self.lbl_preview.image = photo  # keep ref
                    except Exception as e:
                        self._log(f"加载预览图失败: {e}")
                        
                    self._guard._cfg["last_vst_frame"] = str(last_frame.resolve())
                    
                    save = getattr(self._guard, "_save_config", None)
                    if callable(save):
                        save()

                messagebox.showinfo("分析完成", summary)
                # Try to open the output directory
                try:
                    from gui.folder_open import open_folder
                    if out_dir.is_dir():
                        open_folder(out_dir)
                except Exception:
                    pass

            root.after(0, done_ok)

        def cleanup() -> None:
            self._guard._set_busy(False)  # type: ignore[union-attr]
            self.btn_analyze.configure(state=tk.NORMAL)

        def run() -> None:
            try:
                worker()
            finally:
                self.winfo_toplevel().after(0, cleanup)

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------------
    # Audio Playback
    # ------------------------------------------------------------------

    def _play_audio(self) -> None:
        if not self._matched_wav or not self._matched_wav.is_file():
            return
            
        self._stop_audio()
        
        try:
            from gui.audio_playback import play_wav_once

            self._audio_proc = play_wav_once(self._matched_wav)
            self._log(f"正在播放：{self._matched_wav.name}")
        except Exception as e:
            self._log(f"播放失败: {e}")

    def _stop_audio(self) -> None:
        try:
            from gui.audio_playback import stop_wav_playback

            stop_wav_playback(getattr(self, "_audio_proc", None))
            self._audio_proc = None
            self._log("已停止播放")
        except Exception:
            pass
