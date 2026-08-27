"""AIGC 主流程：参考图/主体 → 三档提示词 → 抽卡 → 后验。

一页跑完，不再有子 Tab。参考图只作主体与材质的锚点，生成一律走文生视频——
图生的「全能参考」会把首帧锁死，提示词改不动画面，对三档雨强的对比实验没用。
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gui.clipboard import setup_copyable_readonly_text
from gui.tk_thread import bind_ui_root, schedule_on_main
from gui.ui_theme import UiTheme, apply_primary_button_style
from gui.video_quota_panel import JimengCreditBarCompact, estimate_jimeng_video_credits
from scripts.aigc_lab.agent_store import (
    I2V_MODEL_CHOICES,
    AgentRun,
    create_agent_run,
    lab_params,
    list_agent_runs_light,
    load_agent_run,
    normalize_i2v_resolution,
    resolutions_for_i2v_model,
    save_lab_params,
)
from scripts.aigc_lab.posterior import (
    HUMAN_ADOPT,
    HUMAN_REJECT,
    Posterior,
    run_posterior,
    set_human_verdict,
)
from scripts.aigc_lab.prompt_gen import (
    PromptSet,
    RainPrompt,
    assertions_from_prompt,
    generate_rain_prompts,
)
from scripts.aigc_lab.rain_modes import RAIN_MODES, rain_mode as rain_mode_of
from scripts.aigc_lab.subject_pool import SUBJECT_GROUPS, format_subjects, split_subjects
from scripts.config.paths import agent_t2v_lab_dir, ensure_cli_path

_KIND = "t2v"
_DEFAULT_MODEL = "Seedance 2.0 Fast VIP"
_DEFAULT_DURATION = 6
_LIST_W = 34


def _session_path() -> Path:
    return agent_t2v_lab_dir() / "flow_session.json"


def _load_session() -> dict:
    path = _session_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_session(data: dict) -> None:
    path = _session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _format_run_line(run: AgentRun) -> str:
    meta = run.meta or {}
    mark = "●" if run.video_path.is_file() else "○"
    mode = rain_mode_of(meta.get("rain_mode")).label
    post = run.posterior or {}
    tag = ""
    human = str(post.get("human") or "")
    if human == HUMAN_ADOPT:
        tag = " ✓"
    elif human == HUMAN_REJECT:
        tag = " ✗"
    elif post:
        tag = " ·" if (post.get("gate") or {}).get("ok", True) else " !"
    return f"{mark}{tag} {mode} {run.run_id}"


class _ModeRow:
    """一行雨强：四段提示词（画面/光影/动态/约束），行末抽卡。"""

    def __init__(
        self,
        master,
        *,
        mode_id: str,
        title: str,
        row: int,
        on_draw: Callable[[str], None],
    ) -> None:
        self.mode_id = mode_id
        ttk.Label(master, text=title, width=14).grid(
            row=row, column=0, sticky="nw", padx=(0, 4), pady=2
        )
        self.txt_prompt = tk.Text(master, height=10, wrap=tk.WORD)
        self.txt_prompt.grid(row=row, column=1, sticky="nsew", padx=(0, 0), pady=2)
        self.btn_draw = ttk.Button(master, text="抽卡", command=lambda: on_draw(mode_id))
        self.btn_draw.grid(row=row, column=2, sticky="n", padx=(6, 0), pady=2)

    def set_content(self, item: RainPrompt) -> None:
        self.txt_prompt.delete("1.0", tk.END)
        self.txt_prompt.insert("1.0", item.prompt)

    @property
    def prompt(self) -> str:
        return self.txt_prompt.get("1.0", tk.END).strip()

    @property
    def assertions(self) -> list[str]:
        return assertions_from_prompt(self.prompt)

    def set_enabled(self, enabled: bool) -> None:
        self.btn_draw.configure(state=tk.NORMAL if enabled else tk.DISABLED)


class AigcFlowTab(ttk.Frame):
    title = "AIGC"

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
        self._ref_image: Path | None = None
        self._runs: list[AgentRun] = []
        self._selected_run_id: str | None = None
        self._runs_token = 0
        self._run_load_token = 0
        self._loaded_once = False
        self._jm_quota: JimengCreditBarCompact | None = None

        self._subject_var = tk.StringVar()
        self._note_var = tk.StringVar()
        self._status_var = tk.StringVar(value="待生成提示词")
        self._verdict_note_var = tk.StringVar()

        self._build_ui()
        self._restore_session()

    # --- 构建 UI ------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        self._build_param_bar()
        self._build_input_area()
        self._build_mode_area()
        self._build_records_area()

    def _build_param_bar(self) -> None:
        saved = lab_params(_KIND)
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))

        self._model_var = tk.StringVar(value=str(saved.get("model") or _DEFAULT_MODEL))
        cmb_model = ttk.Combobox(
            bar,
            textvariable=self._model_var,
            values=list(I2V_MODEL_CHOICES),
            state="readonly",
            width=22,
        )
        cmb_model.pack(side=tk.LEFT)
        cmb_model.bind("<<ComboboxSelected>>", self._on_model_changed)

        ttk.Label(bar, text="· 16:9 ·").pack(side=tk.LEFT, padx=6)

        res = normalize_i2v_resolution(str(saved.get("resolution") or "720P"))
        self._resolution_var = tk.StringVar(value=res.replace("P", "p"))
        self.cmb_resolution = ttk.Combobox(
            bar,
            textvariable=self._resolution_var,
            values=list(resolutions_for_i2v_model(self._model_var.get())),
            state="readonly",
            width=6,
        )
        self.cmb_resolution.pack(side=tk.LEFT)
        self.cmb_resolution.bind("<<ComboboxSelected>>", lambda _e: self._persist_params())

        ttk.Label(bar, text="时长").pack(side=tk.LEFT, padx=(10, 4))
        self.spin_duration = ttk.Spinbox(bar, from_=1, to=15, width=3)
        self.spin_duration.set(str(int(saved.get("duration_sec") or _DEFAULT_DURATION)))
        self.spin_duration.pack(side=tk.LEFT)

        ttk.Label(bar, text="每档张数").pack(side=tk.LEFT, padx=(10, 4))
        self.spin_count = ttk.Spinbox(bar, from_=1, to=10, width=3)
        self.spin_count.set(str(int(saved.get("generate_count") or 1)))
        self.spin_count.pack(side=tk.LEFT)

        self.btn_login = ttk.Button(bar, text="登录即梦", command=self._start_login)
        self.btn_login.pack(side=tk.RIGHT, padx=(8, 0))
        self._jm_quota = JimengCreditBarCompact(bar, log_fn=self._log)
        self._jm_quota.pack(side=tk.RIGHT, padx=(12, 8))
        self._sync_jimeng_login_hint()
        self.after_idle(self._jm_quota.reload)

    def _build_input_area(self) -> None:
        box = ttk.LabelFrame(self, text="① 主体", padding=8)
        box.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="参考图（可选）").grid(row=0, column=0, sticky="w")
        img_row = ttk.Frame(box)
        img_row.grid(row=0, column=1, columnspan=2, sticky="ew", padx=4)
        self._img_label = ttk.Label(img_row, text="（未选择）", foreground="gray")
        self._img_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(img_row, text="清除", command=self._clear_image).pack(side=tk.RIGHT)
        ttk.Button(img_row, text="选择…", command=self._pick_image).pack(
            side=tk.RIGHT, padx=(0, 4)
        )

        ttk.Label(box, text="主体关键词").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(box, textvariable=self._subject_var).grid(
            row=1, column=1, sticky="ew", padx=4, pady=(6, 0)
        )
        self._pick_subject = ttk.Combobox(
            box,
            values=[f"{g}｜{s}" for g, items in SUBJECT_GROUPS for s in items],
            state="readonly",
            width=18,
        )
        self._pick_subject.set("常用主体…")
        self._pick_subject.grid(row=1, column=2, sticky="w", pady=(6, 0))
        self._pick_subject.bind("<<ComboboxSelected>>", self._on_subject_picked)

        ttk.Label(box, text="补充要求").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(box, textvariable=self._note_var).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
        )

        row = ttk.Frame(box)
        row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        primary = apply_primary_button_style(ttk.Style(self))
        self.btn_gen_prompts = ttk.Button(
            row, text="生成三档提示词", command=self._start_prompt_gen, style=primary
        )
        self.btn_gen_prompts.pack(side=tk.LEFT)
        ttk.Label(row, textvariable=self._status_var).pack(side=tk.LEFT, padx=(12, 0))

    def _build_mode_area(self) -> None:
        box = ttk.LabelFrame(self, text="② 三档提示词（可改后再抽卡）", padding=6)
        box.grid(row=2, column=0, sticky="ew", padx=4, pady=4)
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="").grid(row=0, column=0)
        ttk.Label(box, text="画面 / 光影 / 动态 / 约束").grid(
            row=0, column=1, sticky="w"
        )

        self._panels: dict[str, _ModeRow] = {}
        for i, mode in enumerate(RAIN_MODES, start=1):
            panel = _ModeRow(
                box,
                mode_id=mode.mode_id,
                title=mode.display,
                row=i,
                on_draw=self._start_draw,
            )
            self._panels[mode.mode_id] = panel

    def _build_records_area(self) -> None:
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.grid(row=3, column=0, sticky="nsew", padx=4, pady=4)

        left = ttk.Frame(paned)
        paned.add(left, weight=1)
        ttk.Label(left, text="③ 实验记录").pack(anchor=tk.W)
        self.run_list = tk.Listbox(left, width=_LIST_W, height=10, exportselection=False)
        self.run_list.pack(fill=tk.BOTH, expand=True)
        self.run_list.bind("<<ListboxSelect>>", self._on_run_select)

        right = ttk.Frame(paned)
        paned.add(right, weight=2)

        head = ttk.Frame(right)
        head.pack(fill=tk.X)
        ttk.Label(head, text="详情与后验").pack(side=tk.LEFT)
        self.btn_reject = ttk.Button(head, text="废弃", command=lambda: self._judge(HUMAN_REJECT))
        self.btn_reject.pack(side=tk.RIGHT)
        self.btn_adopt = ttk.Button(head, text="采用", command=lambda: self._judge(HUMAN_ADOPT))
        self.btn_adopt.pack(side=tk.RIGHT, padx=(0, 4))
        self.btn_recheck = ttk.Button(head, text="重跑后验", command=self._start_recheck)
        self.btn_recheck.pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Entry(head, textvariable=self._verdict_note_var, width=24).pack(
            side=tk.RIGHT, padx=(0, 4)
        )
        ttk.Label(head, text="裁决备注").pack(side=tk.RIGHT)

        self.detail = tk.Text(right, height=12, wrap=tk.WORD, state=tk.DISABLED)
        self.detail.pack(fill=tk.BOTH, expand=True)
        setup_copyable_readonly_text(self.detail, self)

    # --- 参数与会话 ----------------------------------------------------

    def _on_model_changed(self, _event=None) -> None:
        allowed = resolutions_for_i2v_model(self._model_var.get())
        self.cmb_resolution.configure(values=list(allowed))
        if self._resolution_var.get() not in allowed:
            self._resolution_var.set(allowed[0])
        self._persist_params()

    def _gen_params(self) -> dict:
        try:
            duration = max(1, min(15, int(self.spin_duration.get())))
        except (TypeError, ValueError, tk.TclError):
            duration = _DEFAULT_DURATION
        try:
            count = max(1, min(10, int(self.spin_count.get())))
        except (TypeError, ValueError, tk.TclError):
            count = 1
        model = self._model_var.get().strip() or _DEFAULT_MODEL
        resolution = normalize_i2v_resolution(self._resolution_var.get())
        if resolution not in [r.upper() for r in resolutions_for_i2v_model(model)]:
            resolution = "720P"
        return {
            "model": model,
            "aspect_ratio": "16:9",
            "resolution": resolution,
            "duration_sec": duration,
            "generate_count": count,
        }

    def _persist_params(self) -> None:
        try:
            save_lab_params(_KIND, self._gen_params())
        except OSError:
            pass

    def _restore_session(self) -> None:
        data = _load_session()
        self._subject_var.set(str(data.get("subjects") or ""))
        self._note_var.set(str(data.get("note") or ""))
        ref = data.get("ref_image")
        if ref and Path(ref).is_file():
            self._set_image(Path(ref))
        for mode_id, payload in (data.get("prompts") or {}).items():
            panel = self._panels.get(mode_id)
            if panel is None or not isinstance(payload, dict):
                continue
            panel.set_content(RainPrompt.from_dict({"rain_mode": mode_id, **payload}))

    def save_session_now(self) -> None:
        try:
            _save_session(
                {
                    "subjects": self._subject_var.get(),
                    "note": self._note_var.get(),
                    "ref_image": str(self._ref_image) if self._ref_image else "",
                    "prompts": {
                        mode_id: {
                            "prompt": panel.prompt,
                            "assertions": panel.assertions,
                        }
                        for mode_id, panel in self._panels.items()
                    },
                }
            )
        except OSError:
            pass

    # --- 输入 ----------------------------------------------------------

    def _on_subject_picked(self, _event=None) -> None:
        raw = self._pick_subject.get()
        subject = raw.split("｜")[-1].strip()
        self._pick_subject.set("常用主体…")
        if not subject:
            return
        current = split_subjects(self._subject_var.get())
        if subject not in current:
            current.append(subject)
        self._subject_var.set(format_subjects(current))

    def _set_image(self, path: Path) -> None:
        self._ref_image = path
        self._img_label.configure(text=path.name, foreground="")

    def _clear_image(self) -> None:
        self._ref_image = None
        self._img_label.configure(text="（未选择）", foreground="gray")

    def _pick_image(self) -> None:
        initial = str(self._ref_image.parent) if self._ref_image else ""
        path = filedialog.askopenfilename(
            title="选择参考图",
            initialdir=initial or None,
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp"), ("所有文件", "*.*")],
        )
        if path:
            self._set_image(Path(path))

    # --- 忙碌态 --------------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.btn_gen_prompts.configure(state=state)
        self.btn_recheck.configure(state=state)
        for panel in self._panels.values():
            panel.set_enabled(not busy)

    def _failed(self, msg: str) -> None:
        self._set_busy(False)
        self._status_var.set("失败")
        self._log(f"[AIGC] {msg}")
        messagebox.showerror(self.title, msg)

    # --- ① → ② 生成三档提示词 -------------------------------------------

    def _start_prompt_gen(self) -> None:
        if self._busy:
            return
        subjects = split_subjects(self._subject_var.get())
        if not subjects and not self._ref_image:
            messagebox.showwarning(self.title, "请至少填一个主体关键词，或选一张参考图。")
            return
        self._set_busy(True)
        self._status_var.set("生成提示词中…")
        ref = self._ref_image
        note = self._note_var.get()

        def work() -> None:
            try:
                result = generate_rain_prompts(
                    subjects=subjects,
                    ref_image=ref,
                    note=note,
                    log_fn=lambda m: schedule_on_main(self, self._log, m),
                )
                schedule_on_main(self, self._apply_prompt_set, result)
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._failed, f"生成提示词失败：{exc}")

        threading.Thread(target=work, daemon=True).start()

    def _apply_prompt_set(self, result: PromptSet) -> None:
        self._set_busy(False)
        for item in result.prompts:
            panel = self._panels.get(item.rain_mode)
            if panel is not None:
                panel.set_content(item)
        if result.subjects and not split_subjects(self._subject_var.get()):
            self._subject_var.set(format_subjects(result.subjects))
        self._status_var.set(f"三档就绪 · {format_subjects(result.subjects)}")
        self.save_session_now()

    # --- ② → ③ 抽卡 ----------------------------------------------------

    def _start_draw(self, mode_id: str) -> None:
        if self._busy:
            return
        panel = self._panels[mode_id]
        prompt = panel.prompt
        if not prompt:
            messagebox.showwarning(self.title, "该档提示词为空。")
            return
        assertions = panel.assertions
        gen = self._gen_params()
        count = int(gen["generate_count"])
        label = rain_mode_of(mode_id).display
        if not messagebox.askyesno(
            self.title,
            f"抽卡「{label}」？\n"
            f"{gen['model']} · 16:9 · {str(gen['resolution']).lower()} · "
            f"{gen['duration_sec']}s × {count}"
            + ("" if assertions else "\n\n注意：该档没有断言，后验只能做客观闸门。"),
        ):
            return

        self._persist_params()
        self._set_busy(True)
        self._status_var.set(f"抽卡中…（{label}）")
        subjects = split_subjects(self._subject_var.get())
        ref = self._ref_image
        est = estimate_jimeng_video_credits(
            duration_sec=int(gen["duration_sec"]),
            resolution=str(gen["resolution"]),
            model=str(gen["model"]),
        )

        def work() -> None:
            credits = {"v": est}
            last_run_id = ""

            def on_credits(cost: int) -> None:
                credits["v"] = cost

            try:
                ensure_cli_path()
                from jimeng_web.client import JimengWebClient

                client = JimengWebClient()
                for i in range(count):
                    if count > 1:
                        schedule_on_main(
                            self, self._status_var.set, f"抽卡中… {i + 1}/{count}（{label}）"
                        )
                    run = create_agent_run(
                        _KIND,
                        prompt=prompt,
                        rain_mode=mode_id,
                        assertions=assertions,
                        subjects=subjects,
                        scene_keywords=format_subjects(subjects),
                        duration_sec=int(gen["duration_sec"]),
                        ref_image=ref,
                    )
                    last_run_id = run.run_id
                    client.generate_t2v(
                        prompt,
                        run.video_path,
                        duration_sec=int(gen["duration_sec"]),
                        model=str(gen["model"]),
                        aspect_ratio="16:9",
                        resolution=str(gen["resolution"]),
                        log=lambda m: schedule_on_main(self, self._log, m),
                        on_credits=on_credits,
                    )
                    if credits["v"] > 0:
                        run.update_meta(jimeng_credits=int(credits["v"]))
                    self._posterior_in_worker(run)
                schedule_on_main(self, self._draw_done, last_run_id)
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._failed, f"抽卡失败：{exc}")

        threading.Thread(target=work, daemon=True).start()

    def _posterior_in_worker(self, run: AgentRun) -> None:
        """抽卡落盘后立刻跑后验；失败不影响素材本身。"""
        try:
            run_posterior(run, log_fn=lambda m: schedule_on_main(self, self._log, m))
        except Exception as exc:  # noqa: BLE001
            schedule_on_main(self, self._log, f"[后验] 跳过：{exc}")

    def _draw_done(self, run_id: str) -> None:
        self._set_busy(False)
        self._status_var.set(f"完成 · {run_id}")
        if self._jm_quota is not None:
            self._jm_quota.reload()
        self._refresh_runs_async(after=lambda: self._select_run(run_id))

    # --- ③ 记录 / 后验 --------------------------------------------------

    def _refresh_runs_async(self, *, after: Callable[[], None] | None = None) -> None:
        self._runs_token += 1
        token = self._runs_token

        def work() -> None:
            try:
                runs = list_agent_runs_light("t2v") + list_agent_runs_light("i2v")
                runs.sort(key=lambda r: r.run_id, reverse=True)
            except Exception:  # noqa: BLE001
                runs = []

            def apply() -> None:
                if token != self._runs_token:
                    return
                self._runs = runs
                self.run_list.delete(0, tk.END)
                for run in runs:
                    self.run_list.insert(tk.END, _format_run_line(run))
                if after:
                    after()

            schedule_on_main(self, apply)

        threading.Thread(target=work, daemon=True).start()

    def _on_run_select(self, _event=None) -> None:
        sel = self.run_list.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self._runs):
            run = self._runs[idx]
            self._select_run(run.run_id, kind=run.kind)

    def _select_run(self, run_id: str, kind: str | None = None) -> None:
        self._selected_run_id = run_id
        self._run_load_token += 1
        token = self._run_load_token
        if kind is None:
            hit = next((r for r in self._runs if r.run_id == run_id), None)
            kind = hit.kind if hit is not None else _KIND

        def work() -> None:
            try:
                run = load_agent_run(kind, run_id)  # type: ignore[arg-type]
            except FileNotFoundError:
                return

            def apply() -> None:
                if token != self._run_load_token:
                    return
                self._show_run_detail(run)
                if self._on_preview_run:
                    video = run.video_path if run.video_path.is_file() else None
                    img = None
                    for name in ("ref_image.png", "ref_image.jpg"):
                        p = run.dir / name
                        if p.is_file():
                            img = p
                            break
                    kwargs = {"kind": _KIND, "prompt": run.prompt}
                    if img:
                        kwargs["kind"] = "i2v"
                        kwargs["image_path"] = img
                    self._on_preview_run(video, run.run_id, **kwargs)

            schedule_on_main(self, apply)

        threading.Thread(target=work, daemon=True).start()

    def _current_run(self) -> AgentRun | None:
        if not self._selected_run_id:
            return None
        hit = next((r for r in self._runs if r.run_id == self._selected_run_id), None)
        kind = hit.kind if hit is not None else _KIND
        try:
            return load_agent_run(kind, self._selected_run_id)  # type: ignore[arg-type]
        except FileNotFoundError:
            return None

    def _judge(self, verdict: str) -> None:
        run = self._current_run()
        if run is None:
            messagebox.showinfo(self.title, "先选一条记录。")
            return
        set_human_verdict(run, verdict, self._verdict_note_var.get())
        self._verdict_note_var.set("")
        self._log(
            f"[后验] {run.run_id} 人工{'采用' if verdict == HUMAN_ADOPT else '废弃'}"
        )
        self._refresh_runs_async(after=lambda: self._select_run(run.run_id))

    def _start_recheck(self) -> None:
        if self._busy:
            return
        run = self._current_run()
        if run is None:
            messagebox.showinfo(self.title, "先选一条记录。")
            return
        self._set_busy(True)
        self._status_var.set("后验中…")

        def work() -> None:
            try:
                run_posterior(
                    run, log_fn=lambda m: schedule_on_main(self, self._log, m)
                )
                schedule_on_main(self, self._recheck_done, run.run_id)
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._failed, f"后验失败：{exc}")

        threading.Thread(target=work, daemon=True).start()

    def _recheck_done(self, run_id: str) -> None:
        self._set_busy(False)
        self._status_var.set("后验完成")
        self._refresh_runs_async(after=lambda: self._select_run(run_id))

    def _show_run_detail(self, run: AgentRun) -> None:
        meta = run.meta or {}
        lines = [
            f"run_id: {run.run_id}",
            f"雨档: {meta.get('rain_label') or ''}",
            f"主体: {format_subjects(meta.get('subjects') or [])}",
            f"参数: {meta.get('model')} · {meta.get('resolution')} · {meta.get('duration_sec')}s",
            f"成片: {'有' if run.video_path.is_file() else '无'}"
            + (f" · 消耗 {meta.get('jimeng_credits')} 积分" if meta.get("jimeng_credits") else ""),
            "",
        ]

        if run.posterior:
            post = Posterior.from_dict(run.posterior)
            gate = post.gate
            lines.append(f"客观闸门: {'通过' if gate.ok else '不通过'}")
            lines.append(
                f"  运动量 {gate.motion_score:.1f} · 亮度跳动 {gate.flicker:.1f} · "
                f"帧差突变 {gate.cut_ratio:.1f}"
            )
            for issue in gate.issues:
                lines.append(f"  · {issue}")
            if post.assertions:
                lines.append(f"断言核对: 命中率 {post.hit_rate:.0%}")
                for a in post.assertions:
                    lines.append(f"  [{a.verdict}] {a.text}")
                    if a.note:
                        lines.append(f"        {a.note}")
            if post.human:
                mark = "采用" if post.human == HUMAN_ADOPT else "废弃"
                lines.append(f"人工裁决: {mark}" + (f" · {post.human_note}" if post.human_note else ""))
            else:
                lines.append("人工裁决: 未裁决")
            lines.append("")
        else:
            lines.append("后验: 未跑")
            lines.append("")

        assertions = meta.get("assertions") or []
        if assertions:
            lines.append("生成时的断言:")
            lines.extend(f"  {i}. {a}" for i, a in enumerate(assertions, start=1))
            lines.append("")
        lines.append("送模正文:")
        lines.append(run.prompt or "")
        self._set_detail("\n".join(lines))

    def _set_detail(self, text: str) -> None:
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.insert("1.0", text)
        self.detail.configure(state=tk.DISABLED)

    # --- 即梦登录 / 额度 ------------------------------------------------

    def _sync_jimeng_login_hint(self) -> None:
        """用本地 profile 标记即时恢复按钮文案，避免每次重启都显示「登录即梦」。"""
        try:
            ensure_cli_path()
            from jimeng_web.client import LOGIN_MARK, PROFILE_DIR

            if LOGIN_MARK.is_file() and PROFILE_DIR.is_dir():
                self.btn_login.configure(text="已登录")
        except Exception:
            pass

    def _refresh_jimeng_auth_ui(self) -> None:
        """后台校验登录态并刷新额度条。"""
        if self._jm_quota is not None:
            self._jm_quota.reload()

        def work() -> None:
            try:
                ensure_cli_path()
                from jimeng_web.client import JimengWebClient

                st = JimengWebClient().login_status()
                text = "已登录" if st.is_logged_in else "登录即梦"
                schedule_on_main(self, self.btn_login.configure, text=text)
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._log, f"[即梦] 状态检查失败：{exc}")

        threading.Thread(target=work, daemon=True).start()

    def _start_login(self) -> None:
        if self._busy:
            return

        def work() -> None:
            try:
                ensure_cli_path()
                from jimeng_web.client import JimengWebClient

                st = JimengWebClient().interactive_login(
                    log=lambda m: schedule_on_main(self, self._log, m)
                )
                schedule_on_main(self, self._log, f"[即梦] 登录完成：{st.detail}")
                if st.is_logged_in:
                    schedule_on_main(self, self.btn_login.configure, text="已登录")
                    if self._jm_quota is not None:
                        schedule_on_main(self, self._jm_quota.reload)
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._log, f"[即梦] 登录失败：{exc}")

        threading.Thread(target=work, daemon=True).start()

    # --- 宿主回调 -------------------------------------------------------

    def on_tab_selected(self) -> None:
        self._refresh_jimeng_auth_ui()
        if self._loaded_once:
            return
        self._loaded_once = True
        self._refresh_runs_async()

    def apply_theme(self, theme: UiTheme) -> None:
        if self._jm_quota is not None:
            self._jm_quota.apply_theme(theme)
        widgets: list[tk.Widget] = [self.detail, self.run_list]
        for panel in self._panels.values():
            widgets.extend((panel.txt_prompt,))
        for widget in widgets:
            try:
                widget.configure(
                    background=theme.text_bg,
                    foreground=theme.fg,
                    insertbackground=theme.fg,
                    selectbackground=theme.select_bg,
                    selectforeground=theme.select_fg,
                )
            except tk.TclError:
                pass
