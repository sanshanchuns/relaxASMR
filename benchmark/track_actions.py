"""根据 RS-PASS + 工程结构生成可执行的轨级修改建议。"""

from __future__ import annotations

from rpp_context import IDEAL_LAYER_ENERGY, LAYER_ROLE, _has_material_keyword

# layer_id → 默认 Reaper 轨名
LAYER_TRACK_NAMES = {
    "1_rain": "1_rain",
    "2_impact": "2_impact",
    "3_environment": "3_environment",
    "4_water": "4_water",
    "5_wildlife": "5_wildlife",
    "6_human": "6_human",
}

FOREGROUND_LAYERS = ("2_impact", "6_human")
MID_LAYERS = ("3_environment", "4_water")
BACKGROUND_LAYERS = ("1_rain",)
SCATTER_LAYERS = ("5_wildlife",)


def _track_label(layer_id: str, layers: list[dict]) -> tuple[str, int | None]:
    for layer in layers:
        if layer.get("id") == layer_id:
            return layer.get("name") or layer_id, layer.get("track")
    return LAYER_TRACK_NAMES.get(layer_id, layer_id), None


def _label_text(track_num: int | None, layer_id: str, name: str) -> str:
    if track_num is not None:
        return f"轨 {track_num} · `{layer_id}` · {name}"
    return f"`{layer_id}` · {name}"


def _vol_action(
    layer_id: str,
    track_name: str,
    factor: float,
    reason: str,
    *,
    track_num: int | None = None,
    priority: str = "medium",
    auto_apply: bool = True,
) -> dict:
    factor = max(0.5, min(1.5, factor))
    pct = (factor - 1.0) * 100
    sign = "+" if pct >= 0 else ""
    label = _label_text(track_num, layer_id, track_name)
    return {
        "layer_id": layer_id,
        "track": track_num,
        "track_name": track_name,
        "action": "adjust_vol",
        "params": {"factor": round(factor, 3)},
        "priority": priority,
        "auto_apply": auto_apply,
        "reason": reason,
        "text": f"{label}：{reason}（音量 {sign}{pct:.0f}%）",
    }


def _note(
    layer_id: str | None,
    track_name: str | None,
    text: str,
    *,
    track_num: int | None = None,
    priority: str = "info",
    target: str = "track",
) -> dict:
    if track_name and layer_id:
        body = f"{_label_text(track_num, layer_id, track_name)}：{text}"
    elif track_name:
        body = f"轨 `{track_name}`：{text}"
    else:
        body = text
    return {
        "layer_id": layer_id,
        "track": track_num,
        "track_name": track_name,
        "target": target,
        "action": "note",
        "params": {},
        "priority": priority,
        "auto_apply": False,
        "reason": text,
        "text": body,
    }


def _layer_map(layers: list[dict]) -> dict[str, dict]:
    return {l["id"]: l for l in layers if l.get("id")}


def _merge_vol_actions(actions: list[dict]) -> list[dict]:
    """同轨 adjust_vol 合并为单一 factor。"""
    merged: dict[str, dict] = {}
    others: list[dict] = []
    for act in actions:
        if act.get("action") != "adjust_vol":
            others.append(act)
            continue
        key = act.get("layer_id") or act.get("track_name") or "?"
        if key not in merged:
            merged[key] = dict(act)
            continue
        prev = merged[key]
        f1 = prev["params"].get("factor", 1.0)
        f2 = act["params"].get("factor", 1.0)
        prev["params"]["factor"] = round(max(0.5, min(1.5, f1 * f2)), 3)
        prev["reason"] = prev["reason"] + "；" + act["reason"]
        f = prev["params"]["factor"]
        pct = (f - 1.0) * 100
        sign = "+" if pct >= 0 else ""
        lid = prev.get("layer_id") or key
        label = _label_text(
            prev.get("track"),
            lid,
            prev.get("track_name") or lid,
        )
        prev["text"] = f"{label}：{prev['reason']}（合计 {sign}{pct:.0f}%）"
    return others + list(merged.values())


def build_track_actions(result: dict, project: dict | None) -> list[dict]:
    if not project:
        return []

    mix = project.get("mix") or {}
    layers = mix.get("layers", [])
    if not layers:
        return []

    layer_by_id = _layer_map(layers)
    role_pct = mix.get("role_energy_pct", {})
    ideal_pct = mix.get("ideal_role_pct", {k: int(v * 100) for k, v in IDEAL_LAYER_ENERGY.items()})
    dims = result.get("dimensions", {})
    m = result.get("measurements", {})
    nt = result.get("noise_type", {})
    primary = nt.get("primary", "pink")
    mode = result.get("mode", "sleep")
    actions: list[dict] = []

    def layer_ref(lid: str) -> tuple[str, int | None]:
        return _track_label(lid, layers)

    # ── 三层能量 ──
    bg_actual = role_pct.get("background", 0)
    bg_target = ideal_pct.get("background", 10)
    if bg_actual > bg_target * 1.55:
        lid = "1_rain"
        if lid in layer_by_id and layer_by_id[lid].get("active", True) and layer_by_id[lid].get("vol", 0) > 0:
            ratio = bg_target / max(bg_actual, 1)
            factor = max(0.72, min(0.92, ratio ** 0.45))
            name, tnum = layer_ref(lid)
            actions.append(
                _vol_action(
                    lid,
                    name,
                    factor,
                    f"背景层 {bg_actual}% 高于目标 {bg_target}%",
                    track_num=tnum,
                    priority="high" if bg_actual > bg_target * 2 else "medium",
                )
            )

    fg_actual = role_pct.get("foreground", 0)
    fg_target = ideal_pct.get("foreground", 60)
    if fg_actual < fg_target * 0.55:
        boost = min(1.28, max(1.08, (fg_target / max(fg_actual, 1)) ** 0.35))
        for lid in FOREGROUND_LAYERS:
            if lid in layer_by_id and layer_by_id[lid].get("active", True) and layer_by_id[lid].get("vol", 0) > 0:
                name, tnum = layer_ref(lid)
                actions.append(
                    _vol_action(
                        lid,
                        name,
                        boost,
                        f"前景层 {fg_actual}% 低于目标 {fg_target}%",
                        track_num=tnum,
                        priority="high" if fg_actual < fg_target * 0.4 else "medium",
                    )
                )

    mid_actual = role_pct.get("mid", 0)
    mid_target = ideal_pct.get("mid", 30)
    if mid_actual < mid_target * 0.5:
        boost = min(1.22, max(1.1, (mid_target / max(mid_actual, 1)) ** 0.3))
        for lid in MID_LAYERS:
            if lid in layer_by_id and layer_by_id[lid].get("active", True) and layer_by_id[lid].get("vol", 0) > 0:
                name, tnum = layer_ref(lid)
                actions.append(
                    _vol_action(
                        lid,
                        name,
                        boost,
                        f"中景层 {mid_actual}% 低于目标 {mid_target}%",
                        track_num=tnum,
                        priority="medium",
                    )
                )

    # ── RS-PASS 弱项 ──
    s50 = dims.get("s50_sharpness", {}).get("score", 100)
    if s50 < 80:
        group_fx = mix.get("group_fx", [])
        has_eq = any("ReaEQ" in str(x) or "asmr_sleep" in str(x).lower() for x in group_fx)
        if not has_eq:
            actions.append(
                {
                    "layer_id": None,
                    "track_name": "Group",
                    "target": "group",
                    "action": "add_fx",
                    "params": {
                        "fx": "asmr_sleep_hf_eq.jsfx",
                        "js_name": "relaxASMR/asmr_sleep_hf_eq.jsfx",
                        "search_paths": ["scripts/fx", "Reaper/scripts/fx"],
                    },
                    "priority": "high",
                    "auto_apply": True,
                    "reason": f"尖锐度 S_50 得分 {s50:.0f}，Group 缺 HF EQ",
                    "text": "Group 总线：添加 asmr_sleep_hf_eq.jsfx 衰减 3–8 kHz",
                }
            )
        materials = mix.get("materials_detected", [])
        if "metal" in materials:
            for lid in FOREGROUND_LAYERS:
                layer = layer_by_id.get(lid)
                if not layer:
                    continue
                blob = " ".join(layer.get("paths", []))
                if any(_has_material_keyword(blob, k) for k in ("metal", "tin", "steel")):
                    name, tnum = layer_ref(lid)
                    actions.append(
                        _vol_action(
                            lid,
                            name,
                            0.78,
                            "金属类 impact 导致 S_50 偏高",
                            track_num=tnum,
                            priority="high",
                        )
                    )

    f50 = dims.get("f50_fluctuation", {}).get("score", 100)
    rain = layer_by_id.get("1_rain")
    if f50 < 72 and rain and rain.get("active", True) and not rain.get("vol_envelope") and rain.get("vol", 0) > 0:
        rain_name, rain_num = layer_ref("1_rain")
        actions.append(
            {
                "layer_id": "1_rain",
                "track": rain_num,
                "track_name": rain_name,
                "action": "add_vol_envelope",
                "params": {"depth": 0.08, "peak_at": "center", "shape": "single_wave"},
                "priority": "medium",
                "auto_apply": True,
                "reason": f"波动强度 F_50 得分 {f50:.0f}，主雨层缺 macro 起伏",
                "text": f"{_label_text(rain_num, '1_rain', rain_name)}：添加 single_wave 音量包络 depth=0.08",
            }
        )

    n5 = dims.get("n5_peak_loudness", {}).get("score", 100)
    crest = dims.get("crest_headroom", {}).get("score", 100)
    if n5 < 75 or crest < 55:
        cut = 0.82 if crest < 55 else 0.88
        for lid in SCATTER_LAYERS:
            layer = layer_by_id.get(lid)
            if layer and layer.get("active", True) and layer.get("mode") == "scatter" and layer.get("vol", 0) > 0:
                name, tnum = layer_ref(lid)
                actions.append(
                    _vol_action(
                        lid,
                        name,
                        cut,
                        "稀疏层尖峰 / 动态峰值偏高",
                        track_num=tnum,
                        priority="high" if n5 < 65 else "medium",
                    )
                )

    iacc = dims.get("iacc", {}).get("score", 100)
    if iacc < 72:
        rain_name, rain_num = layer_ref("1_rain")
        actions.append(
            _note(
                "1_rain",
                rain_name,
                "IACC 偏高：请为 L/R 使用相位解耦的不同素材（无法自动替换文件）",
                track_num=rain_num,
                priority="medium",
            )
        )

    if mode == "sleep" and primary == "white":
        actions.append(
            _note(
                None,
                None,
                "偏白噪谱：助眠向建议换粉红谱细雨素材或确认 Group HF EQ 已启用",
                priority="high",
                target="project",
            )
        )

    r5 = dims.get("r5_roughness", {}).get("score", 100)
    if r5 < 70:
        imp_name, imp_num = layer_ref("2_impact")
        actions.append(
            _note(
                "2_impact",
                imp_name,
                "粗糙度偏高：考虑换更低 Asper 的落叶/细雨 impact 素材",
                track_num=imp_num,
                priority="medium",
            )
        )

    tmax = dims.get("tmax_tonality", {}).get("score", 100)
    if tmax < 75:
        imp_name, imp_num = layer_ref("2_impact")
        actions.append(
            _note(
                "2_impact",
                imp_name,
                "纯音调 T_max 偏高：检查 ETFE/金属共振，必要时 Group 加窄带陷波",
                track_num=imp_num,
                priority="high",
            )
        )

    actions = _merge_vol_actions(actions)
    priority_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    actions.sort(key=lambda a: (priority_order.get(a.get("priority", "info"), 9), a.get("track_name") or ""))
    return actions
