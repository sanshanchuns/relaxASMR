"""Minimal parser for asmr_config.lua return-table format."""

from __future__ import annotations

import re
from pathlib import Path


def _strip_comments(text: str) -> str:
    return re.sub(r"--[^\n]*", "", text)


def _parse_paths(block: str) -> list[str]:
    return re.findall(r'"([^"]+)"', block)


def _extract_brace_blocks(section: str) -> list[str]:
    blocks: list[str] = []
    depth = 0
    start: int | None = None
    for i, ch in enumerate(section):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                blocks.append(section[start : i + 1])
                start = None
    return blocks


def _parse_layer_block(block: str) -> dict:
    layer: dict = {}
    m = re.search(r"track\s*=\s*(\d+)", block)
    if m:
        layer["track"] = int(m.group(1))
    m = re.search(r'id\s*=\s*"([^"]+)"', block)
    if m:
        layer["id"] = m.group(1)
    m = re.search(r'name\s*=\s*"([^"]+)"', block)
    if m:
        layer["name"] = m.group(1)
    m = re.search(r"vol\s*=\s*([\d.]+)", block)
    if m:
        layer["vol"] = float(m.group(1))
    m = re.search(r"min_gap_min\s*=\s*([\d.]+)", block)
    if m:
        layer["min_gap_min"] = float(m.group(1))
    m = re.search(r"max_gap_min\s*=\s*([\d.]+)", block)
    if m:
        layer["max_gap_min"] = float(m.group(1))
    m = re.search(r"randomness\s*=\s*([\d.]+)", block)
    if m:
        layer["randomness"] = float(m.group(1))
    m = re.search(r"count\s*=\s*(\d+)", block)
    if m:
        layer["count"] = int(m.group(1))
    if re.search(r"clear_existing\s*=\s*true", block):
        layer["clear_existing"] = True
    pm = re.search(r"paths\s*=\s*\{([^}]*)\}", block, re.DOTALL)
    if pm:
        layer["paths"] = _parse_paths(pm.group(1))
    vem = re.search(r"vol_envelope\s*=\s*\{([^}]*)\}", block, re.DOTALL)
    if vem:
        ve_body = vem.group(1)
        ve: dict = {}
        sm = re.search(r'shape\s*=\s*"([^"]+)"', ve_body)
        if sm:
            ve["shape"] = sm.group(1)
        dm = re.search(r"depth\s*=\s*([\d.]+)", ve_body)
        if dm:
            ve["depth"] = float(dm.group(1))
        pam = re.search(r'peak_at\s*=\s*"([^"]+)"', ve_body)
        if pam:
            ve["peak_at"] = pam.group(1)
        layer["vol_envelope"] = ve
    return layer


def _parse_layer_list(section: str) -> list[dict]:
    layers = []
    for block in _extract_brace_blocks(section):
        if "track" not in block:
            continue
        layer = _parse_layer_block(block)
        if layer.get("track"):
            layers.append(layer)
    return layers


def _section_body(text: str, name: str) -> str | None:
    m = re.search(rf"{name}\s*=\s*\{{", text)
    if not m:
        return None
    start = m.end() - 1
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
    return None


def load_asmr_config(path: Path) -> dict:
    text = _strip_comments(path.read_text(encoding="utf-8"))
    cfg: dict = {}

    m = re.search(r'scene_id\s*=\s*"([^"]+)"', text)
    if m:
        cfg["scene_id"] = m.group(1)
    m = re.search(r'project_name\s*=\s*"([^"]+)"', text)
    if m:
        cfg["project_name"] = m.group(1)
    m = re.search(r"duration_hours\s*=\s*([\d.]+)", text)
    if m:
        cfg["duration_hours"] = float(m.group(1))
    m = re.search(r"fade_sec\s*=\s*([\d.]+)", text)
    if m:
        cfg["fade_sec"] = float(m.group(1))

    vm = re.search(r"video\s*=\s*\{([^{}]*)\}", text, re.DOTALL)
    if vm:
        vb = vm.group(1)
        video: dict = {}
        t = re.search(r"track\s*=\s*(\d+)", vb)
        if t:
            video["track"] = int(t.group(1))
        n = re.search(r'name\s*=\s*"([^"]+)"', vb)
        if n:
            video["name"] = n.group(1)
        p = re.search(r'path\s*=\s*"([^"]+)"', vb)
        if p:
            video["path"] = p.group(1)
        cfg["video"] = video

    loop_body = _section_body(text, "loop_layers")
    if loop_body:
        cfg["loop_layers"] = _parse_layer_list(loop_body)

    scatter_body = _section_body(text, "scatter_layers")
    if scatter_body:
        cfg["scatter_layers"] = _parse_layer_list(scatter_body)

    return cfg
