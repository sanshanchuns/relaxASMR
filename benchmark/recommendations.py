"""结合 RS-PASS、噪声类型与 RPP 轨道信息生成修改建议。"""

from __future__ import annotations

from noise_type import TYPE_META


def _fmt_track(layer: dict) -> str:
    tid = layer.get("track")
    name = layer.get("name", layer.get("id", "?"))
    if tid:
        return f"轨 {tid} `{name}`"
    return f"`{name}`"


def build_recommendations(
    result: dict,
    project: dict | None,
    *,
    intent_mode: str | None = None,
) -> list[dict]:
    recs: list[dict] = []
    nt = result.get("noise_type", {})
    primary = nt.get("primary", "pink")
    type_fit = result.get("type_fit", {})
    dims = result.get("dimensions", {})
    m = result.get("measurements", {})
    mode = result.get("mode", "sleep")
    intent = intent_mode or mode

    # --- 噪声类型 vs 使用意图 ---
    rec_mode = TYPE_META[primary]["recommended_mode"]
    if intent == "sleep" and primary == "white":
        recs.append(
            {
                "priority": "high",
                "category": "noise_type",
                "text": (
                    "成品偏 **白噪谱**（平坦高频），不适合整夜助眠。"
                    "建议 Group 总线 ReaEQ：3 kHz 起 −6 dB/oct 低通，或换用粉红谱素材（细雨/树叶 impact）。"
                ),
            }
        )
    elif intent == "sleep" and primary == "brown" and m.get("n5_sone_est", 0) > 2:
        recs.append(
            {
                "priority": "medium",
                "category": "noise_type",
                "text": (
                    "偏 **棕噪/低频** 谱型，助眠可用但注意超低频雷鸣不要过响；"
                    "检查 `1_rain` / 背景层是否含 thunder 类素材，Master 限幅。"
                ),
            }
        )
    elif intent == "focus" and primary == "pink":
        recs.append(
            {
                "priority": "low",
                "category": "noise_type",
                "text": (
                    "当前偏 **粉红谱**，掩蔽力略弱于白噪；专注向可略抬 `2_impact` / 窗雨高频层，"
                    "或临时用 focus 模式 benchmark（N_5≤8 Sone）评估。"
                ),
            }
        )

    if type_fit.get("type_fit_score", 100) < 70:
        recs.append(
            {
                "priority": "medium",
                "category": "noise_type",
                "text": (
                    f"类型贴合度 {type_fit['type_fit_score']:.0f}/100："
                    f"斜率 {nt.get('slope')} 距 {TYPE_META[primary]['label_zh']} 理想值 "
                    f"{nt.get('ideal_slope')} 偏远。"
                    "检查主雨层素材是否与目标场景（细雨/暴雨/远雷）一致。"
                ),
            }
        )

    if intent != rec_mode and type_fit.get("type_fit_score", 0) >= 75:
        recs.append(
            {
                "priority": "info",
                "category": "noise_type",
                "text": (
                    f"音频主类型为 **{TYPE_META[primary]['label_zh']}**，"
                    f"理论最适合 {TYPE_META[primary]['use_zh']}（建议 mode={rec_mode}）。"
                    f"当前 benchmark 使用 mode={intent}。"
                ),
            }
        )

    # --- RS-PASS 弱项 ---
    weak = sorted(
        ((k, v["score"]) for k, v in dims.items()),
        key=lambda x: x[1],
    )[:3]

    for key, sc in weak:
        if sc >= 75:
            continue
        if key == "s50_sharpness":
            recs.append(
                {
                    "priority": "high",
                    "category": "rs_pass",
                    "text": (
                        f"尖锐度 S_50 得分 {sc:.0f}（测得 {m.get('s50_acum_est')} Acum est，"
                        f"目标 ≤{dims['s50_sharpness'].get('target_max', 1.1)}）。"
                        "Group **ReaEQ** 衰减 3–8 kHz；检查 metal/glass 类 impact 音量。"
                    ),
                }
            )
        elif key == "iacc":
            recs.append(
                {
                    "priority": "high",
                    "category": "rs_pass",
                    "text": (
                        f"IACC {m.get('iacc')} 偏高（目标 ≤0.3），包裹感不足。"
                        "为 `1_rain`/`3_environment` 使用 **相位解耦** 的 L/R 不同素材；"
                        "避免所有层同源 mono 复制到双声道。"
                    ),
                }
            )
        elif key == "r5_roughness":
            recs.append(
                {
                    "priority": "medium",
                    "category": "rs_pass",
                    "text": (
                        f"粗糙度 R_5 得分 {sc:.0f}。"
                        "前景层换更低 Asper 的落叶/细雨 impact；"
                        "ETFE/金属帐篷类素材降 vol 或换 cedar/玻璃阻尼类。"
                    ),
                }
            )
        elif key == "f50_fluctuation":
            recs.append(
                {
                    "priority": "medium",
                    "category": "rs_pass",
                    "text": (
                        f"波动强度 F_50 偏离自然风拂（0.05–0.15 Vacil）。"
                        "给 `1_rain` 加 **vol_envelope**（depth 0.05–0.12）；"
                        "或在中景层加入 `3_environment/wind` 慢调制。"
                    ),
                }
            )
        elif key == "tmax_tonality":
            recs.append(
                {
                    "priority": "high",
                    "category": "rs_pass",
                    "text": (
                        f"纯音色调度 T_max={m.get('tmax')} 超标。"
                        "Group 或 impact 轨加 **窄带陷波** 剔除金属/薄膜共振哨音（theory §五）。"
                    ),
                }
            )
        elif key == "n5_peak_loudness":
            recs.append(
                {
                    "priority": "high",
                    "category": "rs_pass",
                    "text": (
                        f"动态峰值 N_5 得分 {sc:.0f}（P95 {m.get('n5_p95_dbfs')} dBFS）。"
                        "降低 scatter 层 vol、检查 impact 尖峰；Group **ReaComp** 软限幅。"
                    ),
                }
            )

    # --- RPP / 配方结构 ---
    if not project:
        recs.append(
            {
                "priority": "info",
                "category": "project",
                "text": "未找到 .rpp / asmr_config，仅音频分析。使用 `--rpp path/to/scene.rpp` 获取轨级建议。",
            }
        )
        return recs

    mix = project.get("mix", {})
    role_pct = mix.get("role_energy_pct", {})
    ideal = mix.get("ideal_role_pct", {})
    layers = mix.get("layers", [])

    for role, target in ideal.items():
        actual = role_pct.get(role, 0)
        if actual < target * 0.55:
            missing_layers = [l for l in layers if l.get("role") == role and l.get("vol", 0) > 0]
            if role == "foreground" and not missing_layers:
                recs.append(
                    {
                        "priority": "high",
                        "category": "mix_structure",
                        "text": (
                            f"前景层能量 {actual}% 低于目标 {target}%（theory §五 约 60%）。"
                            "提高 `2_impact` 落叶/击打 vol，或增加 scatter 密度。"
                        ),
                    }
                )
            elif role == "mid" and actual < target * 0.5:
                recs.append(
                    {
                        "priority": "medium",
                        "category": "mix_structure",
                        "text": (
                            f"中景层 {actual}% vs 目标 {target}%。"
                            "增加 `3_environment` 风/林环境 loop，并加 0.1–1 Hz 音量调制。"
                        ),
                    }
                )
            elif role == "background" and actual < target * 0.4:
                recs.append(
                    {
                        "priority": "medium",
                        "category": "mix_structure",
                        "text": (
                            f"背景层 {actual}% vs 目标 {target}%。"
                            "略抬 `1_rain` 底床或加远距低频环境（远雷 <100 Hz，约 10% 能量）。"
                        ),
                    }
                )
        elif actual > target * 1.6 and role == "background":
            recs.append(
                {
                    "priority": "medium",
                    "category": "mix_structure",
                    "text": (
                        f"背景层占比 {actual}% 过高，可能发闷或偏棕噪。"
                        "降低 `1_rain` vol，把能量让给前景 impact。"
                    ),
                }
            )

    materials = mix.get("materials_detected", [])
    if "metal" in materials and dims.get("s50_sharpness", {}).get("score", 100) < 80:
        metal_layers = [
            l for l in layers
            if l.get("role") == "foreground"
            and any(k in " ".join(l.get("paths", [])).lower() for k in ("metal", "tin", "steel"))
        ]
        hint = _fmt_track(metal_layers[0]) if metal_layers else "`2_impact`"
        recs.append(
            {
                "priority": "high",
                "category": "material",
                "text": (
                    f"检测到金属类素材（{hint}）。"
                    "theory §一：金属板易有色调性噼啪；降 vol、加 LPF，或换 wood/glass 类 impact。"
                ),
            }
        )

    group_fx = mix.get("group_fx", [])
    if "ReaEQ (Cockos)" not in str(group_fx) and dims.get("s50_sharpness", {}).get("score", 100) < 85:
        recs.append(
            {
                "priority": "medium",
                "category": "project",
                "text": "Group 总线未见 ReaEQ。建议加 ReaEQ 做 3 kHz+ 缓降以控制尖锐度（theory §五）。",
            }
        )

    rain_layer = next((l for l in layers if l.get("id") == "1_rain"), None)
    if rain_layer and not rain_layer.get("vol_envelope") and dims.get("f50_fluctuation", {}).get("score", 100) < 70:
        recs.append(
            {
                "priority": "medium",
                "category": "project",
                "text": (
                    f"{_fmt_track(rain_layer)} 未配置 vol_envelope。"
                    "在 asmr_config 加 single_wave depth 0.08，避免机械 loop 感。"
                ),
            }
        )

    return recs
