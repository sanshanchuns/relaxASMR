#!/usr/bin/env python3
"""按 design/rule.md 对渲染成品 wav 打「包裹感 / 安全感」分。

用法：
  python3 Reaper/scripts/score_mix.py --wav path/to/mix.wav [--scene MVI_6918] [--json]
  python3 Reaper/scripts/score_mix.py --scene MVI_6918   # 自动找 <scene>.wav

设计依据 design/rule.md：
  包裹感 = 距离层次完整度 + 近/中/远比例 + 立体声宽度 + 低频托底
  安全感 = 连续声床 + 尖峰控制 + 高频(3-8k)克制 + 密度70/20/10 + 安全声源

成品测声学；配方(--scene)补「距离层数/近中远比例」等混音后拆不回的结构信息。
阈值为启发式，可按主观听感校准。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parent

# 层 id → 距离区域权重（near/mid/far），用于结构性包裹感评估
DISTANCE_MAP = {
    "1_base": {"far": 0.6, "mid": 0.4},     # 空气/底噪铺底
    "2_rain": {"near": 0.5, "mid": 0.5},    # 主雨，近-中弥漫
    "3_impact": {"near": 1.0},              # 击打，近场
    "4_water": {"mid": 1.0},                # 水面，中景
    "5_env": {"mid": 0.5, "far": 0.5},      # 环境包络
    "6_life": {"far": 1.0},                 # 远处生物
    "7_comfort": {"near": 1.0},             # 近场庇护
}
IDEAL_NMF = {"near": 0.40, "mid": 0.40, "far": 0.20}  # rule.md §四

# 安全声源白名单（rule.md §八 + §四 近处可控）→ 关键词
SAFE_KEYWORDS = [
    "雨打树叶", "雨打", "树叶", "小雨", "毛毛雨", "下雨",
    "湖水", "湖浪", "水拍", "拍岸",
    "木船", "船", "划",
    "微风", "风声", "空气", "底噪",
    "鸟鸣", "鸟叫", "远",
    "壁炉", "篝火", "柴火",
    "竹林", "森林", "雨伞", "伞", "屋檐", "帐篷", "溪",
]
# 易破坏安全感的关键词（尖锐/突兀）
UNSAFE_KEYWORDS = ["雷", "爆", "乌鸦", "嘎", "警", "城市", "车", "人声", "钟"]


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def load_stereo(wav: Path):
    """用 ffmpeg 解码为 48k 立体声 float，返回 (L, R, sr)。"""
    import numpy as np

    sr = 48000
    proc = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(wav),
            "-ac", "2", "-ar", str(sr), "-f", "f32le", "-",
        ],
        capture_output=True,
        check=True,
    )
    data = np.frombuffer(proc.stdout, dtype="<f4")
    if data.size % 2:
        data = data[:-1]
    stereo = data.reshape(-1, 2)
    return stereo[:, 0].astype(np.float64), stereo[:, 1].astype(np.float64), sr


def band_pct(mono, sr) -> dict:
    import numpy as np

    fft = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), 1 / sr)
    power = fft ** 2

    def be(lo, hi):
        return float(np.sum(power[(freqs >= lo) & (freqs < hi)]))

    bands = {
        "sub_low": be(20, 200),
        "low_mid": be(200, 500),
        "mid": be(500, 2000),
        "high_mid": be(2000, 6000),
        "high": be(6000, sr / 2),
    }
    harsh = be(3000, 8000)
    total = sum(bands.values()) or 1.0
    pct = {k: 100 * v / total for k, v in bands.items()}
    pct["_harsh_3k8k"] = 100 * harsh / total
    return pct


def windowed_rms_db(mono, sr, hop_s=0.4):
    import numpy as np

    hop = max(1, int(sr * hop_s))
    n = len(mono) // hop
    if n < 2:
        return np.array([-120.0])
    trimmed = mono[: n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(trimmed ** 2, axis=1))
    rms_db = 20 * np.log10(np.maximum(rms, 1e-9))
    return rms_db


def acoustic_features(L, R, sr) -> dict:
    import numpy as np

    mono = (L + R) / 2.0
    side = (L - R) / 2.0

    bp = band_pct(mono, sr)
    rms_db = windowed_rms_db(mono, sr)
    median = float(np.median(rms_db))

    # 连续声床：窗 RMS 的稳定度（std 越小越稳）+ 静音空隙惩罚
    std_db = float(np.std(rms_db))
    gap_frac = float(np.mean(rms_db < median - 20))

    # 尖峰/突兀：相邻窗能量突增次数/分钟
    d = np.diff(rms_db)
    onsets = int(np.sum(d > 6.0))
    minutes = max(len(mono) / sr / 60.0, 1e-6)
    onsets_per_min = onsets / minutes
    # 用 99.9 分位代替绝对最大值，避免单样本/边界 click 主导
    p999 = float(np.percentile(np.abs(mono), 99.9))
    crest = p999 / (np.sqrt(np.mean(mono ** 2)) + 1e-9)
    crest_db = 20 * np.log10(max(crest, 1e-9))

    # 密度 70/20/10：按相对中位数的偏离分类
    dev = np.abs(rms_db - median)
    p_steady = float(np.mean(dev <= 2))
    p_var = float(np.mean((dev > 2) & (dev <= 6)))
    p_sur = float(np.mean(dev > 6))

    # 立体声宽度：side/mid 能量比
    mid_rms = float(np.sqrt(np.mean(mono ** 2)))
    side_rms = float(np.sqrt(np.mean(side ** 2)))
    width = side_rms / (mid_rms + 1e-9)
    # L/R 相关（越低越宽）
    if np.std(L) > 0 and np.std(R) > 0:
        corr = float(np.corrcoef(L, R)[0, 1])
    else:
        corr = 1.0

    return {
        "band_pct": {k: round(v, 1) for k, v in bp.items()},
        "rms_std_db": round(std_db, 2),
        "silence_gap_frac": round(gap_frac, 3),
        "onsets_per_min": round(onsets_per_min, 2),
        "crest_db": round(crest_db, 1),
        "density": {
            "steady": round(p_steady, 2),
            "variation": round(p_var, 2),
            "surprise": round(p_sur, 2),
        },
        "stereo_width": round(width, 3),
        "lr_corr": round(corr, 3),
        "_low_found_pct": bp["sub_low"] + bp["low_mid"],
    }


# ---------- 配方结构（包裹感的距离层）----------

def load_scene_layers(scene: str):
    sys.path.insert(0, str(SCRIPTS_DIR))
    from asmr_config_parser import load_asmr_config

    cfg_path = (
        REPO_ROOT / "Reaper" / "Projects" / "Rain"
        / "subprojects" / scene / "scripts" / "asmr_config.lua"
    )
    if not cfg_path.exists():
        return None
    cfg = load_asmr_config(cfg_path)
    layers = []
    for layer in cfg.get("loop_layers", []):
        layers.append({**layer, "mode": "loop"})
    for layer in cfg.get("scatter_layers", []):
        layers.append({**layer, "mode": "scatter"})
    return layers


def structural_scores(layers) -> dict:
    """返回 near/mid/far 比例、层次完整度、近中远平衡、安全声源比例。"""
    zones = {"near": 0.0, "mid": 0.0, "far": 0.0}
    safe_w = 0.0
    unsafe_w = 0.0
    total_w = 0.0
    n_active = 0
    for layer in layers:
        lid = layer.get("id", "")
        vol = float(layer.get("vol", 0) or 0)
        if vol <= 0:
            continue
        n_active += 1
        # 稀疏层对「连续声场」贡献打折
        eff = vol * (0.4 if layer.get("mode") == "scatter" else 1.0)
        for zone, w in DISTANCE_MAP.get(lid, {"mid": 1.0}).items():
            zones[zone] += eff * w
        name = (layer.get("name", "") + " " + " ".join(layer.get("paths", [])))
        if any(k in name for k in UNSAFE_KEYWORDS):
            unsafe_w += eff
        elif any(k in name for k in SAFE_KEYWORDS):
            safe_w += eff
        total_w += eff

    zsum = sum(zones.values()) or 1.0
    nmf = {k: v / zsum for k, v in zones.items()}
    balance = 1 - 0.5 * sum(abs(nmf[k] - IDEAL_NMF[k]) for k in IDEAL_NMF)
    completeness = sum(1 for k in zones if zones[k] / zsum > 0.08) / 3.0
    safe_ratio = (safe_w - unsafe_w) / (total_w + 1e-9)
    macro_drift = 0.0
    for layer in layers:
        if layer.get("id") == "2_rain":
            ve = layer.get("vol_envelope") or {}
            depth = float(ve.get("depth", 0) or 0)
            if ve and depth > 0:
                macro_drift = 1.0 if 0.05 <= depth <= 0.15 else 0.5
            break
    return {
        "near_mid_far": {k: round(v, 2) for k, v in nmf.items()},
        "balance": round(clip(balance), 3),
        "completeness": round(completeness, 3),
        "safe_ratio": round(clip(safe_ratio), 3),
        "macro_drift": round(macro_drift, 3),
        "n_active": n_active,
    }


# ---------- 打分 ----------

def score_immersion(ac, st) -> dict:
    # 立体声宽度 0(单声)→0 ; 0.6+→满
    width_s = clip(ac["stereo_width"] / 0.6)
    # 低频托底：峰值在 ~25%，过低单薄、过高浑浊
    low = ac["_low_found_pct"]
    lowfound_s = clip(1 - abs(low - 25) / 25)

    sub = {
        "stereo_width": round(width_s, 2),
        "low_freq_foundation": round(lowfound_s, 2),
    }
    if st:
        sub["layer_completeness"] = round(st["completeness"], 2)
        sub["near_mid_far_balance"] = round(st["balance"], 2)
        total = (
            2.5 * st["completeness"]
            + 2.5 * st["balance"]
            + 3.0 * width_s
            + 2.0 * lowfound_s
        )
    else:
        # 无配方：仅声学，权重重分配到 width/low（标注为估计）
        total = 6.0 * width_s + 4.0 * lowfound_s
        sub["_note"] = "无 --scene，结构层缺失，仅声学估计"
    return {"score": round(total, 1), "sub": sub}


def score_safety(ac, st) -> dict:
    # 连续声床：std 越小越稳，>8dB 视为跳；静音空隙惩罚
    cont = clip((8 - ac["rms_std_db"]) / 6) * (1 - clip(ac["silence_gap_frac"]))
    # 尖峰控制：可接受 ~2/min，>20/min 归零；99.9 分位 crest 过高再软惩罚
    trans = clip(1 - max(0.0, ac["onsets_per_min"] - 2) / 18)
    if ac["crest_db"] > 14:
        trans *= clip(1 - (ac["crest_db"] - 14) / 16)
    # 高频 3-8k 克制（rule.md §五）：10%满，35%归零
    harsh = ac["band_pct"]["_harsh_3k8k"]
    hf = clip((35 - harsh) / 25)
    # 密度 70/20/10 吻合度
    den = ac["density"]
    ideal = {"steady": 0.7, "variation": 0.2, "surprise": 0.1}
    dens = clip(1 - 0.5 * sum(abs(den[k] - ideal[k]) for k in ideal))
    macro = st.get("macro_drift", 0.0) if st else 0.0
    if macro > 0:
        dens = clip(0.75 * dens + 0.25 * macro)

    sub = {
        "continuous_bed": round(cont, 2),
        "transient_control": round(trans, 2),
        "highfreq_restraint": round(hf, 2),
        "density_match": round(dens, 2),
    }
    if macro > 0:
        sub["macro_drift"] = round(macro, 2)
    if st:
        sub["safe_source"] = round(st["safe_ratio"], 2)
        total = 3.0 * cont + 2.5 * trans + 2.0 * hf + 1.5 * dens + 1.0 * st["safe_ratio"]
    else:
        total = 3.3 * cont + 2.8 * trans + 2.2 * hf + 1.7 * dens
        sub["_note"] = "无 --scene，安全声源项跳过"
    return {"score": round(total, 1), "sub": sub}


def render_report(wav, ac, st, imm, saf) -> str:
    lines = [
        f"# 混音打分 · {wav.name}",
        "",
        "> 依据 design/rule.md｜成品声学 + 配方结构｜分制 0–10",
        "",
        "## 总分",
        "",
        "| 指标 | 得分 |",
        "|------|------|",
        f"| 包裹感 Immersion | **{imm['score']} / 10** |",
        f"| 安全感 Safety | **{saf['score']} / 10** |",
        "",
        "## 包裹感拆解",
        "",
        "| 子项 | 0–1 |",
        "|------|-----|",
    ]
    for k, v in imm["sub"].items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## 安全感拆解", "", "| 子项 | 0–1 |", "|------|-----|"]
    for k, v in saf["sub"].items():
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "## 声学测量",
        "",
        f"- 频段占比：{ac['band_pct']}",
        f"- 3–8kHz 刺激带：{ac['band_pct']['_harsh_3k8k']}%",
        f"- 窗 RMS 波动 std：{ac['rms_std_db']} dB（越小越稳）",
        f"- 突增事件：{ac['onsets_per_min']} 次/分 · crest {ac['crest_db']} dB",
        f"- 密度 稳/变/惊：{ac['density']}",
        f"- 立体声宽度 side/mid：{ac['stereo_width']} · L/R 相关 {ac['lr_corr']}",
    ]
    if st:
        lines += [
            "",
            "## 配方结构",
            "",
            f"- 近/中/远：{st['near_mid_far']}（理想 40/40/20）",
            f"- 层次完整度：{st['completeness']} · 比例平衡：{st['balance']}",
            f"- 安全声源比例：{st['safe_ratio']} · 活跃层 {st['n_active']}",
        ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="按 rule.md 给混音打 包裹感/安全感 分")
    ap.add_argument("--wav", type=Path, help="渲染成品 wav")
    ap.add_argument("--scene", type=str, help="Rain 子工程 id（读配方补结构层）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    wav = args.wav
    if not wav and args.scene:
        cand = (
            REPO_ROOT / "Reaper" / "Projects" / "Rain"
            / "subprojects" / args.scene / f"{args.scene}.wav"
        )
        if cand.exists():
            wav = cand
    if not wav or not wav.is_file():
        ap.error("需要 --wav 或可定位的 --scene <id>.wav")

    L, R, sr = load_stereo(wav)
    ac = acoustic_features(L, R, sr)

    st = None
    if args.scene:
        layers = load_scene_layers(args.scene)
        if layers:
            st = structural_scores(layers)

    imm = score_immersion(ac, st)
    saf = score_safety(ac, st)

    if args.json:
        print(json.dumps(
            {"wav": str(wav), "immersion": imm, "safety": saf,
             "acoustic": ac, "structural": st},
            ensure_ascii=False, indent=2,
        ))
    else:
        print(render_report(wav, ac, st, imm, saf))


if __name__ == "__main__":
    main()
