"""AIGC 专用右侧预览区：文生 / 图生二选一展示，与工作流封面/视频预览完全隔离。"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from gui.clipboard import setup_copyable_readonly_text
from gui.tk_thread import bind_ui_root

_TMP_PREFIX = "relaxasmr_aigc_preview_"
_VIDEO_MIN_H = 160


class AigcPreviewPanel(ttk.Frame):
    """上 2/3 预览区：只显示文生或图生其中一种布局。"""

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, padding=0)
        bind_ui_root(self)

        self._mode = "t2v"  # t2v | i2v
        self._run_id = "—"
        self._prompt = ""
        self._video_path: Path | None = None
        self._image_path: Path | None = None

        self._cap = None
        self._loop_id: str | None = None
        self._audio_proc = None
        self._audio_path: str | None = None
        self._token = 0
        self._photo: ImageTk.PhotoImage | None = None
        self._img_photo: ImageTk.PhotoImage | None = None
        self._img_render_token = 0
        self._last_rendered_image: Path | None = None
        self._resize_after: str | None = None
        self._i2v_sash_equalized = False
        self._i2v_sash_attempts = 0

        self._frame = ttk.LabelFrame(self, text="文生视频", padding=10)
        self._frame.pack(fill=tk.BOTH, expand=True)

        self.lbl_run = ttk.Label(self._frame, text="—", foreground="gray")
        self.lbl_run.pack(anchor=tk.W, pady=(0, 6))

        self._body = ttk.PanedWindow(self._frame, orient=tk.VERTICAL)
        self._body.pack(fill=tk.BOTH, expand=True)

        self._video_wrap = ttk.Frame(self._body)
        self._body.add(self._video_wrap, weight=3)
        self.video_canvas = tk.Canvas(
            self._video_wrap,
            height=_VIDEO_MIN_H,
            highlightthickness=0,
            bd=0,
        )
        self.video_canvas.pack(fill=tk.BOTH, expand=True)
        self.video_canvas.bind("<Configure>", self._on_video_configure)

        self._bottom = ttk.Frame(self._body)
        self._body.add(self._bottom, weight=2)

        # 文生：整幅 prompt
        self._t2v_prompt_wrap, self._t2v_prompt = self._make_prompt_text(self._bottom)

        # 有参考图时：下半区左右分栏 — 左参考图 / 右 prompt
        self._i2v_bottom = ttk.PanedWindow(self._bottom, orient=tk.HORIZONTAL)
        self._i2v_img_wrap = ttk.Frame(self._i2v_bottom)
        self._i2v_bottom.add(self._i2v_img_wrap, weight=1)
        self.image_canvas = tk.Canvas(
            self._i2v_img_wrap,
            width=200,
            height=140,
            highlightthickness=0,
            bd=0,
        )
        self.image_canvas.pack(fill=tk.BOTH, expand=True)
        self.image_canvas.bind("<Configure>", self._on_image_configure)
        self._i2v_prompt_wrap, self._i2v_prompt = self._make_prompt_text(self._i2v_bottom)
        self._i2v_bottom.add(self._i2v_prompt_wrap, weight=1)
        self._i2v_bottom.bind("<Map>", self._equalize_i2v_sash_once, add="+")

        self._show_t2v_layout()
        self._show_video_placeholder("无预览")
        self._set_prompt_text("")

    def _make_prompt_text(self, parent: tk.Widget) -> tuple[ttk.Frame, tk.Text]:
        wrap = ttk.Frame(parent)
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        scroll = ttk.Scrollbar(wrap, orient=tk.VERTICAL)
        txt = tk.Text(
            wrap,
            height=8,
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=0,
            state=tk.DISABLED,
            font=("", 10),
            yscrollcommand=scroll.set,
        )
        txt.grid(row=0, column=0, sticky="nsew")
        scroll.config(command=txt.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        setup_copyable_readonly_text(txt, self)
        return wrap, txt

    def _show_t2v_layout(self) -> None:
        self._mode = "t2v"
        self._frame.configure(text="文生视频")
        self._i2v_bottom.pack_forget()
        self._t2v_prompt_wrap.pack(fill=tk.BOTH, expand=True)

    def _show_i2v_layout(self) -> None:
        self._mode = "i2v"
        self._frame.configure(text="图生视频")
        self._t2v_prompt_wrap.pack_forget()
        self._i2v_bottom.pack(fill=tk.BOTH, expand=True)
        if not self._i2v_sash_equalized:
            self.after_idle(self._equalize_i2v_sash_once)

    def _equalize_i2v_sash_once(self, _event=None) -> None:
        """图生下栏：参考图与 prompt 初始宽度 1:1；之后用户可拖动 sash。"""
        if self._i2v_sash_equalized or self._mode != "i2v":
            return
        self.update_idletasks()
        w = self._i2v_bottom.winfo_width()
        if w <= 1:
            if self._i2v_sash_attempts < 10:
                self._i2v_sash_attempts += 1
                self.after(80, self._equalize_i2v_sash_once)
            return
        try:
            self._i2v_bottom.sashpos(0, max(w // 2, 80))
        except tk.TclError:
            if self._i2v_sash_attempts < 10:
                self._i2v_sash_attempts += 1
                self.after(80, self._equalize_i2v_sash_once)
            return
        self._i2v_sash_equalized = True

    def set_mode(self, mode: str) -> None:
        kind = "i2v" if mode == "i2v" else "t2v"
        if kind == self._mode:
            return
        if kind == "i2v":
            self._show_i2v_layout()
        else:
            self._show_t2v_layout()
        self._render_prompt()
        if kind == "i2v":
            self._render_image()
        self._refresh_video_frame()

    def show_t2v(
        self,
        video_path: Path | None,
        *,
        run_id: str = "—",
        prompt: str = "",
        slots: dict | None = None,
    ) -> None:
        del slots
        self._show_t2v_layout()
        rid = (run_id or "—").strip() or "—"
        text = str(prompt or "").strip()
        new_video = video_path.resolve() if video_path and video_path.is_file() else None
        if rid == self._run_id and text == self._prompt and new_video == self._video_path:
            return
        self._run_id = rid
        self.lbl_run.configure(text=self._run_id)
        self._prompt = text
        self._render_prompt()
        if new_video != self._video_path:
            self._set_video(new_video)

    def show_i2v(
        self,
        video_path: Path | None,
        *,
        run_id: str = "—",
        prompt: str = "",
        slots: dict | None = None,
        image_path: Path | None = None,
    ) -> None:
        del slots
        self._show_i2v_layout()
        rid = (run_id or "—").strip() or "—"
        text = str(prompt or "").strip()
        new_video = video_path.resolve() if video_path and video_path.is_file() else None
        new_image = image_path.resolve() if image_path and image_path.is_file() else None
        if (
            rid == self._run_id
            and text == self._prompt
            and new_video == self._video_path
            and new_image == self._image_path
        ):
            return
        self._run_id = rid
        self.lbl_run.configure(text=self._run_id)
        self._prompt = text
        self._image_path = new_image
        self._render_prompt()
        if new_image != getattr(self, "_last_rendered_image", None):
            self._last_rendered_image = new_image
            self.after_idle(self._render_image)
        if new_video != self._video_path:
            self._set_video(new_video)

    def clear(self) -> None:
        self.stop_playback()
        self._video_path = None
        self._image_path = None
        self._prompt = ""
        self._run_id = "—"
        self.lbl_run.configure(text="—")
        self._show_video_placeholder("无预览")
        self._set_prompt_text("")
        if self._mode == "i2v":
            self._render_image()

    def stop_playback(self) -> None:
        self._token += 1
        if self._loop_id is not None:
            try:
                self.after_cancel(self._loop_id)
            except tk.TclError:
                pass
            self._loop_id = None
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self._stop_audio()

    def _stop_audio(self) -> None:
        proc = self._audio_proc
        self._audio_proc = None
        self._audio_path = None
        if proc is None:
            return
        try:
            from gui.audio_playback import stop_wav_playback

            stop_wav_playback(proc)
        except Exception:
            pass

    def _start_audio(self, media_path: str) -> None:
        self._stop_audio()
        try:
            from gui.audio_playback import start_media_audio_loop

            self._audio_proc = start_media_audio_loop(Path(media_path))
            self._audio_path = media_path if self._audio_proc is not None else None
        except Exception:
            self._audio_proc = None
            self._audio_path = None

    def _render_prompt(self) -> None:
        self._set_prompt_text(self._prompt)

    def _set_prompt_text(self, text: str) -> None:
        for widget in (self._t2v_prompt, self._i2v_prompt):
            widget.configure(state=tk.NORMAL)
            widget.delete("1.0", tk.END)
            if text:
                widget.insert("1.0", text)
            widget.configure(state=tk.DISABLED)
            widget.see("1.0")

    def _set_video(self, video_path: Path | None) -> None:
        self.stop_playback()
        if video_path is not None and video_path.is_file():
            self._video_path = video_path.resolve()
            self._load_video(self._video_path)
        else:
            self._video_path = None
            self._show_video_placeholder("无预览")

    def _video_size(self) -> tuple[int, int]:
        self.video_canvas.update_idletasks()
        w = max(self.video_canvas.winfo_width(), 160)
        h = max(self.video_canvas.winfo_height(), _VIDEO_MIN_H)
        return w, h

    def _show_video_placeholder(self, text: str) -> None:
        w, h = self._video_size()
        self.video_canvas.delete("all")
        self.video_canvas.create_text(
            w // 2,
            h // 2,
            text=text,
            anchor=tk.CENTER,
            width=max(w - 8, 80),
        )
        self._photo = None

    def _tmp_path(self, token: int) -> str:
        import tempfile

        name = f"{_TMP_PREFIX}{os.getpid()}_{token}.mp4"
        return os.path.join(tempfile.gettempdir(), name)

    def _cleanup_tmp(self, *, keep: str | None = None) -> None:
        import tempfile

        tmp_dir = tempfile.gettempdir()
        prefix = f"{_TMP_PREFIX}{os.getpid()}_"
        keep_abs = os.path.abspath(keep) if keep else None
        try:
            names = os.listdir(tmp_dir)
        except OSError:
            return
        for name in names:
            if not name.startswith(prefix):
                continue
            path = os.path.join(tmp_dir, name)
            if keep_abs is not None and os.path.abspath(path) == keep_abs:
                continue
            try:
                os.remove(path)
            except OSError:
                pass

    def _load_video(self, video_path: Path) -> None:
        self._show_video_placeholder("加载视频预览中...")
        token = self._token
        tmp_path = self._tmp_path(token)

        def copy_and_play() -> None:
            error: Exception | None = None
            try:
                shutil.copy2(video_path, tmp_path)
            except Exception as exc:  # noqa: BLE001
                error = exc

            def done() -> None:
                if token != self._token:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                    return
                if error is not None:
                    self._show_video_placeholder(f"视频复制失败: {error}")
                    return
                self._start_loop(tmp_path)
                self._cleanup_tmp(keep=tmp_path)

            try:
                self.after(0, done)
            except tk.TclError:
                pass

        threading.Thread(target=copy_and_play, daemon=True).start()

    def _start_loop(self, tmp_path: str) -> None:
        import cv2

        self._cap = cv2.VideoCapture(tmp_path)
        if not self._cap.isOpened():
            self._show_video_placeholder("无法打开临时视频文件进行循环播放")
            return
        self._start_audio(tmp_path)
        self._play_next_frame()

    def _play_next_frame(self) -> None:
        if self._cap is None:
            return
        import cv2

        ret, frame = self._cap.read()
        if not ret:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._cap.read()
        if ret:
            try:
                w, h = self._video_size()
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                img.thumbnail((w, h), Image.Resampling.LANCZOS)
                self._photo = ImageTk.PhotoImage(img)
                self.video_canvas.delete("all")
                self.video_canvas.create_image(
                    w // 2,
                    h // 2,
                    anchor=tk.CENTER,
                    image=self._photo,
                )
            except Exception:
                pass
        self._loop_id = self.after(33, self._play_next_frame)

    def _refresh_video_frame(self) -> None:
        # 尺寸变化时下一帧会按新 canvas 重绘；无播放则重画占位
        if self._cap is None and self._video_path is None:
            self._show_video_placeholder("无预览")

    def _on_video_configure(self, _event=None) -> None:
        if self._resize_after:
            try:
                self.after_cancel(self._resize_after)
            except tk.TclError:
                pass
        self._resize_after = self.after(120, self._on_resize_settled)

    def _on_resize_settled(self) -> None:
        self._resize_after = None
        if self._mode == "i2v":
            self._render_image()
        self._refresh_video_frame()

    def _on_image_configure(self, _event=None) -> None:
        if self._mode != "i2v":
            return
        if self._resize_after:
            try:
                self.after_cancel(self._resize_after)
            except tk.TclError:
                pass
        self._resize_after = self.after(120, self._on_resize_settled)

    def _render_image(self) -> None:
        canvas = self.image_canvas
        canvas.update_idletasks()
        w = max(canvas.winfo_width(), 120)
        h = max(canvas.winfo_height(), 90)
        path = self._image_path
        self._img_render_token += 1
        token = self._img_render_token

        if path is None or not path.is_file():
            canvas.delete("all")
            canvas.create_text(w // 2, h // 2, text="无图片", anchor=tk.CENTER)
            self._img_photo = None
            return

        def work() -> None:
            err: str | None = None
            thumb: Image.Image | None = None
            try:
                img = Image.open(path)
                img.thumbnail((w, h), Image.Resampling.LANCZOS)
                thumb = img
            except Exception as exc:  # noqa: BLE001
                err = str(exc)

            def apply() -> None:
                if token != self._img_render_token:
                    return
                canvas.delete("all")
                if thumb is not None:
                    self._img_photo = ImageTk.PhotoImage(thumb)
                    canvas.create_image(
                        w // 2, h // 2, anchor=tk.CENTER, image=self._img_photo
                    )
                    return
                canvas.create_text(
                    w // 2,
                    h // 2,
                    text=f"图片加载失败: {err or '未知错误'}",
                    anchor=tk.CENTER,
                    width=max(w - 8, 80),
                )
                self._img_photo = None

            try:
                self.after(0, apply)
            except tk.TclError:
                pass

        threading.Thread(target=work, daemon=True).start()
