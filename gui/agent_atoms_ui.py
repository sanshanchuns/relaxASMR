"""文生/图生子 Tab 共用的六槽原子标签表（轻量：增删、标红，不拖拽）。"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import simpledialog, ttk

from scripts.aigc_lab.prompt_atoms import SLOT_LABELS, SLOT_ORDER

_FAIL_BORDER = "#c62828"
_OK_BORDER = "#9e9e9e"
_THICK = 2
_REFLOW_DEBOUNCE_MS = 120
_LAYOUT_FREEZE_MS = 180
_WIDTH_EPS = 12


class AtomTable(ttk.Frame):
    def __init__(
        self,
        master,
        *,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._on_change = on_change
        self._atoms: dict[str, list[str]] = {k: [] for k in SLOT_ORDER}
        self._fail: dict[str, set[str]] = {k: set() for k in SLOT_ORDER}
        self._fail_slots: set[str] = set()
        self._slot_labels: dict[str, ttk.Label] = {}
        self._areas: dict[str, tk.Frame] = {}
        self._chip_widgets: dict[str, dict[str, tk.Frame]] = {k: {} for k in SLOT_ORDER}
        self._reflow_guard: dict[str, bool] = {k: False for k in SLOT_ORDER}
        self._reflow_after: dict[str, str | None] = {k: None for k in SLOT_ORDER}
        self._last_width: dict[str, int] = {k: 0 for k in SLOT_ORDER}
        self._layout_frozen = False
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="槽位").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(self, text="原子标签（单击标红；双击编辑；×删除）").grid(
            row=0, column=1, sticky="w"
        )

        for i, key in enumerate(SLOT_ORDER, start=1):
            slot_lbl = ttk.Label(self, text=SLOT_LABELS.get(key, key), width=6)
            slot_lbl.grid(row=i, column=0, sticky="nw", pady=4)
            self._slot_labels[key] = slot_lbl
            area = tk.Frame(self)
            area.grid(row=i, column=1, sticky="ew", pady=4)
            area.bind(
                "<Configure>",
                lambda _e, k=key: self._on_area_configure(k),
            )
            self._areas[key] = area
            add = ttk.Button(
                self, text="+", width=3, command=lambda k=key: self._add_tag(k)
            )
            add.grid(row=i, column=2, sticky="ne", padx=(4, 0), pady=4)

    def get_slots(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._atoms.items()}

    def set_slots(self, slots: dict[str, list[str]]) -> None:
        cleaned = {
            key: [str(x).strip() for x in (slots.get(key) or []) if str(x).strip()]
            for key in SLOT_ORDER
        }
        if cleaned == self.get_slots():
            return
        self._layout_frozen = True
        for key in SLOT_ORDER:
            self._atoms[key] = cleaned[key]
            self._last_width[key] = 0
            self._reflow_slot(key)
        self.update_idletasks()
        self.after(_LAYOUT_FREEZE_MS, self._unfreeze_layout)
        self._fire()

    def set_fail_tags(self, fails: dict[str, set[str]]) -> None:
        for key in SLOT_ORDER:
            wanted = fails.get(key) or set()
            present = set(self._atoms.get(key) or [])
            self._fail[key] = {t for t in wanted if t in present}
        if self._sync_fail_borders() and not self._fail_slots:
            return
        self._reflow_all()

    def set_fail_slots(self, slots: set[str] | list[str]) -> None:
        wanted = {s for s in slots if s in SLOT_ORDER}
        if wanted == self._fail_slots:
            return
        self._fail_slots = wanted
        self._sync_slot_label_borders()

    def fail_slots(self) -> set[str]:
        return set(self._fail_slots)

    def _sync_slot_label_borders(self) -> None:
        for key, lbl in self._slot_labels.items():
            try:
                if key in self._fail_slots:
                    lbl.configure(foreground=_FAIL_BORDER)
                else:
                    lbl.configure(foreground="")
            except tk.TclError:
                pass

    def fail_tags(self) -> dict[str, set[str]]:
        return {k: set(v) for k, v in self._fail.items()}

    def _fire(self) -> None:
        if self._on_change:
            self._on_change()

    def _unfreeze_layout(self) -> None:
        self._layout_frozen = False
        for key in SLOT_ORDER:
            area = self._areas.get(key)
            if area is not None and area.winfo_width() > 1:
                self._last_width[key] = area.winfo_width()

    def _on_area_configure(self, slot: str) -> None:
        if self._layout_frozen or self._reflow_guard.get(slot):
            return
        if not self._atoms.get(slot):
            return
        area = self._areas.get(slot)
        if area is None:
            return
        width = area.winfo_width()
        if width <= 1:
            return
        if abs(width - self._last_width.get(slot, 0)) < _WIDTH_EPS:
            return
        pending = self._reflow_after.get(slot)
        if pending is not None:
            try:
                self.after_cancel(pending)
            except tk.TclError:
                pass
        self._reflow_after[slot] = self.after(
            _REFLOW_DEBOUNCE_MS, lambda s=slot: self._reflow_slot(s)
        )

    def _sync_fail_borders(self) -> bool:
        """就地更新红框，避免整槽重建。全部成功返回 True。"""
        ok = True
        for slot in SLOT_ORDER:
            widgets = self._chip_widgets.get(slot) or {}
            for tag, wrap in widgets.items():
                try:
                    if not wrap.winfo_exists():
                        ok = False
                        continue
                    failed = tag in self._fail[slot]
                    wrap.configure(
                        highlightbackground=_FAIL_BORDER if failed else _OK_BORDER
                    )
                except tk.TclError:
                    ok = False
        return ok

    def _add_tag(self, slot: str) -> None:
        text = simpledialog.askstring("新标签", f"为【{SLOT_LABELS.get(slot, slot)}】添加原子：")
        if not text or not text.strip():
            return
        tag = text.strip()
        if tag not in self._atoms[slot]:
            self._atoms[slot].append(tag)
            self._last_width[slot] = 0
            self._reflow_slot(slot)
            self._fire()

    def _reflow_all(self) -> None:
        for key in SLOT_ORDER:
            self._last_width[key] = 0
            self._reflow_slot(key)

    def _reflow_slot(self, slot: str) -> None:
        area = self._areas.get(slot)
        if area is None:
            return
        if self._reflow_guard.get(slot):
            return
        self._reflow_guard[slot] = True
        self._reflow_after[slot] = None
        self._chip_widgets[slot] = {}
        try:
            for child in list(area.winfo_children()):
                try:
                    child.destroy()
                except tk.TclError:
                    pass

            tags = [t for t in self._atoms[slot] if t.strip()]
            self._atoms[slot] = tags

            width = area.winfo_width()
            if width <= 1:
                width = 360
            max_w = max(width - 6, 120)
            pad = 4

            row = tk.Frame(area, bd=0)
            row.pack(fill=tk.X, anchor="w")
            row_w = 0

            for tag in tags:
                chip = self._make_chip(row, slot, tag)
                chip.pack(side=tk.LEFT, padx=(0, pad), pady=2)
                chip.update_idletasks()
                cw = max(chip.winfo_reqwidth(), 24) + pad
                if row_w > 0 and row_w + cw > max_w:
                    chip.destroy()
                    row = tk.Frame(area, bd=0)
                    row.pack(fill=tk.X, anchor="w")
                    row_w = 0
                    chip = self._make_chip(row, slot, tag)
                    chip.pack(side=tk.LEFT, padx=(0, pad), pady=2)
                    chip.update_idletasks()
                    cw = max(chip.winfo_reqwidth(), 24) + pad
                row_w += cw
                self._chip_widgets[slot][tag] = chip

            self._last_width[slot] = (
                area.winfo_width() if area.winfo_width() > 1 else width
            )
        finally:
            self._reflow_guard[slot] = False

    def _make_chip(self, parent: tk.Frame, slot: str, tag: str) -> tk.Frame:
        failed = tag in self._fail[slot]
        border = _FAIL_BORDER if failed else _OK_BORDER
        wrap = tk.Frame(parent, highlightbackground=border, highlightthickness=_THICK, bd=0)
        lbl = ttk.Label(wrap, text=tag, padding=(6, 2))
        lbl.pack(side=tk.LEFT)
        btn = ttk.Button(
            wrap, text="×", width=2, command=lambda: self._remove(slot, tag)
        )
        btn.pack(side=tk.LEFT)

        def toggle(_e=None, s=slot, t=tag) -> None:
            if t in self._fail[s]:
                self._fail[s].discard(t)
            else:
                self._fail[s].add(t)
            chip = self._chip_widgets.get(s, {}).get(t)
            if chip is not None:
                try:
                    chip.configure(
                        highlightbackground=(
                            _FAIL_BORDER if t in self._fail[s] else _OK_BORDER
                        )
                    )
                    self._fire()
                    return
                except tk.TclError:
                    pass
            self._reflow_slot(s)
            self._fire()

        def edit(_e=None, s=slot, t=tag) -> None:
            neo = simpledialog.askstring("编辑标签", "修改原子：", initialvalue=t)
            if neo is None:
                return
            neo = neo.strip()
            if not neo or neo == t:
                return
            atoms = self._atoms[s]
            if t in atoms:
                atoms[atoms.index(t)] = neo
            if t in self._fail[s]:
                self._fail[s].discard(t)
                self._fail[s].add(neo)
            self._last_width[s] = 0
            self._reflow_slot(s)
            self._fire()

        lbl.bind("<Button-1>", toggle)
        wrap.bind("<Button-1>", toggle)
        lbl.bind("<Double-Button-1>", edit)
        return wrap

    def _remove(self, slot: str, tag: str) -> None:
        self._atoms[slot] = [t for t in self._atoms[slot] if t != tag]
        self._fail[slot].discard(tag)
        self._last_width[slot] = 0
        self._reflow_slot(slot)
        self._fire()
