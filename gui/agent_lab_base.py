"""AIGC「文生视频 / 图生视频」子 Tab 共用基类。"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gui.agent_atoms_ui import AtomTable
from gui.clipboard import setup_copyable_readonly_text
from gui.tk_thread import bind_ui_root, schedule_on_main
from gui.ui_theme import UiTheme, apply_primary_button_style
from scripts.aigc_lab.agent_loop import (
    LoopResult,
    conflict_tag_set,
    loop_result_from_review_json,
    run_agent_review_loop,
)
from scripts.aigc_lab.youtube_competitor_pool import series_goal_label
from scripts.aigc_lab.agent_session import load_agent_session, save_agent_session
from scripts.aigc_lab.agent_store import (
    AgentRun,
    I2V_JIMENG_PARAMS,
    I2V_MODEL_CHOICES,
    create_agent_run,
    lab_params,
    list_agent_runs_light,
    load_agent_run,
    normalize_i2v_resolution,
    resolve_i2v_gen_params,
    resolutions_for_i2v_model,
    save_lab_params,
    slots_from_agent_run,
)
from scripts.aigc_lab.prompt_atoms import (
    DEFAULT_RAIN_MODE,
    RAIN_MODE_LABELS,
    RAIN_MODES,
    compose_prompt,
    normalize_rain_mode,
)
from scripts.aigc_lab.youtube_viral_score import youtube_viral_score
from gui.video_quota_panel import JimengCreditBarCompact, estimate_jimeng_video_credits
from scripts.config.paths import ensure_cli_path

_LIST_W = 40
_CONFIRM_BTN_LABEL = "生成视频"
# 生成后自动油管爆款评分（youtube_viral_score 模块保留，默认关闭）
_AUTO_VIRAL_SCORE_AFTER_GENERATE = False


def _format_slots_brief(slots: dict[str, list[str]] | None) -> str:
    if not slots:
        return "  （空）"
    parts: list[str] = []
    from scripts.aigc_lab.prompt_atoms import SLOT_LABELS

    for key, tags in slots.items():
        if not tags:
            continue
        label = SLOT_LABELS.get(key, key)
        parts.append(f"  {label}: {', '.join(tags[:6])}")
    return "\n".join(parts) if parts else "  （空）"


def _format_run_list_line(run: AgentRun) -> str:
    ok = "●" if run.video_path.is_file() else "○"
    credits = ""
    raw_credits = (run.meta or {}).get("jimeng_credits")
    if raw_credits is not None:
        try:
            n = int(raw_credits)
            if n > 0:
                credits = f" {n}"
        except (TypeError, ValueError):
            pass
    viral = ""
    if run.viral_score:
        viral = f" ★{run.viral_score.get('score', '?')}"
    conflict = ""
    if run.review and not run.review.get("agreed", True):
        conflict = " !"
    return f"{ok}{credits}{conflict}{viral} {run.run_id}"


class AgentLabTabBase(ttk.Frame):
    kind: str = "t2v"  # t2v | i2v
    title: str = "文生视频"

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
        self._loop_result: LoopResult | None = None
        self._confirmed = False
        self._runs: list[AgentRun] = []
        self._selected_run_id: str | None = None
        self._ref_image: Path | None = None
        self._loaded_once = False
        self._session_save_after_id: str | None = None
        self._preview_after_id: str | None = None
        self._runs_refresh_token = 0
        self._run_load_token = 0
        self._preview_load_token = 0
        self._rain_var = tk.StringVar(value=DEFAULT_RAIN_MODE)
        self._scene_var = tk.StringVar(value="原始热带雨林")
        self._round_var = tk.StringVar(value="轮次 —")
        self._status_var = tk.StringVar(value="待草稿")
        self._jm_quota: JimengCreditBarCompact | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3 if self.kind != "i2v" else 4, weight=1)

        content_row0 = 0
        if self.kind == "i2v":
            self._build_i2v_params_bar()
            content_row0 = 1

        top = ttk.LabelFrame(self, text=self.title, padding=8)
        top.grid(row=content_row0, column=0, sticky="ew", padx=4, pady=4)
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="雨型").grid(row=0, column=0, sticky="w")
        if self.kind == "i2v":
            ttk.Label(
                top,
                text="按参考图判断；无雨默认大雨（storm→助眠 / heavy→专注 / light_mod→冥想）",
                foreground="gray",
            ).grid(row=0, column=1, columnspan=2, sticky="w", padx=4)
        else:
            rain = ttk.Combobox(
                top,
                textvariable=self._rain_var,
                values=[m for m, _ in RAIN_MODES],
                state="readonly",
                width=12,
            )
            rain.grid(row=0, column=1, sticky="w", padx=4)
            rain.bind(
                "<<ComboboxSelected>>",
                lambda _e: self._rain_var.set(normalize_rain_mode(self._rain_var.get())),
            )
            self._rain_label = ttk.Label(top, text=RAIN_MODE_LABELS.get(DEFAULT_RAIN_MODE, ""))
            self._rain_label.grid(row=0, column=2, sticky="w", padx=4)
            self._rain_var.trace_add("write", self._sync_rain_label)
            self._rain_var.trace_add("write", lambda *_a: self._schedule_save_session())
        self._scene_var.trace_add("write", lambda *_a: self._schedule_save_session())

        if self.kind == "t2v":
            ttk.Label(top, text="场景关键字").grid(row=1, column=0, sticky="w", pady=(6, 0))
            ttk.Entry(top, textvariable=self._scene_var).grid(
                row=1, column=1, columnspan=2, sticky="ew", padx=4, pady=(6, 0)
            )
        else:
            ttk.Label(top, text="参考截图").grid(row=1, column=0, sticky="w", pady=(6, 0))
            row = ttk.Frame(top)
            row.grid(row=1, column=1, columnspan=2, sticky="ew", padx=4, pady=(6, 0))
            self._img_label = ttk.Label(row, text="（未选择）", foreground="gray")
            self._img_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Button(row, text="选择…", command=self._pick_image).pack(side=tk.RIGHT)

        btns = ttk.Frame(top)
        btns.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.btn_draft = ttk.Button(btns, text="Jimeng草稿+审核", command=self._start_loop)
        self.btn_draft.pack(side=tk.LEFT)
        primary_style = apply_primary_button_style(ttk.Style(self))
        self.btn_confirm = ttk.Button(
            btns,
            text=_CONFIRM_BTN_LABEL,
            command=self._start_generate,
            state=tk.DISABLED,
            style=primary_style,
        )
        self.btn_confirm.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(btns, textvariable=self._round_var).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Label(btns, textvariable=self._status_var).pack(side=tk.LEFT, padx=(8, 0))

        mid = ttk.LabelFrame(self, text="六槽原子（可调）", padding=6)
        mid.grid(row=content_row0 + 1, column=0, sticky="ew", padx=4, pady=4)
        mid.columnconfigure(0, weight=1)
        self.atoms = AtomTable(mid, on_change=self._on_atoms_changed)
        self.atoms.grid(row=0, column=0, sticky="ew")

        bottom = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        bottom.grid(row=content_row0 + 3, column=0, sticky="nsew", padx=4, pady=4)

        left = ttk.Frame(bottom)
        bottom.add(left, weight=1)
        ttk.Label(left, text="实验记录").pack(anchor=tk.W)
        self.run_list = tk.Listbox(left, width=_LIST_W, height=12, exportselection=False)
        self.run_list.pack(fill=tk.BOTH, expand=True)
        self.run_list.bind("<<ListboxSelect>>", self._on_run_select)

        right = ttk.Frame(bottom)
        bottom.add(right, weight=2)
        ttk.Label(right, text="详情").pack(anchor=tk.W)
        self.detail = tk.Text(right, height=14, wrap=tk.WORD, state=tk.DISABLED)
        self.detail.pack(fill=tk.BOTH, expand=True)
        setup_copyable_readonly_text(self.detail, self)

    def _build_i2v_params_bar(self) -> None:
        """图生顶栏：模型 / 16:9 / 分辨率 / 生成数量 / 登录即梦。"""
        saved = resolve_i2v_gen_params(lab_params("i2v"))
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))

        self._model_var = tk.StringVar(value=str(saved["model"]))
        self.cmb_model = ttk.Combobox(
            bar,
            textvariable=self._model_var,
            values=list(I2V_MODEL_CHOICES),
            state="readonly",
            width=22,
        )
        self.cmb_model.pack(side=tk.LEFT)
        self.cmb_model.bind("<<ComboboxSelected>>", self._on_i2v_model_changed)

        ttk.Label(bar, text="·").pack(side=tk.LEFT, padx=(6, 6))
        ttk.Label(bar, text="16:9").pack(side=tk.LEFT)
        ttk.Label(bar, text="·").pack(side=tk.LEFT, padx=(6, 6))

        res_display = str(saved["resolution"]).replace("P", "p")
        self._resolution_var = tk.StringVar(value=res_display)
        self.cmb_resolution = ttk.Combobox(
            bar,
            textvariable=self._resolution_var,
            values=list(resolutions_for_i2v_model(str(saved["model"]))),
            state="readonly",
            width=6,
        )
        self.cmb_resolution.pack(side=tk.LEFT)
        self.cmb_resolution.bind("<<ComboboxSelected>>", lambda _e: self._persist_i2v_gen_params())

        ttk.Label(bar, text="·").pack(side=tk.LEFT, padx=(6, 6))
        ttk.Label(bar, text=f"{int(saved['duration_sec'])}s").pack(side=tk.LEFT)
        ttk.Label(bar, text="生成数量").pack(side=tk.LEFT, padx=(10, 0))
        self.spin_generate_count = ttk.Spinbox(bar, from_=1, to=10, width=3)
        self.spin_generate_count.set(str(int(saved["generate_count"])))
        self.spin_generate_count.pack(side=tk.LEFT, padx=(4, 0))
        self.spin_generate_count.bind("<FocusOut>", lambda _e: self._persist_i2v_gen_params())
        self.spin_generate_count.bind("<Return>", lambda _e: self._persist_i2v_gen_params())

        self.btn_jimeng_login = ttk.Button(
            bar, text="登录即梦", command=self._start_jimeng_login
        )
        self.btn_jimeng_login.pack(side=tk.RIGHT, padx=(8, 0))
        self._jm_quota = JimengCreditBarCompact(bar, log_fn=self._log)
        self._jm_quota.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(12, 8))

    def _on_i2v_model_changed(self, _event=None) -> None:
        model = self._model_var.get().strip() or str(I2V_JIMENG_PARAMS["model"])
        allowed = resolutions_for_i2v_model(model)
        self.cmb_resolution.configure(values=list(allowed))
        cur = self._resolution_var.get().strip().lower()
        if cur not in allowed:
            self._resolution_var.set(allowed[0])
        self._persist_i2v_gen_params()

    def _parse_generate_count(self) -> int:
        if self.kind != "i2v" or not hasattr(self, "spin_generate_count"):
            return 1
        try:
            return max(1, min(10, int(self.spin_generate_count.get())))
        except (TypeError, ValueError, tk.TclError):
            return 1

    def _i2v_gen_params_from_ui(self) -> dict[str, str | int]:
        model = (
            self._model_var.get().strip()
            if hasattr(self, "_model_var")
            else str(I2V_JIMENG_PARAMS["model"])
        )
        res_raw = (
            self._resolution_var.get()
            if hasattr(self, "_resolution_var")
            else str(I2V_JIMENG_PARAMS["resolution"])
        )
        return resolve_i2v_gen_params(
            {
                "model": model,
                "resolution": normalize_i2v_resolution(res_raw),
                "generate_count": self._parse_generate_count(),
                "duration_sec": int(I2V_JIMENG_PARAMS["duration_sec"]),
                "aspect_ratio": "16:9",
                "ref_mode": str(I2V_JIMENG_PARAMS.get("ref_mode") or "全能参考"),
            }
        )

    def _persist_i2v_gen_params(self) -> None:
        if self.kind != "i2v":
            return
        try:
            params = self._i2v_gen_params_from_ui()
            if hasattr(self, "spin_generate_count"):
                self.spin_generate_count.set(str(int(params["generate_count"])))
            if hasattr(self, "_resolution_var"):
                self._resolution_var.set(str(params["resolution"]).replace("P", "p"))
            if hasattr(self, "cmb_resolution"):
                self.cmb_resolution.configure(
                    values=list(resolutions_for_i2v_model(str(params["model"])))
                )
            save_lab_params("i2v", params)
        except Exception:
            pass

    def _jimeng_login_button_text(self, *, logged_in: bool) -> str:
        return "已登录" if logged_in else "登录即梦"

    def _set_jimeng_login_button(self, *, logged_in: bool) -> None:
        if not hasattr(self, "btn_jimeng_login"):
            return
        self.btn_jimeng_login.configure(
            text=self._jimeng_login_button_text(logged_in=logged_in)
        )

    def _refresh_jimeng_login_ui(self) -> None:
        if self.kind != "i2v" or not hasattr(self, "btn_jimeng_login"):
            return

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
                schedule_on_main(self, self._log, f"[即梦] 登录完成：{st.detail}")
                schedule_on_main(
                    self,
                    self._set_jimeng_login_button,
                    logged_in=st.is_logged_in,
                )
                if st.is_logged_in:
                    schedule_on_main(self, self._reload_jimeng_quota)
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._log, f"[即梦] 登录失败：{exc}")

        threading.Thread(target=job, daemon=True).start()

    def _sync_rain_label(self, *_args) -> None:
        if self.kind == "i2v" or not hasattr(self, "_rain_label"):
            return
        mode = normalize_rain_mode(self._rain_var.get())
        label = RAIN_MODE_LABELS.get(mode, mode)
        self._rain_label.configure(text=label)

    def _reset_confirm_button(self) -> None:
        self.btn_confirm.configure(text=_CONFIRM_BTN_LABEL)

    def _review_passed(self) -> bool:
        return self._loop_result is not None and bool(self._loop_result.agreed)

    def _set_confirm_enabled(self, enabled: bool) -> None:
        """仅在 Gemini 审稿通过时可点；样式始终 Primary 蓝。"""
        self.btn_confirm.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def _set_i2v_generate_progress(self, credits: int, pct: int) -> None:
        self.btn_confirm.configure(text=f"{int(credits)} 造梦进度 {int(pct)}%")

    def _reload_jimeng_quota(self) -> None:
        if self._jm_quota is not None:
            self._jm_quota.reload()

    def _image_dialog_initialdir(self) -> str:
        """参考截图对话框：优先上次所选目录，其次当前参考图所在目录。"""
        if self._ref_image is not None:
            parent = self._ref_image.parent
            if parent.is_dir():
                return str(parent)
        try:
            saved = str(lab_params(self.kind).get("last_ref_image_dir") or "").strip()  # type: ignore[arg-type]
        except Exception:
            saved = ""
        if saved and Path(saved).is_dir():
            return saved
        return str(Path.home())

    def _remember_ref_image_dir(self, path: Path) -> None:
        directory = path if path.is_dir() else path.parent
        if not directory.is_dir():
            return
        try:
            save_lab_params(
                self.kind,  # type: ignore[arg-type]
                {"last_ref_image_dir": str(directory.resolve())},
            )
        except Exception:
            pass

    def _pick_image(self) -> None:
        path = filedialog.askopenfilename(
            title="选择参考截图",
            initialdir=self._image_dialog_initialdir(),
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All", "*.*")],
        )
        if not path:
            return
        self._ref_image = Path(path)
        self._img_label.configure(text=self._ref_image.name, foreground="")
        self._remember_ref_image_dir(self._ref_image)
        self._schedule_save_session()
        self.sync_right_preview()

    def _session_payload(self) -> dict:
        conflicts: list[dict[str, str]] = []
        agreed: bool | None = None
        if self._loop_result is not None:
            agreed = self._loop_result.agreed
            conflicts = list(self._loop_result.unresolved_conflicts)
        fail = self.atoms.fail_tags()
        return {
            "rain_mode": normalize_rain_mode(self._rain_var.get()),
            "scene_keywords": self._scene_var.get().strip(),
            "ref_image": str(self._ref_image) if self._ref_image else "",
            "slots": self.atoms.get_slots(),
            "fail_tags": {k: sorted(v) for k, v in fail.items()},
            "selected_run_id": self._selected_run_id or "",
            "status": self._status_var.get(),
            "round_label": self._round_var.get(),
            "review_agreed": agreed,
            "unresolved_conflicts": conflicts,
            "loop_review": self._loop_result.to_review_json() if self._loop_result else None,
            "confirmed": self._confirmed,
        }

    def _schedule_save_session(self) -> None:
        if self._session_save_after_id is not None:
            try:
                self.after_cancel(self._session_save_after_id)
            except tk.TclError:
                pass
        self._session_save_after_id = self.after(300, self.save_session_now)

    def _restore_session(self) -> bool:
        data = load_agent_session(self.kind)  # type: ignore[arg-type]
        if not data:
            return False
        self._rain_var.set(data.get("rain_mode") or DEFAULT_RAIN_MODE)
        self._scene_var.set(str(data.get("scene_keywords") or ""))
        ref = str(data.get("ref_image") or "").strip()
        if ref:
            ref_path = Path(ref)
            if ref_path.is_file():
                self._ref_image = ref_path
                if hasattr(self, "_img_label"):
                    self._img_label.configure(text=self._ref_image.name, foreground="")
            self._remember_ref_image_dir(ref_path)
        self._round_var.set(str(data.get("round_label") or "轮次 —"))
        # 不自动选中上次 run；仅手动点实验记录才灌该次标签
        self._selected_run_id = None
        self._confirmed = bool(data.get("confirmed"))
        # 先恢复审核态，再灌标签，避免 set_slots→on_change 在 loop 未就绪时改状态
        loop = loop_result_from_review_json(data.get("loop_review"))
        if loop is not None:
            self._loop_result = loop
        self.atoms.set_slots(data.get("slots") or {})
        fail_raw = data.get("fail_tags") or {}
        fail_map = {
            k: set(str(t).strip() for t in (fail_raw.get(k) or []) if str(t).strip())
            for k in fail_raw
        }
        if any(fail_map.values()):
            self.atoms.set_fail_tags(fail_map)
        elif data.get("unresolved_conflicts"):
            self.atoms.set_fail_tags(conflict_tag_set(data["unresolved_conflicts"]))
        # 会话里的状态文案优先（含「已改标签」）；再按审核结果开生成钮
        self._status_var.set(str(data.get("status") or "待草稿"))
        if loop is not None:
            if loop.fail_slots:
                self.atoms.set_fail_slots(set(loop.fail_slots))
            self._show_loop_detail(loop)
            self._set_confirm_enabled(bool(loop.agreed))
        else:
            self._set_confirm_enabled(False)
        return True

    def _init_session_once(self) -> None:
        self._restore_session()
        self._refresh_runs_async(after=self._after_runs_loaded)

    def _after_runs_loaded(self) -> None:
        try:
            self.run_list.selection_clear(0, tk.END)
        except tk.TclError:
            pass
        self.sync_right_preview()

    def _on_atoms_changed(self) -> None:
        # 人工改标签：仅审稿已通过时仍可生成；未通过则保持不可点
        if self._loop_result is not None:
            self._confirmed = False
            if self._review_passed():
                self._set_confirm_enabled(True)
                self._status_var.set("已改标签 · 可生成")
            else:
                self._set_confirm_enabled(False)
                self._status_var.set("已改标签 · 需审稿通过后生成")
        self.sync_right_preview()
        self._schedule_save_session()

    def on_tab_selected(self) -> None:
        if self.kind == "i2v":
            self._reload_jimeng_quota()
            self._refresh_jimeng_login_ui()
        if not self._loaded_once:
            self._loaded_once = True
            self.after(120, self._init_session_once)
            return
        self._refresh_runs_async()

    def sync_right_preview(self) -> None:
        if self._preview_after_id is not None:
            try:
                self.after_cancel(self._preview_after_id)
            except tk.TclError:
                pass
        self._preview_after_id = self.after(80, self._sync_preview_now)

    def _sync_preview_now(self) -> None:
        self._preview_after_id = None
        slots = self.atoms.get_slots()
        run_id = self._selected_run_id
        image = self._ref_image if self.kind == "i2v" else None
        if not run_id:
            self._emit_preview(None, "—", slots, image)
            return

        self._preview_load_token += 1
        token = self._preview_load_token
        kind = self.kind

        def work() -> None:
            video: Path | None = None
            preview_run_id = run_id
            preview_slots = slots
            preview_image = image
            try:
                run = load_agent_run(kind, run_id)  # type: ignore[arg-type]
                preview_run_id = run.run_id
                if run.video_path.is_file():
                    video = run.video_path
                if kind == "i2v":
                    for name in ("ref_image.png", "ref_image.jpg"):
                        p = run.dir / name
                        if p.is_file():
                            preview_image = p
                            break
            except FileNotFoundError:
                pass

            def apply() -> None:
                if token != self._preview_load_token:
                    return
                self._emit_preview(video, preview_run_id, preview_slots, preview_image)

            schedule_on_main(self, apply)

        threading.Thread(target=work, daemon=True).start()

    def _emit_preview(
        self,
        video: Path | None,
        run_id: str,
        slots: dict[str, list[str]],
        image: Path | None,
    ) -> None:
        if not self._on_preview_run:
            return
        kwargs: dict = {"kind": self.kind}
        if self.kind == "i2v":
            kwargs["image_path"] = image
        self._on_preview_run(video, run_id, slots, **kwargs)

    def save_session_now(self) -> None:
        self._session_save_after_id = None
        try:
            save_agent_session(self.kind, self._session_payload())  # type: ignore[arg-type]
            params_update: dict = {
                "rain_mode": normalize_rain_mode(self._rain_var.get()),
                "scene_keywords": self._scene_var.get().strip(),
            }
            if self.kind == "i2v":
                params_update.update(self._i2v_gen_params_from_ui())
            save_lab_params(self.kind, params_update)  # type: ignore[arg-type]
        except Exception:
            pass

    def apply_theme(self, theme: UiTheme) -> None:
        del theme

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.btn_draft.configure(state=tk.DISABLED if busy else tk.NORMAL)
        if busy:
            self._set_confirm_enabled(False)
        else:
            self._set_confirm_enabled(self._review_passed())
        if self.kind == "i2v":
            combo_state = tk.DISABLED if busy else "readonly"
            if hasattr(self, "cmb_model"):
                self.cmb_model.configure(state=combo_state)
            if hasattr(self, "cmb_resolution"):
                self.cmb_resolution.configure(state=combo_state)
            if hasattr(self, "spin_generate_count"):
                self.spin_generate_count.configure(
                    state=tk.DISABLED if busy else tk.NORMAL
                )
            if hasattr(self, "btn_jimeng_login"):
                self.btn_jimeng_login.configure(
                    state=tk.DISABLED if busy else tk.NORMAL
                )

    def _start_loop(self) -> None:
        if self._busy:
            return
        if self.kind == "i2v" and (not self._ref_image or not self._ref_image.is_file()):
            messagebox.showwarning(self.title, "请先选择参考截图。")
            return
        scene = self._scene_var.get().strip()
        if self.kind == "t2v" and not scene:
            messagebox.showwarning(self.title, "请填写场景关键字。")
            return
        rain = normalize_rain_mode(self._rain_var.get())
        images = [self._ref_image] if self.kind == "i2v" and self._ref_image else None
        self._set_busy(True)
        self._status_var.set("Jimeng×Gemini 审核中…")
        self._round_var.set("轮次 0/3")
        self._confirmed = False
        self._loop_result = None
        self._set_confirm_enabled(False)

        def work() -> None:
            try:
                result = run_agent_review_loop(
                    kind=self.kind,
                    rain_mode=rain,
                    scene_keywords=scene if self.kind == "t2v" else (scene or "见图"),
                    images=images,
                    log_fn=lambda m: schedule_on_main(self, self._log, m),
                )
                schedule_on_main(self, self._apply_loop_result, result)
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._loop_failed, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _loop_failed(self, msg: str) -> None:
        self._set_busy(False)
        self._reset_confirm_button()
        self._status_var.set("失败")
        self._log(f"[{self.title}] {msg}")
        messagebox.showerror(self.title, msg)
        if self.kind == "i2v":
            self._reload_jimeng_quota()

    def _apply_loop_result(self, result: LoopResult) -> None:
        self._loop_result = result
        self.atoms.set_slots(result.slots)
        if self.kind == "i2v" and result.rain_mode:
            self._rain_var.set(normalize_rain_mode(result.rain_mode))
        n = len(result.rounds)
        self._round_var.set(f"轮次 {n}/3")
        if result.agreed:
            self._status_var.set("审稿通过 · 可生成")
            self.atoms.set_fail_tags({k: set() for k in result.slots})
            self.atoms.set_fail_slots(set())
            self._confirmed = False
            self._set_busy(False)
            self._set_confirm_enabled(True)
        else:
            self._status_var.set("3轮未通过 · 冲突已标红 · 生成不可用")
            self.atoms.set_fail_tags(conflict_tag_set(result.unresolved_conflicts))
            self.atoms.set_fail_slots(set(result.fail_slots or []))
            self._log(
                f"[{self.title}] Gemini 审稿三轮都没通过，"
                "「生成视频」保持不可点击；请改标签后重新草稿+审核"
            )
            self._confirmed = False
            self._set_busy(False)
            self._set_confirm_enabled(False)
        if self.kind == "i2v" and result.series_goal:
            goal = series_goal_label(result.series_goal)
            self._log(f"[{self.title}] 雨档={result.rain_mode} · 目标系列={goal}")
        self._show_loop_detail(result)
        self._preview_slots(result.slots, video=None)
        self._schedule_save_session()

    def _show_loop_detail(self, result: LoopResult) -> None:
        lines = [
            f"达成一致: {'是' if result.agreed else '否'}",
            f"轮次: {len(result.rounds)}/3",
        ]
        if result.rain_mode:
            lines.append(f"雨档: {result.rain_mode}")
        if result.series_goal:
            lines.append(f"目标系列: {series_goal_label(result.series_goal)} ({result.series_goal})")
        lines.append("")
        for r in result.rounds:
            lines.append(f"── 第 {r.round} 轮 ({r.source}) ──")
            rev = r.review or r.comparison or {}
            if self.kind == "i2v":
                lines.append(f"Jimeng rain={r.jimeng_rain_mode or '—'}")
                lines.append(_format_slots_brief(r.jimeng_slots or r.draft_slots))
            lines.append(f"verdict: {rev.get('verdict', rev.get('agreed'))}")
            for iss in rev.get("issues") or []:
                lines.append(
                    f"  · [{iss.get('slot')}] {iss.get('tag')}: {iss.get('problem')}"
                )
            for m in rev.get("missing") or []:
                if isinstance(m, dict):
                    lines.append(
                        f"  · 缺失 [{m.get('slot')}]: {m.get('description')}"
                    )
                else:
                    lines.append(f"  · 缺失/应补充: {m}")
            for d in rev.get("duplicates") or []:
                lines.append(f"  · 重复: {d}")
            for q in rev.get("questions") or []:
                lines.append(f"  · 疑问: {q}")
            for qa in r.handbook_qa or rev.get("handbook_qa") or []:
                if isinstance(qa, dict):
                    lines.append(f"  · 手册答：{(qa.get('question') or '')[:40]}")
                    ans = str(qa.get("answer") or "").strip()
                    if ans:
                        lines.append(f"      {ans[:120]}{'…' if len(ans) > 120 else ''}")
            lines.append("")
        if result.handbook_qa:
            lines.append("本轮写入 Seedance 手册：")
            for qa in result.handbook_qa:
                lines.append(f"  · {qa.get('title') or qa.get('question') or ''}")
            lines.append("")
        if result.unresolved_conflicts:
            lines.append("未决冲突标签:")
            for c in result.unresolved_conflicts:
                lines.append(f"  · [{c.get('slot')}] {c.get('tag')}")
        if result.fail_slots:
            lines.append("槽位标题标红（Gemini 认为缺失且 Jimeng 无对应标签）:")
            for s in result.fail_slots:
                lines.append(f"  · {s}")
        self._set_detail("\n".join(lines))

    def _set_detail(self, text: str) -> None:
        self.detail.configure(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.insert("1.0", text)
        self.detail.configure(state=tk.DISABLED)

    def _preview_slots(
        self,
        slots: dict[str, list[str]],
        *,
        video: Path | None,
        run_id: str = "草稿",
    ) -> None:
        if not self._on_preview_run:
            return
        kwargs = {"kind": self.kind}
        if self.kind == "i2v":
            kwargs["image_path"] = self._ref_image
        self._on_preview_run(video, run_id, slots, **kwargs)

    def _start_generate(self) -> None:
        if self._busy:
            return
        if not self._review_passed():
            messagebox.showwarning(self.title, "需 Gemini 审稿通过后才能生成视频。")
            return
        slots = self.atoms.get_slots()
        if not any(slots.values()):
            messagebox.showwarning(self.title, "原子表为空。")
            return
        if self.kind == "i2v" and (not self._ref_image or not self._ref_image.is_file()):
            messagebox.showwarning(self.title, "请先选择参考截图。")
            return
        if self.kind == "i2v":
            self._persist_i2v_gen_params()
            gen = self._i2v_gen_params_from_ui()
            count = int(gen["generate_count"])
            confirm_msg = (
                f"确认用当前原子表生成视频？\n"
                f"{gen['model']} · 16:9 · {str(gen['resolution']).replace('P', 'p')} · "
                f"{gen['duration_sec']}s × {count}"
            )
        else:
            gen = {}
            count = 1
            confirm_msg = "确认用当前原子表生成视频？"
        if not messagebox.askyesno(self.title, confirm_msg):
            return
        rain = normalize_rain_mode(
            self._loop_result.rain_mode
            if self.kind == "i2v" and self._loop_result and self._loop_result.rain_mode
            else self._rain_var.get()
        )
        series_goal = self._loop_result.series_goal if self._loop_result else ""
        scene = self._scene_var.get().strip()
        prompt = compose_prompt(slots)
        review = self._loop_result.to_review_json() if self._loop_result else {}
        if self.kind == "i2v":
            dur = int(gen["duration_sec"])
            model = str(gen["model"])
            aspect = "16:9"
            resolution = str(gen["resolution"])
            ref_mode = str(gen.get("ref_mode") or "全能参考")
        else:
            params = lab_params(self.kind)  # type: ignore[arg-type]
            dur = int(params.get("duration_sec", 5))
            model = str(params.get("model") or "Seedance 2.0 Fast VIP")
            aspect = str(params.get("aspect_ratio") or "16:9")
            resolution = str(params.get("resolution") or "720P")
            ref_mode = ""
        self._set_busy(True)
        self._status_var.set("生成视频中…")
        est = 0
        if self.kind == "i2v":
            est = estimate_jimeng_video_credits(
                duration_sec=dur, resolution=resolution, model=model
            )
            self._set_i2v_generate_progress(est, 0)

        def work() -> None:
            credit_holder = {"v": est if self.kind == "i2v" else 0}
            last_run_id = ""

            def on_credits(cost: int) -> None:
                credit_holder["v"] = cost
                if self.kind == "i2v":
                    schedule_on_main(self, self._set_i2v_generate_progress, cost, 0)

            def progress(pct: int) -> None:
                if self.kind == "i2v":
                    schedule_on_main(
                        self,
                        self._set_i2v_generate_progress,
                        credit_holder["v"],
                        pct,
                    )

            try:
                ensure_cli_path()
                from jimeng_web.client import JimengWebClient

                client = JimengWebClient()
                for i in range(count):
                    if count > 1:
                        schedule_on_main(
                            self,
                            self._log,
                            f"[{self.title}] 生成 {i + 1}/{count} …",
                        )
                        schedule_on_main(self, self._status_var.set, f"生成视频中… {i + 1}/{count}")
                    run = create_agent_run(
                        self.kind,  # type: ignore[arg-type]
                        prompt=prompt,
                        rain_mode=rain,
                        slots=slots,
                        scene_keywords=scene,
                        duration_sec=dur,
                        ref_image=self._ref_image if self.kind == "i2v" else None,
                        review=review,
                        series_goal=series_goal,
                    )
                    last_run_id = run.run_id
                    if self.kind == "t2v":
                        client.generate_t2v(
                            prompt,
                            run.video_path,
                            duration_sec=dur,
                            model=model,
                            aspect_ratio=aspect,
                            resolution=resolution,
                            log=lambda m: schedule_on_main(self, self._log, m),
                        )
                    else:
                        assert self._ref_image is not None
                        if i > 0:
                            schedule_on_main(self, self._set_i2v_generate_progress, credit_holder["v"], 0)
                        client.generate_i2v(
                            self._ref_image,
                            prompt,
                            run.video_path,
                            duration_sec=dur,
                            model=model,
                            aspect_ratio=aspect,
                            resolution=resolution,
                            ref_mode=ref_mode,
                            log=lambda m: schedule_on_main(self, self._log, m),
                            progress=progress,
                            on_credits=on_credits,
                        )
                    if credit_holder["v"] > 0:
                        run.update_meta(jimeng_credits=int(credit_holder["v"]))
                    if _AUTO_VIRAL_SCORE_AFTER_GENERATE:
                        try:
                            youtube_viral_score(
                                run,
                                log_fn=lambda m: schedule_on_main(self, self._log, m),
                                rain_mode=rain,
                                series_goal=series_goal or None,
                            )
                        except Exception as exc:  # noqa: BLE001
                            schedule_on_main(
                                self, self._log, f"[{self.title}] 油管打分失败：{exc}"
                            )
                schedule_on_main(self, self._generate_done, last_run_id)
            except Exception as exc:  # noqa: BLE001
                schedule_on_main(self, self._loop_failed, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _generate_done(self, run_id: str) -> None:
        self._set_busy(False)
        self._reset_confirm_button()
        self._confirmed = True
        self._status_var.set(f"完成 · {run_id}")
        if self.kind == "i2v":
            self._reload_jimeng_quota()
        self._refresh_runs_async(after=lambda: self._select_run(run_id))
        self._schedule_save_session()

    def _refresh_runs_async(self, *, after: Callable[[], None] | None = None) -> None:
        self._runs_refresh_token += 1
        token = self._runs_refresh_token
        kind = self.kind

        def work() -> None:
            try:
                runs = list_agent_runs_light(kind)  # type: ignore[arg-type]
            except Exception:
                runs = []

            def apply() -> None:
                if token != self._runs_refresh_token:
                    return
                self._runs = runs
                self.run_list.delete(0, tk.END)
                for run in self._runs:
                    self.run_list.insert(tk.END, _format_run_list_line(run))
                if after:
                    after()

            schedule_on_main(self, apply)

        threading.Thread(target=work, daemon=True).start()

    def _refresh_runs(self) -> None:
        self._refresh_runs_async()

    def _on_run_select(self, _event=None) -> None:
        sel = self.run_list.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._runs):
            return
        self._select_run(self._runs[idx].run_id)

    def _select_run(
        self, run_id: str, *, preview: bool = True, load_slots: bool = True
    ) -> None:
        self._selected_run_id = run_id
        self._run_load_token += 1
        token = self._run_load_token
        kind = self.kind

        def work() -> None:
            try:
                run = load_agent_run(kind, run_id)  # type: ignore[arg-type]
            except FileNotFoundError:
                return

            def apply() -> None:
                if token != self._run_load_token:
                    return
                self._apply_loaded_run(run, preview=preview, load_slots=load_slots)

            schedule_on_main(self, apply)

        threading.Thread(target=work, daemon=True).start()

    def _apply_loaded_run(
        self, run: AgentRun, *, preview: bool = True, load_slots: bool = True
    ) -> None:
        if load_slots:
            slots = slots_from_agent_run(run)
            self.atoms.set_slots(slots)
            conflicts = (run.review or {}).get("unresolved_conflicts") or []
            if conflicts:
                self.atoms.set_fail_tags(conflict_tag_set(conflicts))
            fail_slots = (run.review or {}).get("fail_slots") or []
            if fail_slots:
                self.atoms.set_fail_slots(set(str(s) for s in fail_slots))
        else:
            slots = self.atoms.get_slots()
        self._show_run_detail(run)
        if preview and self._on_preview_run:
            video = run.video_path if run.video_path.is_file() else None
            img = None
            if self.kind == "i2v":
                for name in ("ref_image.png", "ref_image.jpg"):
                    p = run.dir / name
                    if p.is_file():
                        img = p
                        self._ref_image = p
                        if hasattr(self, "_img_label"):
                            self._img_label.configure(text=p.name, foreground="")
                        break
            kwargs = {"kind": self.kind}
            if img:
                kwargs["image_path"] = img
            self._on_preview_run(video, run.run_id, slots, **kwargs)
        self._schedule_save_session()

    def _show_run_detail(self, run: AgentRun) -> None:
        lines = [
            f"run_id: {run.run_id}",
            f"雨档: {(run.meta or {}).get('rain_label')}",
            f"场景: {(run.meta or {}).get('scene_keywords')}",
            f"成片: {'有' if run.video_path.is_file() else '无'}",
        ]
        jc = (run.meta or {}).get("jimeng_credits")
        if jc is not None:
            lines.append(f"消耗积分: {jc}")
        lines.append("")
        rev = run.review or {}
        if rev:
            lines.append(f"审核达成: {rev.get('agreed')}")
            if rev.get("unresolved_conflicts"):
                lines.append("冲突标签:")
                for c in rev["unresolved_conflicts"]:
                    lines.append(f"  · [{c.get('slot')}] {c.get('tag')}")
            lines.append("")
        viral = run.viral_score or {}
        if viral:
            goal = viral.get("series_goal_label") or viral.get("series_goal") or ""
            lines.append(
                f"黑马评分: score={viral.get('score')} verdict={viral.get('verdict')}"
                + (f" · 目标={goal}" if goal else "")
            )
            bc = viral.get("benchmark_count")
            if bc is not None:
                lines.append(
                    f"基准: Top{bc} · 缓存命中 {viral.get('benchmark_cache_hits', 0)}"
                )
            dims = viral.get("dimensions") or {}
            if dims:
                lines.append(
                    "维度: "
                    + ", ".join(f"{k}={v}" for k, v in list(dims.items())[:6])
                )
            for n in viral.get("notes") or []:
                lines.append(f"  · {n}")
            if viral.get("youtube_title_hint"):
                lines.append(f"标题灵感: {viral.get('youtube_title_hint')}")
            lines.append("")
        lines.append("送模正文:")
        lines.append(run.prompt or "")
        self._set_detail("\n".join(lines))
