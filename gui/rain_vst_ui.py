"""RAIN VST 参数分析 UI 组件。"""

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

OUTPUT_DIR = REPO_ROOT / "assets" / "sound_effect" / "rain_sound" / "1_rain" / "vst_params"

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


class RainVstSection(ttk.LabelFrame):
    """可嵌入主窗口的 RAIN VST 参数分析区域。"""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        log_fn: Callable[[str], None],
        busy_guard: object,
    ) -> None:
        super().__init__(parent, text="1.5 RAIN VST 参数分析", padding=10)
        self._log = log_fn
        self._guard = busy_guard  # expects ._busy and ._set_busy()
        self._selected_path: Path | None = None
        self._video_list: list[Path] = []
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
        """Persist the selected directory in the parent config."""
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
        self._remember_dir(p.parent)
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
        self._log("—— 开始 RAIN VST 参数分析 ——")

        def worker() -> None:
            succeeded: list[str] = []
            failed: list[tuple[str, str]] = []
            root = self.winfo_toplevel()

            try:
                # Lazy import — the analyzer may have heavy dependencies.
                from scripts.rain_vst_analyze import analyze_video  # noqa: E402
            except ImportError as exc:
                def show_err(err: BaseException = exc) -> None:
                    self._log(f"错误：无法导入 rain_vst_analyze — {err}")
                    messagebox.showerror(
                        "导入失败",
                        f"无法导入 scripts.rain_vst_analyze：\n{err}\n\n"
                        "请确认依赖已安装。",
                    )
                root.after(0, show_err)
                return

            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            for idx, video in enumerate(videos, 1):
                vid = extract_video_id(video.name)
                if total > 1:
                    status = f"分析中 ({idx}/{total}): {vid}..."
                else:
                    status = f"分析中: {vid}..."
                root.after(0, lambda s=status: self.lbl_progress.configure(text=s))
                self._log(status)

                try:
                    analyze_video(video, OUTPUT_DIR, on_progress=self._progress)
                    succeeded.append(vid)
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
            parts.append(f"\n输出目录：\n{OUTPUT_DIR}")
            summary = "\n".join(parts)

            def done_ok() -> None:
                self.lbl_progress.configure(
                    text=f"完成 — 成功 {len(succeeded)}, 失败 {len(failed)}"
                )
                self._log("—— VST 参数分析完成 ——")
                messagebox.showinfo("分析完成", summary)
                # Try to open the output directory
                try:
                    from gui.folder_open import open_folder

                    if OUTPUT_DIR.is_dir():
                        open_folder(OUTPUT_DIR)
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
