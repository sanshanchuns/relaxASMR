"""「AIGC」Tab：文生视频实验台（Seedance VIP · 六槽原子表）。"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

from gui.clipboard import setup_copyable_readonly_text
from gui.tk_thread import bind_ui_root, schedule_on_main
from gui.ui_theme import UiTheme
from gui.video_quota_panel import JimengQuotaPanel
from scripts.aigc_lab import ScoreError, create_run, list_runs, load_run, score_run
from scripts.aigc_lab.store import lab_params, save_lab_params, slots_from_run
from scripts.aigc_lab.prompt_atoms import (
    DEFAULT_RAIN_MODE,
    DEFAULT_SCENES,
    LOCKED_SLOTS,
    RAIN_MODE_LABELS,
    RAIN_MODES,
    SLOT_LABELS,
    SLOT_ORDER,
    check_tag_conflicts,
    compose_prompt,
    default_scenes,
    format_scenes,
    format_table,
    normalize_rain_mode,
    product_locked_closed_slots,
    replace_failed_atoms,
    rewrite_atomic,
)
from scripts.aigc_lab.session import load_session, save_session
from scripts.aigc_lab.tag_pools import (
    failed_tags_from_scores,
    format_tags_by_slot,
    merge_into_pools,
    merge_scenes_into_pool,
    qualified_tags_from_scores,
    suggest_for_scene,
    suggest_for_slot,
)
from scripts.config.paths import ensure_cli_path

_LIST_W = 42
_GENERATE_BTN_LABEL = "生成视频"
_FAIL_BORDER = "#c62828"
_DRAG_BORDER = "#1976d2"
_TAG_BORDER_THICKNESS = 2  # 合格/不合格统一厚度，仅改边框色，避免点击时布局跳动
_TAG_DRAG_THRESHOLD_PX = 6
_TAG_DISPLAY_MAX_CHARS = 24


class AigcTab(ttk.Frame):
    def __init__(
        self,
        master,
        *,
        log_fn: Callable[[str], None],
        on_preview_run: Callable[..., None] | None = None,
    ) -> None:
        super().__init__(master)
        bind_ui_root(self)
        self._log = log_fn
        self._on_preview_run = on_preview_run
        self._busy = False
        self._cancel = False
        self._runs: list = []
        self._selected_run_id: str | None = None
        self._run_ui_loaded_id: str | None = None
        self._suppress_run_select = False
        self._slot_containers: dict[str, tk.Frame] = {}
        self._slot_tags_areas: dict[str, tk.Frame] = {}
        self._slot_add_frames: dict[str, tk.Frame] = {}
        # 每槽原子原文（UI 唯一数据源）
        self._slot_atoms: dict[str, list[str]] = {key: [] for key in SLOT_ORDER}
        # 场景标签（指导 LLM，不进送模）
        self._scene_atoms: list[str] = list(DEFAULT_SCENES)
        # 人工/评分标记的不合格标签（红框）；入池时排除
        self._slot_fail_tags: dict[str, set[str]] = {key: set() for key in SLOT_ORDER}
        self._slot_add_vars: dict[str, tk.StringVar] = {
            key: tk.StringVar(value="") for key in SLOT_ORDER
        }
        self._scene_add_var = tk.StringVar(value="")
        self._slot_add_combos: dict[str, ttk.Combobox] = {}
        self._scene_add_combo: ttk.Combobox | None = None
        self._slot_reflow_after: dict[str, str | None] = {
            key: None for key in SLOT_ORDER
        }
        self._scene_reflow_after: str | None = None
        self._reflow_guard: dict[str, bool] = {key: False for key in SLOT_ORDER}
        self._scene_reflow_guard = False
        self._slot_last_width: dict[str, int] = {key: 0 for key in SLOT_ORDER}
        self._scene_last_width = 0
        self._slot_tag_widgets: dict[str, dict[str, tk.Frame]] = {
            key: {} for key in SLOT_ORDER
        }
        self._scene_tag_widgets: dict[str, tk.Frame] = {}
        self._layout_frozen = False
        # 统一配色（apply_theme 覆盖）
        self._atom_row_bg = "#f5f5f5"
        self._atom_tag_bg = "#e8e8e8"
        self._atom_tag_fg = "#1a1a1a"
        self._atom_border = "#d0d0d0"
        self._loaded_once = False
        self._session_save_after_id: str | None = None
        self._runs_refresh_token = 0
        self._scroll_canvas: tk.Canvas | None = None
        self._scroll_vbar: ttk.Scrollbar | None = None
        self._scroll_inner: ttk.Frame | None = None
        self._scroll_window: int | None = None
        self._scroll_guard = False
        self._scroll_sync_after: str | None = None
        self._scroll_last_width = 0
        self._body_pane: ttk.PanedWindow | None = None
        self._body_pane_ratio_attempts = 0
        # 标签拖拽：区分单击（槽位标红）与拖动换序
        self._tag_drag: dict | None = None
        self._tag_drag_ghost: tk.Toplevel | None = None

        self._build_ui()

    def _setup_scroll_area(self) -> ttk.Frame:
        """左侧 AIGC 内容区：溢出时垂直滚动。

        滚动条始终占位（不 grid_remove），避免显隐导致宽度抖动 →
        标签 reflow → Configure 递归。
        """
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(container, highlightthickness=0, borderwidth=0)
        vbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")

        inner = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=inner, anchor=tk.NW)

        inner.bind("<Configure>", self._on_scroll_inner_configure)
        canvas.bind("<Configure>", self._on_scroll_canvas_configure)
        canvas.bind("<Enter>", self._bind_scroll_wheel)
        canvas.bind("<Leave>", self._unbind_scroll_wheel)
        inner.bind("<Enter>", self._bind_scroll_wheel)
        inner.bind("<Leave>", self._unbind_scroll_wheel)

        self._scroll_canvas = canvas
        self._scroll_vbar = vbar
        self._scroll_inner = inner
        self._scroll_window = window
        return inner

    def _on_scroll_inner_configure(self, _event=None) -> None:
        """内容尺寸变化 → 防抖刷新 scrollregion（禁止在回调里 update_idletasks）。"""
        self._schedule_scroll_sync()

    def _on_scroll_canvas_configure(self, event=None) -> None:
        if event is None or self._scroll_canvas is None or self._scroll_window is None:
            return
        width = int(event.width)
        if width <= 1 or abs(width - self._scroll_last_width) < 2:
            return
        self._scroll_last_width = width
        if self._scroll_guard:
            return
        self._scroll_guard = True
        try:
            self._scroll_canvas.itemconfigure(self._scroll_window, width=width)
        finally:
            self._scroll_guard = False
        self._schedule_scroll_sync()

    def _schedule_scroll_sync(self) -> None:
        if self._scroll_sync_after is not None:
            try:
                self.after_cancel(self._scroll_sync_after)
            except tk.TclError:
                pass
        self._scroll_sync_after = self.after(80, self._apply_scroll_region)

    def _apply_scroll_region(self) -> None:
        self._scroll_sync_after = None
        canvas = self._scroll_canvas
        if canvas is None or self._scroll_guard:
            return
        self._scroll_guard = True
        try:
            bbox = canvas.bbox("all")
            if bbox is not None:
                canvas.configure(scrollregion=bbox)
        except tk.TclError:
            pass
        finally:
            self._scroll_guard = False

    def _bind_scroll_wheel(self, _event=None) -> None:
        canvas = self._scroll_canvas
        if canvas is None:
            return
        canvas.bind_all("<MouseWheel>", self._on_scroll_wheel)
        canvas.bind_all("<Button-4>", self._on_scroll_wheel)
        canvas.bind_all("<Button-5>", self._on_scroll_wheel)

    def _unbind_scroll_wheel(self, _event=None) -> None:
        canvas = self._scroll_canvas
        if canvas is None:
            return
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")

    def _wheel_delta_units(self, event) -> int:
        if getattr(event, "num", None) == 4:
            return -3
        if getattr(event, "num", None) == 5:
            return 3
        delta = int(-1 * (event.delta / 120)) if getattr(event, "delta", 0) else 0
        return delta

    def _event_over_run_list(self, event) -> bool:
        """鼠标是否在「实验记录」列表或其滚动条上。"""
        widget = getattr(event, "widget", None)
        while widget is not None:
            if widget is getattr(self, "list_runs", None) or widget is getattr(
                self, "_list_runs_scroll", None
            ):
                return True
            try:
                widget = widget.master
            except (AttributeError, tk.TclError):
                break
        # bind_all 时 widget 偶发不是命中控件，再用坐标判定
        try:
            x, y = self.winfo_pointerxy()
            hit = self.winfo_containing(x, y)
        except tk.TclError:
            return False
        while hit is not None:
            if hit is getattr(self, "list_runs", None) or hit is getattr(
                self, "_list_runs_scroll", None
            ):
                return True
            try:
                hit = hit.master
            except (AttributeError, tk.TclError):
                break
        return False

    def _on_run_list_wheel(self, event) -> str:
        """实验记录列表上的滚轮：只滚列表，阻断外层整页滚动。"""
        units = self._wheel_delta_units(event)
        if units:
            self.list_runs.yview_scroll(units, "units")
        return "break"

    def _on_scroll_wheel(self, event) -> str | None:
        units = self._wheel_delta_units(event)
        if not units:
            return None
        if self._event_over_run_list(event):
            self.list_runs.yview_scroll(units, "units")
            return "break"
        canvas = self._scroll_canvas
        if canvas is None:
            return None
        canvas.yview_scroll(units, "units")
        return None

    def _sync_scroll_region(self) -> None:
        self._schedule_scroll_sync()

    def _build_ui(self) -> None:
        root = self._setup_scroll_area()

        top = ttk.Frame(root)
        top.pack(fill=tk.X, padx=8, pady=(8, 4))

        params = lab_params()
        model = params.get("model", "Seedance 2.0 Fast VIP")
        default_dur = int(params.get("duration_sec", 4))
        ttk.Label(
            top,
            text=f"实验台 · {model} · 16:9 · 720p ·",
        ).pack(side=tk.LEFT)
        self.spin_duration = ttk.Spinbox(top, from_=1, to=15, width=3)
        self.spin_duration.set(str(default_dur))
        self.spin_duration.pack(side=tk.LEFT, padx=(0, 0))
        ttk.Label(top, text="s").pack(side=tk.LEFT, padx=(0, 8))
        self.spin_duration.bind("<FocusOut>", lambda _e: self._persist_duration_sec())
        self.spin_duration.bind("<Return>", lambda _e: self._persist_duration_sec())
        ttk.Label(top, text="生成数量").pack(side=tk.LEFT, padx=(0, 0))
        try:
            default_count = max(1, min(10, int(params.get("generate_count", 1))))
        except (TypeError, ValueError):
            default_count = 1
        self.spin_generate_count = ttk.Spinbox(top, from_=1, to=10, width=3)
        self.spin_generate_count.set(str(default_count))
        self.spin_generate_count.pack(side=tk.LEFT, padx=(4, 8))
        self.spin_generate_count.bind(
            "<FocusOut>", lambda _e: self._persist_generate_count()
        )
        self.spin_generate_count.bind(
            "<Return>", lambda _e: self._persist_generate_count()
        )

        self.btn_jimeng_login = ttk.Button(
            top, text="即梦登录", command=self._start_jimeng_login
        )
        self.btn_jimeng_login.pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(top, text="刷新列表", command=self.refresh).pack(side=tk.RIGHT)

        quota_frame = ttk.LabelFrame(root, text="生视频模型额度")
        quota_frame.pack(fill=tk.X, padx=8, pady=(0, 4))
        self.jimeng_quota_panel = JimengQuotaPanel(quota_frame, log_fn=self._log)
        self.jimeng_quota_panel.pack(fill=tk.X, expand=True, padx=8, pady=5)

        scene_frame = ttk.LabelFrame(
            root,
            text="场景（总约束 · 指导 LLM 基线/替换 · 不进送模 · 拖动改序 · ×删除 · 行末从池选或新输入）",
            padding=8,
        )
        scene_frame.pack(fill=tk.X, padx=8, pady=(4, 0))
        self._build_scene_bar(scene_frame)

        prompt_frame = ttk.LabelFrame(
            root,
            text="Prompt 原子表（拖动改序；×删除；单击标可疑/红框；行末从池选或新输入；送模=各槽拼接）",
            padding=8,
        )
        prompt_frame.pack(fill=tk.X, padx=8, pady=4)

        # 用 tk.Frame 而非 ttk，避免 ttk 父级下 tk 子控件几何异常
        table = tk.Frame(prompt_frame, bg=self._atom_row_bg)
        table.pack(fill=tk.X)
        table.columnconfigure(1, weight=1)
        self._atom_table = table

        ttk.Label(table, text="槽位", width=6).grid(row=0, column=0, sticky="w")
        ttk.Label(table, text="原子标签").grid(row=0, column=1, sticky="w")

        for i, key in enumerate(SLOT_ORDER, start=1):
            ttk.Label(table, text=SLOT_LABELS[key], width=6).grid(
                row=i, column=0, sticky="nw", pady=4
            )
            self._build_slot_row(table, key, i)

        ttk.Label(
            prompt_frame,
            text="镜头/风格/约束在 LLM 基线时固定；仅主体/动作/环境可变",
        ).pack(anchor=tk.W, pady=(4, 0))

        row_gen = ttk.Frame(prompt_frame)
        row_gen.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row_gen, text="雨档").pack(side=tk.LEFT)
        self.rain_var = tk.StringVar(value=RAIN_MODE_LABELS[DEFAULT_RAIN_MODE])
        self.cmb_rain = ttk.Combobox(
            row_gen,
            textvariable=self.rain_var,
            values=[label for _, label in RAIN_MODES],
            state="readonly",
            width=8,
        )
        self.cmb_rain.pack(side=tk.LEFT, padx=(4, 8))
        self.cmb_rain.bind("<<ComboboxSelected>>", lambda _e: self._on_rain_mode_changed())
        ttk.Button(
            row_gen, text="LLM生成基线", command=self._start_llm_baseline
        ).pack(side=tk.LEFT)
        ttk.Button(
            row_gen, text="预览送模正文", command=self._preview_model_prompt
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            row_gen, text="合格标签入池", command=self._pool_qualified_manual
        ).pack(side=tk.LEFT, padx=(6, 0))
        self.btn_generate = ttk.Button(
            row_gen, text="生成视频", command=self._start_generate
        )
        self.btn_generate.pack(side=tk.LEFT, padx=(12, 0))
        self.btn_stop = ttk.Button(row_gen, text="停止", command=self._request_cancel)
        self.btn_stop.pack(side=tk.LEFT, padx=(6, 0))

        body = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.X, padx=8, pady=(0, 8))
        self._body_pane = body

        left = ttk.Frame(body)
        body.add(left, weight=4)

        ttk.Label(left, text="实验记录").pack(anchor=tk.W)
        list_row = ttk.Frame(left)
        list_row.pack(fill=tk.BOTH, expand=True)
        self.list_runs = tk.Listbox(
            list_row, width=_LIST_W, height=14, exportselection=False
        )
        self._list_runs_scroll = ttk.Scrollbar(
            list_row, orient=tk.VERTICAL, command=self.list_runs.yview
        )
        self.list_runs.configure(yscrollcommand=self._list_runs_scroll.set)
        # 先 pack 滚动条，避免被 Listbox expand 挤掉
        self._list_runs_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_runs.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # 列表内滚轮：只滚实验记录（外层 bind_all 也会判定命中后交给这里）
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.list_runs.bind(seq, self._on_run_list_wheel, add="+")
            self._list_runs_scroll.bind(seq, self._on_run_list_wheel, add="+")
        # 只响应点中某一行；空白处 / 重复点同一条不重载
        self.list_runs.bind("<ButtonRelease-1>", self._on_run_click)
        self.list_runs.bind("<KeyRelease-Up>", self._on_run_key_nav)
        self.list_runs.bind("<KeyRelease-Down>", self._on_run_key_nav)
        self.list_runs.bind("<KeyRelease-Return>", self._on_run_key_nav)

        right = ttk.Frame(body)
        body.add(right, weight=6)

        ttk.Label(right, text="详情").pack(anchor=tk.W)
        self.txt_detail = tk.Text(right, height=10, wrap=tk.WORD)
        self.txt_detail.pack(fill=tk.X)
        setup_copyable_readonly_text(self.txt_detail, self)

        row_act = ttk.Frame(right)
        row_act.pack(fill=tk.X, pady=(6, 0))
        self.btn_score = ttk.Button(
            row_act, text="VLM标记可疑标签", command=self._start_score
        )
        self.btn_score.pack(side=tk.LEFT)
        self.btn_llm_replace = ttk.Button(
            row_act, text="LLM替换可疑标签", command=self._start_llm_replace
        )
        self.btn_llm_replace.pack(side=tk.LEFT, padx=(6, 0))
        body.bind("<Map>", self._equalize_body_pane_once, add="+")
        self.after_idle(self._equalize_body_pane_once)
        self._sync_scroll_region()

    def _equalize_body_pane_once(self, _event=None) -> None:
        """实验记录 : 详情 初始宽度 4:6；之后用户可拖动 sash 调整。"""
        pane = self._body_pane
        if pane is None:
            return
        self.update_idletasks()
        w = pane.winfo_width()
        if w <= 1:
            if self._body_pane_ratio_attempts < 10:
                self._body_pane_ratio_attempts += 1
                self.after(80, self._equalize_body_pane_once)
            return
        target = max(int(w * 0.4), 120)
        try:
            pane.sashpos(0, target)
        except tk.TclError:
            pass

    def on_tab_selected(self) -> None:
        if not self._loaded_once:
            self._loaded_once = True
            # 等 Notebook 几何稳定后恢复 session 或只填一次基线
            self.after(120, self._init_session_once)
            self._refresh_jimeng_login_ui()
            self.jimeng_quota_panel.reload()
            return
        self.refresh()
        self._refresh_jimeng_login_ui()
        self.jimeng_quota_panel.reload()
        self._sync_scroll_region()

    def _refresh_runs_async(self, *, after: Callable[[], None] | None = None) -> None:
        self._runs_refresh_token += 1
        token = self._runs_refresh_token

        def work() -> None:
            try:
                runs = list_runs()
            except Exception:
                runs = []

            def apply() -> None:
                if token != self._runs_refresh_token:
                    return
                self._apply_runs_list(runs, after=after)

            schedule_on_main(self, apply)

        threading.Thread(target=work, daemon=True).start()

    def _apply_runs_list(
        self, runs: list, *, after: Callable[[], None] | None = None
    ) -> None:
        self._runs = runs
        sel = self._selected_run_id
        need_autoload = False
        self._suppress_run_select = True
        try:
            self.list_runs.delete(0, tk.END)
            for run in self._runs:
                video_ok = "✓" if run.video_path.is_file() else "…"
                scored = "◎" if run.scores else " "
                dispute = "!" if run.scores.get("needs_human") else ""
                label = f"{video_ok}{scored}{dispute} {run.run_id}"
                self.list_runs.insert(tk.END, label)
            if sel:
                for i, run in enumerate(self._runs):
                    if run.run_id == sel:
                        self.list_runs.selection_set(i)
                        self.list_runs.see(i)
                        break
            need_autoload = bool(self._runs) and not self.list_runs.curselection()
            if need_autoload:
                self.list_runs.selection_set(0)
        finally:
            self._suppress_run_select = False
        if need_autoload:
            self._on_run_select(force=True)
        if after:
            after()

    def refresh(self, *, after: Callable[[], None] | None = None) -> None:
        self._refresh_runs_async(after=after)

    def sync_right_preview(self) -> None:
        """供 AIGC 壳子 Tab 切换时刷新右侧预览（不阻塞）。"""
        if not self._on_preview_run:
            return
        run = self._selected_run()
        if run is not None:
            video = run.video_path if run.video_path.is_file() else None
            self._on_preview_run(
                video, run.run_id, slots_from_run(run), kind="t2v"
            )
        else:
            self._on_preview_run(None, "—", self._read_slots(), kind="t2v")

    def _init_session_once(self) -> None:
        ready = all(
            area.winfo_width() > 1
            for area in list(self._slot_tags_areas.values())
            + ([self._scene_tags_area] if getattr(self, "_scene_tags_area", None) else [])
        )
        if not ready:
            self.after(50, self._init_session_once)
            return
        if self._restore_session():
            return
        if any(self._slot_atoms.values()):
            self.refresh()
            return
        self._write_scenes(default_scenes())
        self._apply_locked_slots_only()
        self.refresh()

    def _session_payload(self) -> dict:
        return {
            "rain_mode": self._current_rain_mode(),
            "scenes": self._read_scenes(),
            "slots": self._read_slots(),
            "fail_tags": {
                key: sorted(self._slot_fail_tags.get(key) or set())
                for key in SLOT_ORDER
            },
            "selected_run_id": self._selected_run_id or "",
        }

    def _schedule_save_session(self) -> None:
        if self._session_save_after_id is not None:
            try:
                self.after_cancel(self._session_save_after_id)
            except tk.TclError:
                pass
        self._session_save_after_id = self.after(300, self.save_session_now)

    def save_session_now(self) -> None:
        self._session_save_after_id = None
        try:
            save_session(self._session_payload())
        except OSError:
            pass

    def _sync_fail_borders(self) -> None:
        """内存中的红框状态 → 标签边框色（必要时 reflow）。"""
        if not self._repaint_tag_borders():
            for key in SLOT_ORDER:
                self._reflow_tags(key)

    def _preload_fail_marks(
        self, fails: dict[str, list[str]], slots: dict[str, list[str]]
    ) -> None:
        """在创建标签 widget 前写入红框，避免首帧全灰。"""
        self._clear_fail_marks()
        for key in SLOT_ORDER:
            slot_tags = {
                str(a).strip() for a in (slots.get(key) or []) if str(a).strip()
            }
            for tag in fails.get(key) or []:
                t = str(tag).strip()
                if t and t in slot_tags:
                    self._slot_fail_tags[key].add(t)

    def _restore_session(self) -> bool:
        data = load_session()
        if data is None:
            return False
        mode = normalize_rain_mode(str(data.get("rain_mode") or DEFAULT_RAIN_MODE))
        self.rain_var.set(RAIN_MODE_LABELS[mode])
        scenes = [str(s).strip() for s in (data.get("scenes") or []) if str(s).strip()]
        if not scenes:
            scenes = list(DEFAULT_SCENES)
        self._write_scenes(scenes)
        slots = {key: list((data.get("slots") or {}).get(key) or []) for key in SLOT_ORDER}
        fails = {
            key: list((data.get("fail_tags") or {}).get(key) or []) for key in SLOT_ORDER
        }
        sel = str(data.get("selected_run_id") or "").strip()
        if not any(slots.values()) and sel:
            try:
                run = load_run(sel)
                run_slots = slots_from_run(run)
                if any(run_slots.values()):
                    slots = run_slots
                    run_mode = str((run.meta or {}).get("rain_mode") or "").strip()
                    if run_mode:
                        mode = normalize_rain_mode(run_mode)
                        self.rain_var.set(RAIN_MODE_LABELS[mode])
            except Exception:  # noqa: BLE001
                pass
        self._preload_fail_marks(fails, slots)
        self._write_slots(slots, clear_fails=False)
        if sel and not any(v for s in self._slot_fail_tags.values() for v in s):
            try:
                self._apply_score_fails_from_run(load_run(sel))
            except Exception:  # noqa: BLE001
                pass
        if sel:
            self._selected_run_id = sel
        self.refresh()
        if sel and self.list_runs.curselection():
            self._on_run_select(load_slots=False, force=True)
        self._log("[AIGC] 已恢复上次会话（场景 · 原子表 · 红框 · 选中 run）")
        return True

    def _apply_score_fails_from_run(self, run) -> None:
        """把 scores 里 partial/no 标签标红（仅作用于当前表内已有标签）。"""
        scores = getattr(run, "scores", None) or {}
        if not scores:
            return
        failed = failed_tags_from_scores(scores)
        self._set_fail_marks_for_current_ui(failed)
        self._sync_fail_borders()

    def _repaint_tag_borders(self) -> bool:
        """就地刷新边框色；widget 与原子表不一致时返回 False。"""
        for slot in SLOT_ORDER:
            atoms = [a for a in (self._slot_atoms.get(slot) or []) if a.strip()]
            widgets = self._slot_tag_widgets.get(slot) or {}
            if set(widgets) != set(atoms):
                return False
        for slot in SLOT_ORDER:
            fails = self._slot_fail_tags.get(slot) or set()
            for text in self._slot_atoms.get(slot) or []:
                outer = self._slot_tag_widgets.get(slot, {}).get(text)
                if outer is None:
                    return False
                try:
                    outer.configure(bg=self._tag_border_color(failed=text in fails))
                except tk.TclError:
                    return False
        return True

    def _apply_run_slots(self, run, *, clear_fails: bool = True) -> bool:
        """把 run 的六槽原子载入标签表；内容相同则跳过重建，避免闪烁。"""
        slots = slots_from_run(run)
        if not any(slots.values()):
            return False
        run_mode = str((run.meta or {}).get("rain_mode") or "").strip()
        if run_mode:
            mode = normalize_rain_mode(run_mode)
            self.rain_var.set(RAIN_MODE_LABELS[mode])
        current = self._read_slots()
        same = all(
            [str(a).strip() for a in (slots.get(key) or []) if str(a).strip()]
            == current.get(key)
            for key in SLOT_ORDER
        )
        if same:
            if clear_fails:
                self._clear_fail_marks()
                self._sync_fail_borders()
            return True
        self._write_slots(slots, clear_fails=clear_fails)
        return True

    def apply_theme(self, theme: UiTheme) -> None:
        if theme.name == "light":
            self._atom_row_bg = "#f3f3f3"
            self._atom_tag_bg = "#e4e4e4"
            self._atom_tag_fg = "#1a1a1a"
            self._atom_border = "#c8c8c8"
        else:
            self._atom_row_bg = "#2d2d2d"
            self._atom_tag_bg = "#3c3c3c"
            self._atom_tag_fg = "#e8e8e8"
            self._atom_border = "#555555"
        self._paint_slot_chrome()
        if self._scene_atoms:
            self._reflow_scene_tags()
        if any(self._slot_atoms.values()):
            for key in SLOT_ORDER:
                self._reflow_tags(key)
        self.txt_detail.configure(
            bg=theme.text_bg,
            fg=theme.fg,
            insertbackground=theme.fg,
            selectbackground=theme.select_bg,
            selectforeground=theme.select_fg,
        )
        self.list_runs.configure(
            bg=theme.text_bg,
            fg=theme.fg,
            selectbackground=theme.select_bg,
            selectforeground=theme.select_fg,
            highlightbackground=theme.trough,
            highlightcolor=theme.trough,
        )
        if self._scroll_canvas is not None:
            self._scroll_canvas.configure(bg=theme.canvas_bg)
        self._sync_scroll_region()

    def _jimeng_login_button_text(self, *, logged_in: bool) -> str:
        return "即梦 · 已登录" if logged_in else "即梦登录"

    def _set_jimeng_login_button(self, *, logged_in: bool) -> None:
        self.btn_jimeng_login.configure(
            text=self._jimeng_login_button_text(logged_in=logged_in)
        )

    def _refresh_jimeng_login_ui(self) -> None:
        def job() -> None:
            logged_in = False
            try:
                ensure_cli_path()
                from jimeng_web.client import JimengWebClient

                logged_in = JimengWebClient().login_status().is_logged_in
            except Exception:  # noqa: BLE001
                pass
            schedule_on_main(
                self, self._set_jimeng_login_button, logged_in=logged_in
            )

        threading.Thread(target=job, daemon=True).start()

    def _selected_run(self):
        sel = self.list_runs.curselection()
        if not sel:
            return None
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._runs):
            return None
        return self._runs[idx]

    def _on_run_click(self, event) -> None:
        """仅当鼠标点中某一行条目时加载；点空白不刷新。"""
        if self._suppress_run_select:
            return
        size = self.list_runs.size()
        if size <= 0:
            return
        idx = self.list_runs.nearest(event.y)
        if idx < 0 or idx >= size:
            return
        bbox = self.list_runs.bbox(idx)
        if not bbox:
            return
        _x, y, _w, h = bbox
        if event.y < y or event.y > y + h:
            return
        self.list_runs.selection_clear(0, tk.END)
        self.list_runs.selection_set(idx)
        self.list_runs.activate(idx)
        self._on_run_select()

    def _on_run_key_nav(self, _event=None) -> None:
        if self._suppress_run_select:
            return
        self.after_idle(self._on_run_select)

    def _on_run_select(
        self, _event=None, *, load_slots: bool = True, force: bool = False
    ) -> None:
        if self._suppress_run_select and not force:
            return
        run = self._selected_run()
        if run is None:
            return
        # 同一条已加载：不重写原子表 / 不重刷详情（避免点空白或重复点闪烁）
        if (
            not force
            and run.run_id == self._selected_run_id
            and run.run_id == self._run_ui_loaded_id
        ):
            return
        self._selected_run_id = run.run_id
        if load_slots:
            self._apply_run_slots(run, clear_fails=True)
            self._apply_score_fails_from_run(run)
        self._schedule_save_session()
        lines = [
            f"run_id: {run.run_id}",
            f"video: {'已落盘' if run.video_path.is_file() else '未生成'}",
        ]
        if run.meta:
            lines.append(
                f"参数: {run.meta.get('model')} / {run.meta.get('duration_sec')}s"
                f" / {run.meta.get('rain_label') or run.meta.get('rain_mode') or ''}"
            )
        if run.scores:
            lines.append(f"运动量: {run.scores.get('motion_score', '—')}")
            lines.append(
                f"待人审: {'是' if run.scores.get('needs_human') else '否'}"
            )
            for reason in run.scores.get("dispute_reasons") or []:
                lines.append(f"  ! {reason}")
            # 新格式：L1 画面标签 / L2 动作标签
            l1 = run.scores.get("l1") or {}
            l2 = run.scores.get("l2") or {}
            if l1.get("slots") or l2.get("slots"):
                from scripts.aigc_lab.prompt_atoms import SLOT_LABELS

                def _dump_layer(title: str, layer: dict) -> None:
                    lines.append("")
                    lines.append(title)
                    for sid, tags in (layer.get("slots") or {}).items():
                        label = SLOT_LABELS.get(sid, sid)
                        lines.append(f"  [{label}]")
                        for entry in tags or []:
                            tag = entry.get("tag") or ""
                            short = tag if len(tag) <= 28 else tag[:26] + "…"
                            lines.append(
                                f"    · {entry.get('verdict')} "
                                f"({float(entry.get('confidence') or 0):.2f}) "
                                f"{short}"
                            )
                            note = (entry.get("note") or "").strip()
                            if note:
                                lines.append(f"      {note}")

                _dump_layer("—— L1 画面标签（主体/环境/镜头/风格/约束）——", l1)
                _dump_layer("—— L2 动作标签（动作/约束）——", l2)
            else:
                # 兼容旧 scores.json（槽位级 assertions）
                for aid, entry in (run.scores.get("assertions") or {}).items():
                    lines.append(
                        f"  · {aid}: {entry.get('verdict')} "
                        f"({entry.get('confidence', 0):.2f})"
                    )
        lines.append("")
        lines.append("—— 表格 ——")
        table = (run.meta or {}).get("prompt_table") or ""
        if table:
            lines.append(table)
        else:
            lines.append(run.prompt[:800])
        lines.append("")
        lines.append("—— 送模正文 ——")
        lines.append(run.prompt)
        self._set_detail("\n".join(lines))
        self._run_ui_loaded_id = run.run_id
        if self._on_preview_run:
            video = run.video_path if run.video_path.is_file() else None
            self._on_preview_run(video, run.run_id, slots_from_run(run), kind="t2v")

    def _set_detail(self, text: str) -> None:
        self.txt_detail.delete("1.0", tk.END)
        self.txt_detail.insert("1.0", text)

    def _set_generate_progress(self, pct: int | None) -> None:
        if pct is None:
            self.btn_generate.configure(text=_GENERATE_BTN_LABEL)
        else:
            self.btn_generate.configure(text=f"造梦进度：{pct}%")

    def _run_bg(self, fn: Callable[[], None]) -> None:
        if self._busy:
            return
        self._busy = True
        self._cancel = False
        self.btn_generate.configure(state=tk.DISABLED)

        def wrapper() -> None:
            try:
                fn()
            finally:
                schedule_on_main(self, self._on_bg_done)

        threading.Thread(target=wrapper, daemon=True).start()

    def _on_bg_done(self) -> None:
        self._busy = False
        self._set_generate_progress(None)
        self.btn_generate.configure(state=tk.NORMAL)
        self.refresh()

    def _request_cancel(self) -> None:
        self._cancel = True
        self._log("[AIGC] 已请求停止（当前条目不中断）")

    def _current_rain_mode(self) -> str:
        return normalize_rain_mode(self.rain_var.get())

    def _read_scenes(self) -> list[str]:
        tags = [a for a in self._scene_atoms if a.strip()]
        return tags if tags else list(DEFAULT_SCENES)

    def _write_scenes(self, scenes: list[str]) -> None:
        cleaned = [str(s).strip() for s in scenes if str(s).strip()]
        self._scene_atoms = cleaned if cleaned else list(DEFAULT_SCENES)
        self._scene_last_width = 0
        self._reflow_scene_tags()
        self._schedule_save_session()

    def _build_scene_bar(self, parent: ttk.LabelFrame) -> None:
        """场景总约束：在槽位表外，不进送模。"""
        container = tk.Frame(
            parent,
            bg=self._atom_row_bg,
            highlightthickness=1,
            highlightbackground=self._atom_border,
        )
        container.pack(fill=tk.X, pady=2)
        self._scene_container = container

        add = tk.Frame(container, bg=self._atom_row_bg)
        add.pack(side=tk.RIGHT, anchor="n", padx=(6, 4), pady=4)
        combo = ttk.Combobox(
            add,
            textvariable=self._scene_add_var,
            values=suggest_for_scene(),
            width=14,
        )
        combo.pack(side=tk.LEFT, ipady=1)
        combo.bind("<Return>", lambda _e: self._add_scene_from_entry())
        combo.bind("<<ComboboxSelected>>", lambda _e: self._add_scene_from_entry())
        combo.bind("<KeyRelease>", lambda _e: self._refresh_scene_suggestions())
        combo.bind("<FocusIn>", lambda _e: self._refresh_scene_suggestions())
        self._scene_add_combo = combo
        tk.Button(
            add,
            text="+",
            command=self._add_scene_from_entry,
            relief=tk.FLAT,
            borderwidth=0,
            padx=8,
            pady=1,
            bg=self._atom_tag_bg,
            fg=self._atom_tag_fg,
            activebackground=self._atom_border,
            activeforeground=self._atom_tag_fg,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(4, 0))
        self._scene_add_frame = add

        tags = tk.Frame(container, bg=self._atom_row_bg)
        tags.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=2)
        self._scene_tags_area = tags
        tags.bind("<Configure>", self._on_scene_tags_configure)

    def _build_slot_row(self, table: tk.Frame, slot: str, row: int) -> None:
        """一行结构：左=可换行标签区，右=固定新增区（只建一次）。"""
        container = tk.Frame(
            table,
            bg=self._atom_row_bg,
            highlightthickness=1,
            highlightbackground=self._atom_border,
        )
        container.grid(row=row, column=1, sticky="ew", pady=3, padx=(4, 0))
        self._slot_containers[slot] = container

        add = tk.Frame(container, bg=self._atom_row_bg)
        add.pack(side=tk.RIGHT, anchor="n", padx=(6, 4), pady=4)
        combo = ttk.Combobox(
            add,
            textvariable=self._slot_add_vars[slot],
            values=suggest_for_slot(slot),
            width=14,
        )
        combo.pack(side=tk.LEFT, ipady=1)
        combo.bind("<Return>", lambda _e, s=slot: self._add_atom_from_entry(s))
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _e, s=slot: self._add_atom_from_entry(s),
        )
        combo.bind(
            "<KeyRelease>",
            lambda _e, s=slot: self._refresh_slot_suggestions(s),
        )
        combo.bind(
            "<FocusIn>",
            lambda _e, s=slot: self._refresh_slot_suggestions(s),
        )
        self._slot_add_combos[slot] = combo
        tk.Button(
            add,
            text="+",
            command=lambda s=slot: self._add_atom_from_entry(s),
            relief=tk.FLAT,
            borderwidth=0,
            padx=8,
            pady=1,
            bg=self._atom_tag_bg,
            fg=self._atom_tag_fg,
            activebackground=self._atom_border,
            activeforeground=self._atom_tag_fg,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(4, 0))
        self._slot_add_frames[slot] = add

        tags = tk.Frame(container, bg=self._atom_row_bg)
        tags.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=2)
        self._slot_tags_areas[slot] = tags
        tags.bind(
            "<Configure>",
            lambda e, s=slot: self._on_tags_configure(s, e),
        )

    def _paint_slot_chrome(self) -> None:
        """只刷底色/边框，不重建标签（避免闪烁）。"""
        table = getattr(self, "_atom_table", None)
        if table is not None:
            table.configure(bg=self._atom_row_bg)

        scene_container = getattr(self, "_scene_container", None)
        if scene_container is not None:
            scene_container.configure(
                bg=self._atom_row_bg,
                highlightbackground=self._atom_border,
                highlightcolor=self._atom_border,
            )
        scene_tags = getattr(self, "_scene_tags_area", None)
        if scene_tags is not None:
            scene_tags.configure(bg=self._atom_row_bg)
        scene_add = getattr(self, "_scene_add_frame", None)
        if scene_add is not None:
            scene_add.configure(bg=self._atom_row_bg)
            for child in scene_add.winfo_children():
                if isinstance(child, tk.Button):
                    child.configure(
                        bg=self._atom_tag_bg,
                        fg=self._atom_tag_fg,
                        activebackground=self._atom_border,
                        activeforeground=self._atom_tag_fg,
                    )
            self._refresh_scene_suggestions()

        for slot in SLOT_ORDER:
            container = self._slot_containers.get(slot)
            if container is not None:
                container.configure(
                    bg=self._atom_row_bg,
                    highlightbackground=self._atom_border,
                    highlightcolor=self._atom_border,
                )
            tags = self._slot_tags_areas.get(slot)
            if tags is not None:
                tags.configure(bg=self._atom_row_bg)
            add = self._slot_add_frames.get(slot)
            if add is None:
                continue
            add.configure(bg=self._atom_row_bg)
            for child in add.winfo_children():
                if isinstance(child, tk.Button):
                    child.configure(
                        bg=self._atom_tag_bg,
                        fg=self._atom_tag_fg,
                        activebackground=self._atom_border,
                        activeforeground=self._atom_tag_fg,
                    )
            self._refresh_slot_suggestions(slot)

    def _cancel_pending_reflows(self) -> None:
        for key in SLOT_ORDER:
            pending = self._slot_reflow_after.get(key)
            if pending is not None:
                try:
                    self.after_cancel(pending)
                except tk.TclError:
                    pass
            self._slot_reflow_after[key] = None
        if self._scene_reflow_after is not None:
            try:
                self.after_cancel(self._scene_reflow_after)
            except tk.TclError:
                pass
            self._scene_reflow_after = None

    def _on_scene_tags_configure(self, event=None) -> None:
        if self._layout_frozen or self._scene_reflow_guard:
            return
        if not self._scene_atoms:
            return
        tags = getattr(self, "_scene_tags_area", None)
        if tags is None or (event is not None and event.widget is not tags):
            return
        width = tags.winfo_width()
        if width <= 1:
            return
        if abs(width - self._scene_last_width) < 12:
            return
        if self._scene_reflow_after is not None:
            try:
                self.after_cancel(self._scene_reflow_after)
            except tk.TclError:
                pass
        self._scene_reflow_after = self.after(120, self._reflow_scene_tags)

    def _on_tags_configure(self, slot: str, event=None) -> None:
        if self._layout_frozen or self._reflow_guard.get(slot):
            return
        # 尚无原子时不必重排（避免 Tab 初显空跑一轮）
        if not self._slot_atoms.get(slot):
            return
        tags = self._slot_tags_areas.get(slot)
        if tags is None or (event is not None and event.widget is not tags):
            return
        width = tags.winfo_width()
        if width <= 1:
            return
        if abs(width - self._slot_last_width.get(slot, 0)) < 12:
            return
        pending = self._slot_reflow_after.get(slot)
        if pending is not None:
            try:
                self.after_cancel(pending)
            except tk.TclError:
                pass
        self._slot_reflow_after[slot] = self.after(
            120, lambda s=slot: self._reflow_tags(s)
        )

    def _is_fail_tag(self, slot: str, text: str) -> bool:
        return text in (self._slot_fail_tags.get(slot) or set())

    def _tag_border_color(self, *, failed: bool) -> str:
        return _FAIL_BORDER if failed else self._atom_border

    def _toggle_fail_tag(self, slot: str, text: str) -> None:
        fails = self._slot_fail_tags.setdefault(slot, set())
        if text in fails:
            fails.discard(text)
            self._log(f"[AIGC] 取消可疑标记：[{SLOT_LABELS.get(slot, slot)}] {text}")
        else:
            fails.add(text)
            self._log(f"[AIGC] 标可疑：[{SLOT_LABELS.get(slot, slot)}] {text}")
        outer = self._slot_tag_widgets.get(slot, {}).get(text)
        if outer is not None:
            try:
                if outer.winfo_exists():
                    outer.configure(bg=self._tag_border_color(failed=text in fails))
                    self._schedule_save_session()
                    return
            except tk.TclError:
                pass
        self._reflow_tags(slot)
        self._schedule_save_session()

    def _format_tag_display(self, text: str) -> str:
        t = text.strip()
        if len(t) <= _TAG_DISPLAY_MAX_CHARS:
            return t
        return t[: _TAG_DISPLAY_MAX_CHARS - 1] + "…"

    def _populate_tag_inner(
        self,
        inner: tk.Frame,
        text: str,
        *,
        on_delete: Callable[[], None],
    ) -> tk.Label:
        """标签正文 + ×；超长正文省略，× 固定在最右侧。"""
        display = self._format_tag_display(text)
        btn = tk.Button(
            inner,
            text="×",
            command=on_delete,
            relief=tk.FLAT,
            borderwidth=0,
            padx=4,
            pady=0,
            bg=self._atom_tag_bg,
            fg=self._atom_tag_fg,
            activebackground=self._atom_border,
            activeforeground=self._atom_tag_fg,
            cursor="hand2",
            font=("", 10, "bold"),
        )
        btn.pack(side=tk.RIGHT)
        lbl = tk.Label(
            inner,
            text=display,
            bg=self._atom_tag_bg,
            fg=self._atom_tag_fg,
            padx=6,
            pady=2,
            anchor="w",
            cursor="hand2",
        )
        lbl.pack(side=tk.LEFT)
        return lbl

    def _bind_tag_drag(
        self,
        widgets: tuple[tk.Misc, ...],
        *,
        kind: str,
        index: int,
        text: str,
        slot: str | None = None,
    ) -> None:
        """标签正文可拖动换序；槽位标签短按仍可切换红框。"""
        for widget in widgets:
            widget.bind(
                "<ButtonPress-1>",
                lambda e, k=kind, s=slot, i=index, t=text: self._on_tag_drag_press(
                    e, kind=k, slot=s, index=i, text=t
                ),
                add="+",
            )
            widget.bind(
                "<B1-Motion>",
                self._on_tag_drag_motion,
                add="+",
            )
            widget.bind(
                "<ButtonRelease-1>",
                self._on_tag_drag_release,
                add="+",
            )

    def _on_tag_drag_press(
        self,
        event,
        *,
        kind: str,
        slot: str | None,
        index: int,
        text: str,
    ) -> None:
        self._destroy_drag_ghost()
        self._tag_drag = {
            "kind": kind,
            "slot": slot,
            "index": index,
            "text": text,
            "start_x": int(event.x_root),
            "start_y": int(event.y_root),
            "dragging": False,
            "bound_all": False,
        }

    def _on_tag_drag_motion(self, event) -> None:
        drag = self._tag_drag
        if drag is None:
            return
        x_root = int(event.x_root)
        y_root = int(event.y_root)
        if not drag["dragging"]:
            dx = abs(x_root - int(drag["start_x"]))
            dy = abs(y_root - int(drag["start_y"]))
            if max(dx, dy) < _TAG_DRAG_THRESHOLD_PX:
                return
            self._begin_tag_drag(x_root=x_root, y_root=y_root)
        self._move_drag_ghost(x_root=x_root, y_root=y_root)

    def _on_tag_drag_release(self, event) -> None:
        drag = self._tag_drag
        if drag is None:
            return
        was_dragging = bool(drag.get("dragging"))
        kind = str(drag.get("kind") or "")
        slot = drag.get("slot")
        text = str(drag.get("text") or "")
        x_root = int(getattr(event, "x_root", 0) or 0)
        y_root = int(getattr(event, "y_root", 0) or 0)
        if not was_dragging:
            self._end_tag_drag()
            if kind == "slot" and slot:
                self._toggle_fail_tag(str(slot), text)
            return
        # 松手时再重排一次，拖动过程不 reflow，避免整表闪烁
        atoms = self._tag_atoms_for(kind=kind, slot=slot if isinstance(slot, str) else None)
        try:
            from_index = atoms.index(text)
        except ValueError:
            from_index = int(drag.get("index") or 0)
        to_index = self._tag_drop_index(
            kind=kind,
            slot=slot if isinstance(slot, str) else None,
            x_root=x_root,
            y_root=y_root,
            ignore_text=text,
        )
        self._paint_drag_source_border(active=False)
        self._end_tag_drag()
        self._reorder_tags(
            kind=kind,
            slot=slot if isinstance(slot, str) else None,
            from_index=from_index,
            to_index=to_index,
            persist=True,
        )

    def _begin_tag_drag(self, *, x_root: int, y_root: int) -> None:
        drag = self._tag_drag
        if drag is None or drag.get("dragging"):
            return
        drag["dragging"] = True
        try:
            self.configure(cursor="fleur")
        except tk.TclError:
            pass
        self._paint_drag_source_border(active=True)
        self._create_drag_ghost(x_root=x_root, y_root=y_root)
        # 拖出原标签后仍需收到移动/松手事件
        if not drag.get("bound_all"):
            self.bind_all("<B1-Motion>", self._on_tag_drag_motion, add="+")
            self.bind_all("<ButtonRelease-1>", self._on_tag_drag_release, add="+")
            drag["bound_all"] = True

    def _end_tag_drag(self) -> None:
        drag = self._tag_drag
        self._tag_drag = None
        if drag and drag.get("bound_all"):
            try:
                self.unbind_all("<B1-Motion>")
            except tk.TclError:
                pass
            try:
                self.unbind_all("<ButtonRelease-1>")
            except tk.TclError:
                pass
        self._destroy_drag_ghost()
        try:
            self.configure(cursor="")
        except tk.TclError:
            pass

    def _drag_source_outer(self) -> tk.Frame | None:
        drag = self._tag_drag
        if drag is None:
            return None
        text = str(drag.get("text") or "")
        if not text:
            return None
        if drag.get("kind") == "scene":
            return self._scene_tag_widgets.get(text)
        slot = drag.get("slot")
        if not slot:
            return None
        return (self._slot_tag_widgets.get(str(slot)) or {}).get(text)

    def _paint_drag_source_border(self, *, active: bool) -> None:
        drag = self._tag_drag
        outer = self._drag_source_outer()
        if outer is None:
            return
        try:
            if not outer.winfo_exists():
                return
            if active:
                outer.configure(bg=_DRAG_BORDER)
                return
            if drag and drag.get("kind") == "slot":
                slot = str(drag.get("slot") or "")
                text = str(drag.get("text") or "")
                failed = self._is_fail_tag(slot, text)
                outer.configure(bg=self._tag_border_color(failed=failed))
            else:
                outer.configure(bg=self._atom_border)
        except tk.TclError:
            pass

    def _create_drag_ghost(self, *, x_root: int, y_root: int) -> None:
        drag = self._tag_drag
        if drag is None:
            return
        self._destroy_drag_ghost()
        text = str(drag.get("text") or "")
        ghost = tk.Toplevel(self)
        ghost.overrideredirect(True)
        try:
            ghost.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            ghost.attributes("-alpha", 0.92)
        except tk.TclError:
            pass
        outer = tk.Frame(
            ghost,
            bg=_DRAG_BORDER,
            padx=_TAG_BORDER_THICKNESS + 1,
            pady=_TAG_BORDER_THICKNESS + 1,
        )
        outer.pack()
        inner = tk.Frame(outer, bg=self._atom_tag_bg)
        inner.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            inner,
            text=self._format_tag_display(text),
            bg=self._atom_tag_bg,
            fg=self._atom_tag_fg,
            padx=6,
            pady=2,
        ).pack()
        self._tag_drag_ghost = ghost
        self._move_drag_ghost(x_root=x_root, y_root=y_root)

    def _move_drag_ghost(self, *, x_root: int, y_root: int) -> None:
        ghost = self._tag_drag_ghost
        if ghost is None:
            return
        try:
            if not ghost.winfo_exists():
                self._tag_drag_ghost = None
                return
            ghost.geometry(f"+{x_root + 12}+{y_root + 10}")
        except tk.TclError:
            self._tag_drag_ghost = None

    def _destroy_drag_ghost(self) -> None:
        ghost = self._tag_drag_ghost
        self._tag_drag_ghost = None
        if ghost is None:
            return
        try:
            ghost.destroy()
        except tk.TclError:
            pass

    def _tag_widgets_for(self, *, kind: str, slot: str | None) -> dict[str, tk.Frame]:
        if kind == "scene":
            return self._scene_tag_widgets
        if slot:
            return self._slot_tag_widgets.get(slot) or {}
        return {}

    def _tag_atoms_for(self, *, kind: str, slot: str | None) -> list[str]:
        if kind == "scene":
            return list(self._scene_atoms)
        if slot:
            return list(self._slot_atoms.get(slot) or [])
        return []

    def _tag_drop_index(
        self,
        *,
        kind: str,
        slot: str | None,
        x_root: int,
        y_root: int,
        ignore_text: str | None = None,
    ) -> int:
        """根据指针位置计算插入下标（0..len）。"""
        atoms = self._tag_atoms_for(kind=kind, slot=slot)
        widgets = self._tag_widgets_for(kind=kind, slot=slot)
        if not atoms:
            return 0
        # 拖动中忽略自身，避免落点抖动
        candidates = [
            (i, atom)
            for i, atom in enumerate(atoms)
            if not ignore_text or atom != ignore_text
        ]
        # 先找命中标签：左半插入该位，右半插入其后
        for i, atom in candidates:
            widget = widgets.get(atom)
            if widget is None:
                continue
            try:
                if not widget.winfo_exists():
                    continue
                x0 = widget.winfo_rootx()
                y0 = widget.winfo_rooty()
                x1 = x0 + max(widget.winfo_width(), 1)
                y1 = y0 + max(widget.winfo_height(), 1)
            except tk.TclError:
                continue
            if x0 <= x_root <= x1 and y0 <= y_root <= y1:
                return i if x_root < (x0 + x1) / 2 else i + 1
        # 回退：按阅读顺序找最近中心点
        best_i = len(atoms)
        best_d = float("inf")
        for i, atom in candidates:
            widget = widgets.get(atom)
            if widget is None:
                continue
            try:
                if not widget.winfo_exists():
                    continue
                mid_x = widget.winfo_rootx() + max(widget.winfo_width(), 1) / 2
                mid_y = widget.winfo_rooty() + max(widget.winfo_height(), 1) / 2
            except tk.TclError:
                continue
            dist = (mid_y - y_root) ** 2 + (mid_x - x_root) ** 2
            if dist < best_d:
                best_d = dist
                best_i = i if x_root < mid_x else i + 1
        return max(0, min(best_i, len(atoms)))

    def _reorder_tags(
        self,
        *,
        kind: str,
        slot: str | None,
        from_index: int,
        to_index: int,
        persist: bool = True,
    ) -> bool:
        atoms = self._tag_atoms_for(kind=kind, slot=slot)
        if from_index < 0 or from_index >= len(atoms):
            return False
        insert_at = to_index
        if insert_at > from_index:
            insert_at -= 1
        insert_at = max(0, min(insert_at, len(atoms) - 1))
        if insert_at == from_index:
            return False
        item = atoms.pop(from_index)
        atoms.insert(insert_at, item)
        if kind == "scene":
            self._scene_atoms = atoms
            self._reflow_scene_tags()
        elif slot:
            self._slot_atoms[slot] = atoms
            self._reflow_tags(slot)
        if persist:
            self._schedule_save_session()
        return True

    def _clear_fail_marks(self) -> None:
        self._slot_fail_tags = {key: set() for key in SLOT_ORDER}

    def _set_fail_marks_for_current_ui(self, failed: dict[str, list[str]]) -> None:
        """仅对当前标签表中已存在的标签标红，不增删改标签。"""
        self._clear_fail_marks()
        for key in SLOT_ORDER:
            current = {
                t.strip()
                for t in (self._slot_atoms.get(key) or [])
                if str(t).strip()
            }
            for tag in failed.get(key) or []:
                t = str(tag).strip()
                if t and t in current:
                    self._slot_fail_tags[key].add(t)

    def _refresh_slot_suggestions(self, slot: str) -> None:
        combo = self._slot_add_combos.get(slot)
        if combo is None:
            return
        prefix = self._slot_add_vars[slot].get()
        combo.configure(values=suggest_for_slot(slot, prefix))

    def _refresh_scene_suggestions(self) -> None:
        combo = self._scene_add_combo
        if combo is None:
            return
        combo.configure(values=suggest_for_scene(self._scene_add_var.get()))

    def _refresh_all_suggestions(self) -> None:
        self._refresh_scene_suggestions()
        for key in SLOT_ORDER:
            self._refresh_slot_suggestions(key)

    def _make_scene_tag(self, parent: tk.Frame, text: str, index: int) -> tk.Frame:
        outer = tk.Frame(
            parent,
            bg=self._atom_border,
            padx=_TAG_BORDER_THICKNESS,
            pady=_TAG_BORDER_THICKNESS,
            highlightthickness=0,
            cursor="hand2",
        )
        self._scene_tag_widgets[text] = outer
        inner = tk.Frame(outer, bg=self._atom_tag_bg, cursor="hand2")
        inner.pack(fill=tk.BOTH, expand=True)
        lbl = self._populate_tag_inner(
            inner,
            text,
            on_delete=lambda i=index: self._remove_scene(i),
        )
        self._bind_tag_drag(
            (outer, inner, lbl),
            kind="scene",
            index=index,
            text=text,
        )
        return outer

    def _remove_scene(self, index: int) -> None:
        atoms = list(self._scene_atoms)
        if index < 0 or index >= len(atoms):
            return
        if len(atoms) <= 1:
            self._log("[AIGC] 至少保留一个场景标签")
            return
        atoms.pop(index)
        self._scene_atoms = atoms
        self._reflow_scene_tags()
        self._schedule_save_session()

    def _add_scene_from_entry(self) -> None:
        text = self._scene_add_var.get().strip()
        if not text:
            return
        atoms = list(self._scene_atoms)
        if text not in atoms:
            atoms.append(text)
            merge_scenes_into_pool([text])
        self._scene_atoms = atoms
        self._scene_add_var.set("")
        self._refresh_scene_suggestions()
        self._reflow_scene_tags()
        self._schedule_save_session()

    def _reflow_scene_tags(self) -> None:
        tags_area = getattr(self, "_scene_tags_area", None)
        if tags_area is None:
            return
        if self._scene_reflow_guard:
            return
        self._scene_reflow_guard = True
        self._scene_reflow_after = None
        self._scene_tag_widgets = {}
        try:
            for child in list(tags_area.winfo_children()):
                try:
                    child.destroy()
                except tk.TclError:
                    pass

            tags_area.configure(bg=self._atom_row_bg)
            atoms = [a for a in self._scene_atoms if a.strip()]
            if not atoms:
                atoms = list(DEFAULT_SCENES)
            self._scene_atoms = atoms

            width = tags_area.winfo_width()
            if width <= 1:
                width = 360
            max_w = max(width - 6, 120)
            pad = 6

            row = tk.Frame(tags_area, bg=self._atom_row_bg)
            row.pack(fill=tk.X, anchor="w")
            row_w = 0

            for i, text in enumerate(atoms):
                tag = self._make_scene_tag(row, text, i)
                tag.pack(side=tk.LEFT, padx=(0, pad), pady=2)
                tag.update_idletasks()
                cw = max(tag.winfo_reqwidth(), 24) + pad
                if row_w > 0 and row_w + cw > max_w:
                    tag.destroy()
                    row = tk.Frame(tags_area, bg=self._atom_row_bg)
                    row.pack(fill=tk.X, anchor="w")
                    row_w = 0
                    tag = self._make_scene_tag(row, text, i)
                    tag.pack(side=tk.LEFT, padx=(0, pad), pady=2)
                    tag.update_idletasks()
                    cw = max(tag.winfo_reqwidth(), 24) + pad
                row_w += cw

            self._scene_last_width = (
                tags_area.winfo_width() if tags_area.winfo_width() > 1 else width
            )
        finally:
            self._scene_reflow_guard = False
        self._sync_scroll_region()

    def _make_tag(self, parent: tk.Frame, slot: str, text: str, index: int) -> tk.Frame:
        failed = self._is_fail_tag(slot, text)
        outer = tk.Frame(
            parent,
            bg=self._tag_border_color(failed=failed),
            padx=_TAG_BORDER_THICKNESS,
            pady=_TAG_BORDER_THICKNESS,
            highlightthickness=0,
            cursor="hand2",
        )
        self._slot_tag_widgets.setdefault(slot, {})[text] = outer
        inner = tk.Frame(outer, bg=self._atom_tag_bg, cursor="hand2")
        inner.pack(fill=tk.BOTH, expand=True)
        lbl = self._populate_tag_inner(
            inner,
            text,
            on_delete=lambda s=slot, i=index: self._remove_atom(s, i),
        )
        # 单击标签正文 → 切换不合格；拖动 → 同槽改序；× 仍负责删除
        self._bind_tag_drag(
            (outer, inner, lbl),
            kind="slot",
            slot=slot,
            index=index,
            text=text,
        )
        return outer

    def _remove_atom(self, slot: str, index: int) -> None:
        atoms = list(self._slot_atoms.get(slot) or [])
        if index < 0 or index >= len(atoms):
            return
        removed = atoms.pop(index)
        self._slot_atoms[slot] = atoms
        self._slot_fail_tags.get(slot, set()).discard(removed)
        self._reflow_tags(slot)
        self._schedule_save_session()

    def _add_atom_from_entry(self, slot: str) -> None:
        var = self._slot_add_vars.get(slot)
        if var is None:
            return
        text = var.get().strip()
        if not text:
            return
        atoms = list(self._slot_atoms.get(slot) or [])
        if text not in atoms:
            atoms.append(text)
        self._slot_atoms[slot] = atoms
        var.set("")
        self._refresh_slot_suggestions(slot)
        self._reflow_tags(slot)
        self._schedule_save_session()

    def _reflow_tags(self, slot: str) -> None:
        """只重建左侧标签区；右侧新增框不动。"""
        tags_area = self._slot_tags_areas.get(slot)
        if tags_area is None:
            return
        if self._reflow_guard.get(slot):
            return
        self._reflow_guard[slot] = True
        self._slot_reflow_after[slot] = None
        self._slot_tag_widgets[slot] = {}
        try:
            for child in list(tags_area.winfo_children()):
                try:
                    child.destroy()
                except tk.TclError:
                    pass

            tags_area.configure(bg=self._atom_row_bg)
            atoms = [a for a in (self._slot_atoms.get(slot) or []) if a.strip()]
            self._slot_atoms[slot] = atoms

            width = tags_area.winfo_width()
            if width <= 1:
                width = 360
            max_w = max(width - 6, 120)
            pad = 6

            row = tk.Frame(tags_area, bg=self._atom_row_bg)
            row.pack(fill=tk.X, anchor="w")
            row_w = 0

            for i, text in enumerate(atoms):
                tag = self._make_tag(row, slot, text, i)
                tag.pack(side=tk.LEFT, padx=(0, pad), pady=2)
                tag.update_idletasks()
                cw = max(tag.winfo_reqwidth(), 24) + pad
                if row_w > 0 and row_w + cw > max_w:
                    tag.destroy()
                    row = tk.Frame(tags_area, bg=self._atom_row_bg)
                    row.pack(fill=tk.X, anchor="w")
                    row_w = 0
                    tag = self._make_tag(row, slot, text, i)
                    tag.pack(side=tk.LEFT, padx=(0, pad), pady=2)
                    tag.update_idletasks()
                    cw = max(tag.winfo_reqwidth(), 24) + pad
                row_w += cw

            self._slot_last_width[slot] = (
                tags_area.winfo_width() if tags_area.winfo_width() > 1 else width
            )
        finally:
            self._reflow_guard[slot] = False
        self._sync_scroll_region()

    def _render_slot_atoms(self, slot: str, atoms: list[str]) -> None:
        self._slot_atoms[slot] = [str(a).strip() for a in atoms if str(a).strip()]
        self._slot_last_width[slot] = 0
        self._reflow_tags(slot)

    def _read_slots(self) -> dict[str, list[str]]:
        """原样读取当前标签表（不钳制、不补默认，尊重用户删改）。"""
        return {
            key: [a for a in (self._slot_atoms.get(key) or []) if a.strip()]
            for key in SLOT_ORDER
        }

    def _write_slots(
        self,
        slots: dict[str, list[str]],
        *,
        clear_fails: bool = True,
    ) -> None:
        self._cancel_pending_reflows()
        if clear_fails:
            self._clear_fail_marks()
        cleaned = {
            key: [str(a).strip() for a in (slots.get(key) or []) if str(a).strip()]
            for key in SLOT_ORDER
        }
        # 内容完全一致时只清红框，不销毁重建标签
        if cleaned == self._read_slots():
            if clear_fails:
                self._sync_fail_borders()
            self._schedule_save_session()
            return
        self._layout_frozen = True
        for key in SLOT_ORDER:
            self._slot_atoms[key] = cleaned[key]
            self._slot_last_width[key] = 0
            self._reflow_tags(key)
        self.update_idletasks()
        for key in SLOT_ORDER:
            area = self._slot_tags_areas.get(key)
            if area is not None and area.winfo_width() > 1:
                self._slot_last_width[key] = area.winfo_width()
        # 推迟解冻，吞掉本轮重建触发的 Configure，避免第二波闪烁
        self.after(180, self._unfreeze_layout)
        self._refresh_all_suggestions()
        self._schedule_save_session()
        self._sync_scroll_region()

    def _unfreeze_layout(self) -> None:
        self._layout_frozen = False
        for key in SLOT_ORDER:
            area = self._slot_tags_areas.get(key)
            if area is not None and area.winfo_width() > 1:
                self._slot_last_width[key] = area.winfo_width()

    def _model_prompt(self) -> str:
        return compose_prompt(self._read_slots())

    def _on_rain_mode_changed(self) -> None:
        """雨档变更：只同步固定闭集槽（音频等），开放三槽不动。"""
        self._sync_locked_slots_for_rain()
        label = RAIN_MODE_LABELS[self._current_rain_mode()]
        self._log(f"[AIGC] 雨档 → {label}（已更新镜头/风格/约束固定项）")

    def _apply_locked_slots_only(self) -> None:
        """首启无 session：只铺固定闭集槽，开放三槽留空待 LLM 生成。"""
        self._sync_locked_slots_for_rain()

    def _sync_locked_slots_for_rain(self) -> None:
        locked = product_locked_closed_slots(self._current_rain_mode())
        for key in LOCKED_SLOTS:
            self._slot_atoms[key] = list(locked[key])
            self._slot_last_width[key] = 0
            self._reflow_tags(key)
        self._schedule_save_session()

    def _start_llm_baseline(self) -> None:
        if self._busy:
            return
        mode = self._current_rain_mode()
        scenes = self._read_scenes()

        def job() -> None:
            try:
                slots, email = rewrite_atomic(
                    "",
                    rain_mode=mode,
                    scenes=scenes,
                    log_fn=lambda m: schedule_on_main(self, self._log, m),
                )
                schedule_on_main(self, self._apply_llm_baseline, slots, email)
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._log, f"[AIGC] LLM生成基线失败：{exc}")

        self._log(
            f"[AIGC] LLM生成基线中… 场景={format_scenes(scenes)} · "
            f"{RAIN_MODE_LABELS[mode]}"
        )
        self._run_bg(job)

    def _apply_llm_baseline(self, slots: dict[str, list[str]], email: str) -> None:
        self._write_slots(slots)
        self._log(
            f"[AIGC] LLM生成基线完成（场景={format_scenes(self._read_scenes())}；"
            f"主体/动作/环境由 LLM 生成；镜头/风格/约束固定） · {email}"
        )
        self._log(f"[AIGC] 送模正文预览：{compose_prompt(slots)}")

    def _start_llm_replace(self) -> None:
        if self._busy:
            return
        failed = {
            key: sorted(self._slot_fail_tags.get(key) or set())
            for key in SLOT_ORDER
        }
        if not any(failed.values()):
            messagebox.showinfo("AIGC", "没有红框可疑标签。请先 VLM 标记或单击标签标红。")
            return
        mode = self._current_rain_mode()
        scenes = self._read_scenes()
        slots = self._read_slots()

        def job() -> None:
            try:
                new_slots, email = replace_failed_atoms(
                    slots,
                    failed,
                    rain_mode=mode,
                    scenes=scenes,
                    log_fn=lambda m: schedule_on_main(self, self._log, m),
                )
                schedule_on_main(
                    self, self._apply_llm_replace, new_slots, failed, email
                )
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._log, f"[AIGC] LLM替换可疑标签失败：{exc}")

        self._log(
            f"[AIGC] LLM替换可疑标签中… 场景={format_scenes(scenes)}\n"
            f"{format_tags_by_slot(failed)}"
        )
        self._run_bg(job)

    def _apply_llm_replace(
        self,
        slots: dict[str, list[str]],
        old_failed: dict[str, list[str]],
        email: str,
    ) -> None:
        self._write_slots(slots, clear_fails=True)
        # 若替换未成功、旧标签仍在，则继续标红
        remaining: dict[str, list[str]] = {key: [] for key in SLOT_ORDER}
        for key in SLOT_ORDER:
            current = set(slots.get(key) or [])
            for tag in old_failed.get(key) or []:
                if tag in current:
                    remaining[key].append(tag)
        if any(remaining.values()):
            self._set_fail_marks_for_current_ui(remaining)
            self._sync_fail_borders()
        self._log(f"[AIGC] LLM替换可疑标签完成 · {email}")
        self._log(f"[AIGC] 送模正文预览：{compose_prompt(slots)}")
        self._schedule_save_session()

    def _preview_model_prompt(self) -> None:
        slots = self._read_slots()
        prompt = compose_prompt(slots)
        if not prompt:
            messagebox.showinfo("AIGC", "各槽为空，无送模正文。")
            return
        self._log(f"[AIGC] 送模正文：{prompt}")
        fail_lines: list[str] = []
        for key in SLOT_ORDER:
            fails = sorted(self._slot_fail_tags.get(key) or set())
            if fails:
                fail_lines.append(
                    f"{SLOT_LABELS.get(key, key)}：{' · '.join(fails)}"
                )
        detail = (
            f"—— 场景（指导 LLM，不进送模）——\n"
            f"{format_scenes(self._read_scenes())}\n\n"
            "—— 当前表格（以标签表为准）——\n"
            + format_table(slots)
            + "\n\n—— 送模正文 ——\n"
            + prompt
        )
        if fail_lines:
            detail += "\n\n—— 已标不合格（红框，入池时排除）——\n" + "\n".join(
                fail_lines
            )
        self._set_detail(detail)

    def _qualified_tags_from_ui(self) -> dict[str, list[str]]:
        """当前表中未标红的标签 = 人工合格候选。"""
        out: dict[str, list[str]] = {key: [] for key in SLOT_ORDER}
        for key in SLOT_ORDER:
            fails = self._slot_fail_tags.get(key) or set()
            for tag in self._slot_atoms.get(key) or []:
                t = tag.strip()
                if t and t not in fails:
                    out[key].append(t)
        return out

    def _confirm_and_merge_pools(
        self,
        candidates: dict[str, list[str]],
        *,
        source: str,
    ) -> None:
        cleaned = {
            k: [t for t in (candidates.get(k) or []) if t.strip()]
            for k in SLOT_ORDER
        }
        if not any(cleaned.values()):
            messagebox.showinfo("AIGC", "没有可入池的合格标签。")
            return
        body = format_tags_by_slot(cleaned)
        self._log(f"[AIGC] 拟入池（{source}）：\n{body}")
        ok = messagebox.askyesno(
            "合格标签入池",
            f"来源：{source}\n\n以下标签将合入本地学习池"
            f"（aigc/t2v_lab/learned_pools.json）。\n\n{body}\n\n确认合入？",
        )
        if not ok:
            self._log("[AIGC] 已取消入池")
            return
        added, updated, _pools = merge_into_pools(cleaned)
        if not any(added.values()) and not any(updated.values()):
            self._log("[AIGC] 入池完成：无有效标签")
            messagebox.showinfo("AIGC", "没有可合入的有效标签。")
        else:
            parts: list[str] = []
            if any(added.values()):
                parts.append(f"新增：\n{format_tags_by_slot(added)}")
            if any(updated.values()):
                parts.append(f"覆盖（已去重）：\n{format_tags_by_slot(updated)}")
            summary = "\n\n".join(parts)
            self._log(f"[AIGC] 已入池：\n{summary}")
            messagebox.showinfo("AIGC", f"已合入学习池：\n\n{summary}")
        self._refresh_all_suggestions()

    def _parse_duration_sec(self) -> int:
        try:
            return max(1, min(15, int(self.spin_duration.get())))
        except (ValueError, tk.TclError, AttributeError):
            return 4

    def _persist_duration_sec(self) -> None:
        dur = self._parse_duration_sec()
        try:
            self.spin_duration.set(str(dur))
            save_lab_params({"duration_sec": dur})
        except OSError:
            pass

    def _parse_generate_count(self) -> int:
        try:
            return max(1, min(10, int(self.spin_generate_count.get())))
        except (ValueError, tk.TclError, AttributeError):
            return 1

    def _persist_generate_count(self) -> None:
        n = self._parse_generate_count()
        try:
            self.spin_generate_count.set(str(n))
            save_lab_params({"generate_count": n})
        except OSError:
            pass

    def _pool_qualified_manual(self) -> None:
        """人工：红框外的标签入池（先标完不合格再点）。"""
        self._confirm_and_merge_pools(
            self._qualified_tags_from_ui(),
            source="人工确认（排除红框不合格）",
        )

    def _apply_score_to_ui(self, run_id: str) -> None:
        """评分结束后：仅红框标可疑；入池只走人工「合格标签入池」。"""
        try:
            run = load_run(run_id)
        except Exception as exc:  # noqa: BLE001
            self._log(f"[AIGC] 加载评分结果失败：{exc}")
            return
        scores = run.scores or {}
        failed = failed_tags_from_scores(scores)
        qualified = qualified_tags_from_scores(scores)

        self._apply_score_fails_from_run(run)
        self._schedule_save_session()

        fail_body = format_tags_by_slot(failed)
        yes_body = format_tags_by_slot(qualified)
        self._log(f"[AIGC] VLM 可疑（已红框）：\n{fail_body}")
        self._log(
            f"[AIGC] VLM 合格候选（不自动入池，需点「合格标签入池」）：\n{yes_body}"
        )
        self.refresh()
        # 选中刚评的 run，刷新详情
        self._selected_run_id = run_id
        for i, r in enumerate(self._runs):
            if r.run_id == run_id:
                self.list_runs.selection_clear(0, tk.END)
                self.list_runs.selection_set(i)
                self.list_runs.see(i)
                break
        self._on_run_select(load_slots=False, force=True)

    def _start_jimeng_login(self) -> None:
        if self._busy:
            return

        def job() -> None:
            try:
                ensure_cli_path()
                from jimeng_web.client import JimengWebClient

                st = JimengWebClient().interactive_login(
                    log=lambda m: schedule_on_main(self, self._log, m)
                )
                schedule_on_main(
                    self, self._log, f"[即梦] 登录完成：{st.detail}"
                )
                schedule_on_main(
                    self,
                    self._set_jimeng_login_button,
                    logged_in=st.is_logged_in,
                )
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._log, f"[即梦] 登录失败：{exc}")

        self._run_bg(job)

    def _focus_run(self, run_id: str, *, load_slots: bool = False) -> None:
        """选中指定实验记录并刷新详情/预览。"""
        rid = str(run_id or "").strip()
        if not rid:
            return
        self._selected_run_id = rid
        self.refresh()
        if not self.list_runs.curselection():
            return
        self._on_run_select(load_slots=load_slots, force=True)

    def _auto_vlm_mark(self, run_id: str) -> None:
        """后台 VLM 标记可疑标签（生成完成后自动调用）。"""
        rid = str(run_id or "").strip()
        if not rid:
            return
        try:
            score_run(
                rid,
                log_fn=lambda m: schedule_on_main(self, self._log, m),
            )
            schedule_on_main(self, self._apply_score_to_ui, rid)
        except ScoreError as exc:
            schedule_on_main(self, self._log, f"[AIGC] 自动 VLM 标记失败：{exc}")
        except Exception as exc:  # noqa: BLE001
            schedule_on_main(self, self._log, f"[AIGC] 自动 VLM 标记异常：{exc}")

    def _show_tag_preflight_issues(
        self,
        report: dict[str, list[dict[str, object]]],
        prepared: dict[str, object],
    ) -> None:
        """展示生成前冲突/重复检查；冲突标签标红，用户决定是否继续。"""
        conflicts = report.get("conflicts") or []
        duplicates = report.get("duplicates") or []
        marked: dict[str, list[str]] = {
            key: list(self._slot_fail_tags.get(key) or set()) for key in SLOT_ORDER
        }
        conflict_lines: list[str] = []
        for conflict in conflicts:
            refs = conflict.get("tags") or []
            labels: list[str] = []
            for ref in refs:
                if not isinstance(ref, dict):
                    continue
                slot = str(ref.get("slot") or "").strip()
                tag = str(ref.get("tag") or "").strip()
                if slot not in marked or not tag:
                    continue
                if tag not in marked[slot]:
                    marked[slot].append(tag)
                labels.append(f"[{SLOT_LABELS.get(slot, slot)}] {tag}")
            reason = str(conflict.get("reason") or "标签描述互相矛盾").strip()
            if labels:
                conflict_lines.append(f"• {' ↔ '.join(labels)}\n  {reason}")
        if conflict_lines:
            self._set_fail_marks_for_current_ui(marked)
            self._sync_fail_borders()

        duplicate_lines: list[str] = []
        for duplicate in duplicates:
            labels: list[str] = []
            for ref in duplicate.get("tags") or []:
                if not isinstance(ref, dict):
                    continue
                slot = str(ref.get("slot") or "").strip()
                tag = str(ref.get("tag") or "").strip()
                if slot and tag:
                    labels.append(f"[{SLOT_LABELS.get(slot, slot)}] {tag}")
            reason = str(duplicate.get("reason") or "表达的信息重复").strip()
            if labels:
                duplicate_lines.append(f"• {' ↔ '.join(labels)}\n  {reason}")
        self._schedule_save_session()
        parts: list[str] = []
        if conflict_lines:
            parts.append("【互相矛盾（已标红）】\n" + "\n".join(conflict_lines))
        if duplicate_lines:
            parts.append("【重复描述】\n" + "\n".join(duplicate_lines))
        body = "\n\n".join(parts) or "检测到标签检查问题。"
        self._log(f"[AIGC] 生成前标签检查提示：\n{body}")
        should_continue = messagebox.askyesno(
            "标签检查提示",
            f"{body}\n\n是否继续造梦？\n"
            "选择「是」继续造梦；选择「否」返回修改。",
            icon=messagebox.WARNING,
        )
        if should_continue:
            self._log("[AIGC] 已确认忽略本次标签检查提示，继续造梦")
            # 让预检后台任务先释放 _busy，再启动真正的生成任务。
            self.after(
                75,
                lambda: self._start_generate(skip_preflight=True, prepared=prepared),
            )
        else:
            self._log("[AIGC] 已返回修改标签，未提交造梦")

    def _start_generate(
        self,
        *,
        skip_preflight: bool = False,
        prepared: dict[str, object] | None = None,
    ) -> None:
        if prepared is None:
            slots = self._read_slots()
            prompt = compose_prompt(slots)
            table = format_table(slots)
            n = self._parse_generate_count()
            mode = self._current_rain_mode()
            scenes = self._read_scenes()
            prepared = {
                "slots": slots,
                "prompt": prompt,
                "table": table,
                "n": n,
                "mode": mode,
                "scenes": scenes,
            }
        else:
            slots = prepared["slots"]  # type: ignore[assignment]
            prompt = str(prepared["prompt"])
            table = str(prepared["table"])
            n = int(prepared["n"])
            mode = str(prepared["mode"])
            scenes = prepared["scenes"]  # type: ignore[assignment]
        if not prompt:
            messagebox.showwarning("AIGC", "请先填写原子表。")
            return
        if not skip_preflight:
            self._persist_generate_count()

        def job() -> None:
            ensure_cli_path()
            from jimeng_web.client import JimengWebClient, JimengWebError

            duration = self._parse_duration_sec()
            schedule_on_main(self, self._persist_duration_sec)
            params = lab_params()
            model = params.get("model", "Seedance 2.0 Fast VIP")

            if not skip_preflight:
                schedule_on_main(self, self._log, "[AIGC] 生成前 LLM 检查标签冲突/重复…")
                try:
                    report, email = check_tag_conflicts(
                        slots,
                        rain_mode=mode,
                        scenes=scenes,
                        log_fn=lambda m: schedule_on_main(self, self._log, m),
                    )
                except Exception as exc:  # noqa: BLE001
                    schedule_on_main(
                        self,
                        self._log,
                        f"[AIGC] 生成前标签检查失败，已中止提交：{exc}",
                    )
                    schedule_on_main(
                        self,
                        messagebox.showwarning,
                        "标签检查失败，未生成",
                        f"无法完成生成前 LLM 标签检查：\n{exc}",
                    )
                    return
                if report.get("conflicts") or report.get("duplicates"):
                    schedule_on_main(
                        self, self._show_tag_preflight_issues, report, prepared
                    )
                    return
                schedule_on_main(
                    self, self._log, f"[AIGC] 标签冲突/重复检查通过 · {email}"
                )
            client = JimengWebClient()

            schedule_on_main(self, self._log, f"[AIGC] 送模 prompt：{prompt}")

            for i in range(n):
                if self._cancel:
                    schedule_on_main(self, self._log, "[AIGC] 已取消后续生成")
                    break
                run = create_run(
                    prompt,
                    rain_mode=mode,
                    prompt_table=table,
                    slots={k: list(v) for k, v in slots.items()},
                    repeat_index=i if n > 1 else None,
                    duration_sec=duration,
                )
                schedule_on_main(
                    self,
                    self._log,
                    f"[AIGC] 生成 {run.run_id}（{RAIN_MODE_LABELS[mode]}）"
                    f" ({i + 1}/{n}) …",
                )

                def progress(pct: int) -> None:
                    schedule_on_main(self, self._set_generate_progress, pct)

                schedule_on_main(self, self._set_generate_progress, 0)

                try:
                    client.generate_t2v(
                        prompt,
                        run.video_path,
                        duration_sec=duration,
                        model=model,
                        log=lambda m: schedule_on_main(self, self._log, m),
                        progress=progress,
                    )
                    meta = dict(run.meta)
                    meta["generated_at"] = meta.get("created_at")
                    run.save_meta(meta)
                    schedule_on_main(
                        self, self._log, f"[AIGC] 完成 {run.video_path.name}"
                    )
                    # 选中最新记录 + 刷新预览/详情；槽位保持当前编辑表
                    schedule_on_main(
                        self, self._focus_run, run.run_id, load_slots=False
                    )
                    schedule_on_main(
                        self, self._log, f"[AIGC] 自动 VLM 标记可疑标签：{run.run_id}"
                    )
                    self._auto_vlm_mark(run.run_id)
                except JimengWebError as exc:
                    schedule_on_main(
                        self, self._log, f"[AIGC] 失败 {run.run_id}：{exc}"
                    )
                    break

        self._run_bg(job)

    def _start_score(self) -> None:
        run = self._selected_run()
        if run is None:
            messagebox.showinfo("AIGC", "请先在列表中选择一条实验记录。")
            return
        if not run.video_path.is_file():
            messagebox.showwarning("AIGC", "该记录尚无视频，请先生成。")
            return

        rid = run.run_id

        def job() -> None:
            try:
                score_run(
                    rid,
                    log_fn=lambda m: schedule_on_main(self, self._log, m),
                )
                schedule_on_main(self, self._apply_score_to_ui, rid)
            except ScoreError as exc:
                schedule_on_main(self, self._log, f"[AIGC] 评分失败：{exc}")

        self._run_bg(job)


__all__ = ["AigcTab"]
