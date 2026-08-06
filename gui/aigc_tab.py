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
from scripts.aigc_lab import ScoreError, create_run, list_runs, load_run, score_run
from scripts.aigc_lab.store import lab_params
from scripts.aigc_lab.prompt_atoms import (
    DEFAULT_RAIN_MODE,
    RAIN_MODE_LABELS,
    RAIN_MODES,
    SLOT_LABELS,
    SLOT_ORDER,
    active_agy_account_display,
    compose_prompt,
    default_slots,
    format_table,
    normalize_rain_mode,
)
from scripts.aigc_lab.session import load_session, save_session
from scripts.aigc_lab.tag_pools import (
    failed_tags_from_scores,
    format_tags_by_slot,
    merge_into_pools,
    qualified_tags_from_scores,
    suggest_for_slot,
)
from scripts.config.paths import ensure_cli_path

_LIST_W = 42
_GENERATE_BTN_LABEL = "生成视频"
_FAIL_BORDER = "#c62828"


class AigcTab(ttk.Frame):
    def __init__(
        self,
        master,
        *,
        log_fn: Callable[[str], None],
        on_preview_run: Callable[[Path, str, str], None] | None = None,
    ) -> None:
        super().__init__(master)
        bind_ui_root(self)
        self._log = log_fn
        self._on_preview_run = on_preview_run
        self._busy = False
        self._cancel = False
        self._runs: list = []
        self._selected_run_id: str | None = None
        self._slot_containers: dict[str, tk.Frame] = {}
        self._slot_tags_areas: dict[str, tk.Frame] = {}
        self._slot_add_frames: dict[str, tk.Frame] = {}
        # 每槽原子原文（UI 唯一数据源）
        self._slot_atoms: dict[str, list[str]] = {key: [] for key in SLOT_ORDER}
        # 人工/评分标记的不合格标签（红框）；入池时排除
        self._slot_fail_tags: dict[str, set[str]] = {key: set() for key in SLOT_ORDER}
        self._slot_add_vars: dict[str, tk.StringVar] = {
            key: tk.StringVar(value="") for key in SLOT_ORDER
        }
        self._slot_add_combos: dict[str, ttk.Combobox] = {}
        self._slot_reflow_after: dict[str, str | None] = {
            key: None for key in SLOT_ORDER
        }
        self._reflow_guard: dict[str, bool] = {key: False for key in SLOT_ORDER}
        self._slot_last_width: dict[str, int] = {key: 0 for key in SLOT_ORDER}
        self._layout_frozen = False
        # 统一配色（apply_theme 覆盖）
        self._atom_row_bg = "#f5f5f5"
        self._atom_tag_bg = "#e8e8e8"
        self._atom_tag_fg = "#1a1a1a"
        self._atom_border = "#d0d0d0"
        self._loaded_once = False
        self._session_save_after_id: str | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=(8, 4))

        params = lab_params()
        model = params.get("model", "Seedance 2.0 VIP")
        dur = params.get("duration_sec", 4)
        ttk.Label(
            top,
            text=f"实验台 · {model} · 16:9 · 720p · {dur}s",
        ).pack(side=tk.LEFT)

        self.btn_jimeng_login = ttk.Button(
            top, text="即梦登录", command=self._start_jimeng_login
        )
        self.btn_jimeng_login.pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(top, text="刷新列表", command=self.refresh).pack(side=tk.RIGHT)

        prompt_frame = ttk.LabelFrame(
            self,
            text="Prompt 原子表（×删除；单击标不合格/红框；行末从池选或新输入；送模=各槽拼接）",
            padding=8,
        )
        prompt_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # 用 tk.Frame 而非 ttk，避免 ttk 父级下 tk 子控件几何异常
        table = tk.Frame(prompt_frame, bg=self._atom_row_bg)
        table.pack(fill=tk.BOTH, expand=True)
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
            text="镜头=固定镜头+平视/仰视/俯视；焦距广角不写（由主体范围表达）",
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
        self.cmb_rain.bind("<<ComboboxSelected>>", lambda _e: self._fill_baseline())
        ttk.Button(
            row_gen, text="填入基线原子稿", command=self._fill_baseline
        ).pack(side=tk.LEFT)
        ttk.Button(
            row_gen, text="预览送模正文", command=self._preview_model_prompt
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            row_gen, text="合格标签入池", command=self._pool_qualified_manual
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(row_gen, text="重复 N 次").pack(side=tk.LEFT, padx=(12, 0))
        self.spin_repeat = ttk.Spinbox(row_gen, from_=1, to=10, width=4)
        self.spin_repeat.set("1")
        self.spin_repeat.pack(side=tk.LEFT, padx=(4, 12))
        self.btn_generate = ttk.Button(
            row_gen, text="生成视频", command=self._start_generate
        )
        self.btn_generate.pack(side=tk.LEFT)
        self.btn_stop = ttk.Button(row_gen, text="停止", command=self._request_cancel)
        self.btn_stop.pack(side=tk.LEFT, padx=(6, 0))

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        left = ttk.Frame(body)
        body.add(left, weight=1)

        ttk.Label(left, text="样本 runs").pack(anchor=tk.W)
        self.list_runs = tk.Listbox(left, width=_LIST_W, height=16, exportselection=False)
        scroll = ttk.Scrollbar(left, command=self.list_runs.yview)
        self.list_runs.configure(yscrollcommand=scroll.set)
        self.list_runs.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_runs.bind("<<ListboxSelect>>", self._on_run_select)

        right = ttk.Frame(body)
        body.add(right, weight=2)

        ttk.Label(right, text="详情").pack(anchor=tk.W)
        self.txt_detail = tk.Text(right, height=14, wrap=tk.WORD)
        self.txt_detail.pack(fill=tk.BOTH, expand=True)
        setup_copyable_readonly_text(self.txt_detail, self)

        row_act = ttk.Frame(right)
        row_act.pack(fill=tk.X, pady=(6, 0))
        self.btn_score = ttk.Button(
            row_act, text="L1+L2 评分", command=self._start_score
        )
        self.btn_score.pack(side=tk.LEFT)

    def on_tab_selected(self) -> None:
        if not self._loaded_once:
            self._loaded_once = True
            # 等 Notebook 几何稳定后恢复 session 或只填一次基线
            self.after(120, self._init_session_once)
            self._refresh_jimeng_login_ui()
            return
        self.refresh()
        self._refresh_jimeng_login_ui()

    def _init_session_once(self) -> None:
        ready = all(
            area.winfo_width() > 1
            for area in self._slot_tags_areas.values()
        )
        if not ready:
            self.after(50, self._init_session_once)
            return
        if self._restore_session():
            return
        if any(self._slot_atoms.values()):
            self.refresh()
            return
        self._fill_baseline()
        self.refresh()

    def _session_payload(self) -> dict:
        return {
            "rain_mode": self._current_rain_mode(),
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

    def _restore_session(self) -> bool:
        data = load_session()
        if data is None:
            return False
        mode = normalize_rain_mode(str(data.get("rain_mode") or DEFAULT_RAIN_MODE))
        self.rain_var.set(RAIN_MODE_LABELS[mode])
        slots = {key: list((data.get("slots") or {}).get(key) or []) for key in SLOT_ORDER}
        fails = {
            key: list((data.get("fail_tags") or {}).get(key) or []) for key in SLOT_ORDER
        }
        self._write_slots(slots, clear_fails=False)
        self._set_fail_marks_for_current_ui(fails)
        for key in SLOT_ORDER:
            self._reflow_tags(key)
        sel = str(data.get("selected_run_id") or "").strip()
        if sel:
            self._selected_run_id = sel
        self.refresh()
        if sel and self.list_runs.curselection():
            self._on_run_select()
        self._log("[AIGC] 已恢复上次会话（原子表 · 红框 · 选中 run）")
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

    def refresh(self) -> None:
        self._runs = list_runs()
        sel = self._selected_run_id
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
        if self._runs and not self.list_runs.curselection():
            self.list_runs.selection_set(0)
            self._on_run_select()

    def _selected_run(self):
        sel = self.list_runs.curselection()
        if not sel:
            return None
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._runs):
            return None
        return self._runs[idx]

    def _on_run_select(self, _event=None) -> None:
        run = self._selected_run()
        if run is None:
            return
        self._selected_run_id = run.run_id
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
        if run.video_path.is_file() and self._on_preview_run:
            self._on_preview_run(run.video_path, run.run_id, run.prompt)

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

    def _toggle_fail_tag(self, slot: str, text: str) -> None:
        fails = self._slot_fail_tags.setdefault(slot, set())
        if text in fails:
            fails.discard(text)
            self._log(f"[AIGC] 取消不合格：[{SLOT_LABELS.get(slot, slot)}] {text}")
        else:
            fails.add(text)
            self._log(f"[AIGC] 标不合格：[{SLOT_LABELS.get(slot, slot)}] {text}")
        self._reflow_tags(slot)
        self._schedule_save_session()

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

    def _refresh_all_suggestions(self) -> None:
        for key in SLOT_ORDER:
            self._refresh_slot_suggestions(key)

    def _make_tag(self, parent: tk.Frame, slot: str, text: str, index: int) -> tk.Frame:
        failed = self._is_fail_tag(slot, text)
        border = _FAIL_BORDER if failed else self._atom_border
        thickness = 2 if failed else 1
        outer = tk.Frame(
            parent,
            bg=border,
            padx=thickness,
            pady=thickness,
            highlightthickness=0,
        )
        inner = tk.Frame(outer, bg=self._atom_tag_bg)
        inner.pack(fill=tk.BOTH, expand=True)
        lbl = tk.Label(
            inner,
            text=text,
            bg=self._atom_tag_bg,
            fg=self._atom_tag_fg,
            padx=6,
            pady=2,
            cursor="hand2",
        )
        lbl.pack(side=tk.LEFT)
        # 单击标签正文 → 切换不合格；× 仍负责删除
        lbl.bind(
            "<Button-1>",
            lambda _e, s=slot, t=text: self._toggle_fail_tag(s, t),
        )
        tk.Button(
            inner,
            text="×",
            command=lambda s=slot, i=index: self._remove_atom(s, i),
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
        ).pack(side=tk.LEFT)
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
        self._layout_frozen = True
        for key in SLOT_ORDER:
            self._slot_atoms[key] = [
                str(a).strip() for a in (slots.get(key) or []) if str(a).strip()
            ]
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

    def _unfreeze_layout(self) -> None:
        self._layout_frozen = False
        for key in SLOT_ORDER:
            area = self._slot_tags_areas.get(key)
            if area is not None and area.winfo_width() > 1:
                self._slot_last_width[key] = area.winfo_width()

    def _model_prompt(self) -> str:
        return compose_prompt(self._read_slots())

    def _fill_baseline(self) -> None:
        mode = self._current_rain_mode()
        slots = default_slots(mode)
        self._write_slots(slots)
        label = RAIN_MODE_LABELS[mode]
        model_prompt = compose_prompt(slots)
        self._log(
            f"[AIGC] 已填入「{label}」六槽基线 · agy {active_agy_account_display()}"
        )
        self._log(f"[AIGC] 送模正文预览：{model_prompt}")

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
        added, _pools = merge_into_pools(cleaned)
        if not any(added.values()):
            self._log("[AIGC] 入池完成：无新增（均已在池中）")
            messagebox.showinfo("AIGC", "这些标签都已在学习池中，无新增。")
        else:
            summary = format_tags_by_slot(added)
            self._log(f"[AIGC] 已入池新增：\n{summary}")
            messagebox.showinfo("AIGC", f"已合入学习池：\n\n{summary}")
        self._refresh_all_suggestions()

    def _pool_qualified_manual(self) -> None:
        """人工：红框外的标签入池（先标完不合格再点）。"""
        self._confirm_and_merge_pools(
            self._qualified_tags_from_ui(),
            source="人工确认（排除红框不合格）",
        )

    def _apply_score_to_ui(self, run_id: str) -> None:
        """评分结束后：红框不合格 + 弹窗确认合格入池。"""
        try:
            run = load_run(run_id)
        except Exception as exc:  # noqa: BLE001
            self._log(f"[AIGC] 加载评分结果失败：{exc}")
            return
        scores = run.scores or {}
        failed = failed_tags_from_scores(scores)
        qualified = qualified_tags_from_scores(scores)

        # 只标红当前表里的标签，不写入 run.meta.slots（避免恢复/覆盖用户编辑）
        self._set_fail_marks_for_current_ui(failed)
        for key in SLOT_ORDER:
            self._reflow_tags(key)
        self._schedule_save_session()

        fail_body = format_tags_by_slot(failed)
        yes_body = format_tags_by_slot(qualified)
        self._log(f"[AIGC] 评分不合格（红框）：\n{fail_body}")
        self._log(f"[AIGC] 评分合格候选（待确认入池）：\n{yes_body}")
        self.refresh()
        # 选中刚评的 run，刷新详情
        self._selected_run_id = run_id
        for i, r in enumerate(self._runs):
            if r.run_id == run_id:
                self.list_runs.selection_clear(0, tk.END)
                self.list_runs.selection_set(i)
                self.list_runs.see(i)
                break
        self._on_run_select()
        self._confirm_and_merge_pools(qualified, source=f"L1+L2 自动评分 · {run_id}")

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

    def _start_generate(self) -> None:
        slots = self._read_slots()
        prompt = compose_prompt(slots)
        if not prompt:
            messagebox.showwarning("AIGC", "请先填写原子表。")
            return
        table = format_table(slots)
        try:
            n = max(1, min(10, int(self.spin_repeat.get())))
        except ValueError:
            n = 1

        def job() -> None:
            ensure_cli_path()
            from jimeng_web.client import JimengWebClient, JimengWebError

            client = JimengWebClient()
            params = lab_params()
            duration = int(params.get("duration_sec", 4))
            model = params.get("model", "Seedance 2.0 VIP")
            mode = self._current_rain_mode()

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
                except JimengWebError as exc:
                    schedule_on_main(
                        self, self._log, f"[AIGC] 失败 {run.run_id}：{exc}"
                    )
                    break

        self._run_bg(job)

    def _start_score(self) -> None:
        run = self._selected_run()
        if run is None:
            messagebox.showinfo("AIGC", "请先在列表中选择一条 run。")
            return
        if not run.video_path.is_file():
            messagebox.showwarning("AIGC", "该 run 尚无视频，请先生成。")
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
