#!/usr/bin/env python3
"""RS-PASS + 色噪声类型 benchmark（benchmark/theory.md §一、§四）。

对渲染成品 mp4/wav 分析前 N 秒（默认 300s；不足则分析全长）：
  - 判断主噪声类型：pink / white / brown
  - 类型内 RS-PASS 七项指标 + 类型贴合度
  - 可选读取 .rpp / asmr_config 给出 Reaper 修改建议

用法：
  python3 benchmark/score.py path/to/render.mp4
  python3 benchmark/score.py path/to/mix.wav --rpp Reaper/Projects/Rain/subprojects/MVI_6918/MVI_6918.rpp
  python3 benchmark/score.py path/to/render.mp4 --mode sleep --output-dir material/out/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rpp_context import load_project_context
from rs_pass import (
    DEFAULT_DURATION,
    RS_PASS_WEIGHTS,
    score_rs_pass,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

DIM_LABELS = {
    "n5_peak_loudness": "动态峰值响度 N_5",
    "s50_sharpness": "尖锐度 S_50",
    "r5_roughness": "粗糙度 R_5",
    "iacc": "双耳互相关 IACC",
    "f50_fluctuation": "波动强度 F_50",
    "si_irregularity": "光谱不规则度 SI",
    "tmax_tonality": "纯音色调度 T_max",
    "crest_headroom": "峰均差 Crest（稀疏尖峰）",
}

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def render_markdown(result: dict) -> str:
    d = result["dimensions"]
    nt = result.get("noise_type", {})
    tf = result.get("type_fit", {})
    proj = result.get("project") or {}
    req = result.get("duration_requested_s", result["duration_s"])
    actual = result["duration_s"]
    if result.get("duration_file_s") is not None and actual < req - 0.5:
        dur_desc = f"全长 **{actual:.0f} s**"
    else:
        dur_desc = f"前 **{actual:.0f} s**"
    lines = [
        f"# RS-PASS Benchmark · {Path(result['file']).name}",
        "",
        "> 依据 `benchmark/theory.md` · "
        f"模式 **{result['mode']}** · 分析 {dur_desc}",
    ]
    scene_id = (proj.get("mix") or {}).get("scene_id")
    if scene_id:
        lines.append(f"> 场景：**{scene_id}** · 配方 `asmr_config.lua`")
    lines += [
        "",
        f"**综合分 {result['total_score']:.1f} / 100** · **{result['grade']}** "
        f"（RS-PASS {result.get('rs_pass_score', result['total_score']):.1f} + "
        f"类型贴合 {tf.get('type_fit_score', 0):.1f}）",
        "",
        "## 色噪声类型（theory §一）",
        "",
        f"- **主类型**：{nt.get('label_zh', '?')} (`{nt.get('primary', '?')}`)",
        f"- **PSD 斜率**：{nt.get('slope')}（理想 {nt.get('ideal_slope')}）· 置信度 {nt.get('confidence')}",
        f"- **场景**：{nt.get('use_zh', '')}",
        f"- **类型贴合度**：{tf.get('type_fit_score', 0):.1f} / 100",
    ]
    if nt.get("secondary"):
        lines.append(f"- **次类型提示**：`{nt['secondary']}`")
    lines += [
        "",
        "## RS-PASS 指标",
        "",
        "| 指标 | 得分 / 100 | 权重 |",
        "|------|------------|------|",
    ]
    for key, w in RS_PASS_WEIGHTS.items():
        lines.append(
            f"| {DIM_LABELS[key]} | **{d[key]['score']:.1f}** | {int(w * 100)}% |"
        )

    mix = proj.get("mix") or {}
    if mix.get("role_energy_pct"):
        lines += [
            "",
            "## 混音三层能量（theory §五 · 来自 RPP/配方）",
            "",
            "| 层 | 实际 | 目标 |",
            "|----|------|------|",
        ]
        ideal = mix.get("ideal_role_pct", {})
        for role in ("foreground", "mid", "background"):
            lines.append(
                f"| {role} | {mix['role_energy_pct'].get(role, 0)}% | "
                f"{ideal.get(role, '?')}% |"
            )
        if proj.get("rpp_path"):
            lines.append(f"\n工程：`{proj['rpp_path']}`")

    recs = result.get("recommendations") or []
    if recs:
        lines += ["", "## 修改建议", ""]
        for rec in sorted(recs, key=lambda r: PRIORITY_ORDER.get(r["priority"], 9)):
            tag = rec["priority"].upper()
            lines.append(f"- **[{tag}]** {rec['text']}")

    track_actions = result.get("track_actions") or []
    if track_actions:
        lines += ["", "## 轨级修改建议", ""]
        lines += [
            "| 轨 | 优先级 | 自动 | 建议 |",
            "|----|--------|------|------|",
        ]
        for act in track_actions:
            auto = "是" if act.get("auto_apply") and act.get("action") != "note" else "否"
            tid = act.get("track")
            lid = act.get("layer_id")
            name = act.get("track_name") or lid or act.get("target") or "—"
            if tid and lid:
                track = f"{tid} · `{lid}` · {name}"
            else:
                track = name
            lines.append(
                f"| {track} | {act.get('priority', '?')} | {auto} | "
                f"{act.get('text', act.get('reason', ''))} |"
            )

    m = result.get("measurements") or {}
    if m:
        lines += [
            "",
            "## 原始测量（代理量）",
            "",
            f"- N_5 响度估计: {m.get('n5_sone_est', '?')} Sone (P95 {m.get('n5_p95_dbfs', '?')} dBFS)",
            f"- S_50: {m.get('s50_acum_est', '?')} Acum(est)",
            f"- R_5: {m.get('r5_asper_est', '?')} Asper(est)",
            f"- IACC: {m.get('iacc', '?')}",
            f"- F_50: {m.get('f50_vacil_est', '?')} Vacil(est)",
            f"- SI: {m.get('si', '?')}",
            f"- T_max: {m.get('tmax', '?')}",
            f"- RMS / Peak / Crest: {m.get('rms_dbfs', '?')} / {m.get('peak_dbfs', '?')} / "
            f"{round(m.get('peak_dbfs', 0) - m.get('rms_dbfs', 0), 2)} dB",
        ]

    lines += [
        "## 等级（甜区校准 · 代理量）",
        "",
        "> 旧版「不超标即满分」已改为 **ideal 甜区** 打分；88+ 应少见。",
        "",
        "| 总分 | 等级 | 含义 |",
        "|------|------|------|",
        "| ≥88 | 极品 | 各维接近甜区中心 |",
        "| 81–87 | 优秀 | 明显好于平均 |",
        "| 62–80 | 普通 | 合格日常雨片 |",
        "| <62 | 劣质 | 需返工 |",
    ]
    return "\n".join(lines)


def write_results(
    result: dict,
    out_dir: Path,
    report_stem: str = "benchmark",
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{report_stem}.md"
    json_path = out_dir / f"{report_stem}.json"
    md_path.write_text(render_markdown(result), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def _lua_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def write_actions_lua(actions: list, path: Path) -> None:
    """生成 Reaper loadfile 可读的 Lua 表。"""
    lines = ["return {"]
    for act in actions:
        lines.append("  {")
        for key in (
            "layer_id", "track", "track_name", "target", "action", "priority",
            "auto_apply", "reason", "text",
        ):
            val = act.get(key)
            if val is None:
                lines.append(f"    {key} = nil,")
            elif isinstance(val, bool):
                lines.append(f"    {key} = {'true' if val else 'false'},")
            elif isinstance(val, (int, float)):
                lines.append(f"    {key} = {val},")
            else:
                lines.append(f"    {key} = {_lua_str(str(val))},")
        params = act.get("params") or {}
        lines.append("    params = {")
        for pk, pv in params.items():
            if isinstance(pv, bool):
                lines.append(f"      {pk} = {'true' if pv else 'false'},")
            elif isinstance(pv, (int, float)):
                lines.append(f"      {pk} = {pv},")
            elif isinstance(pv, list):
                items = ", ".join(_lua_str(str(x)) for x in pv)
                lines.append(f"      {pk} = {{{items}}},")
            else:
                lines.append(f"      {pk} = {_lua_str(str(pv))},")
        lines.append("    },")
        lines.append("  },")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(result: dict, path: Path, *, report_stem: str = "benchmark") -> None:
    """键值行摘要，供 Reaper Lua 读取。"""
    nt = result.get("noise_type", {})
    tf = result.get("type_fit", {})
    dims = result.get("dimensions", {})
    weak = sorted(
        ((k, dims[k]["score"]) for k in dims),
        key=lambda x: x[1],
    )[:3]
    weak_txt = ", ".join(f"{k}={v:.0f}" for k, v in weak)
    out_dir = path.parent
    actions_lua = out_dir / f"{report_stem}_actions.lua"
    actions = result.get("track_actions") or []
    if actions:
        write_actions_lua(actions, actions_lua)
    auto_n = sum(1 for a in actions if a.get("auto_apply") and a.get("action") != "note")
    lines = [
        f"total_score={result.get('total_score', 0)}",
        f"rs_pass_score={result.get('rs_pass_score', 0)}",
        f"type_fit_score={tf.get('type_fit_score', 0)}",
        f"grade={result.get('grade', '')}",
        f"mode={result.get('mode', '')}",
        f"noise_type={nt.get('label_zh', '')}",
        f"noise_primary={nt.get('primary', '')}",
        f"duration_s={result.get('duration_s', 0)}",
        f"report_md={out_dir / (report_stem + '.md')}",
        f"report_json={out_dir / (report_stem + '.json')}",
        f"actions_lua={actions_lua if actions else ''}",
        f"track_actions_count={len(actions)}",
        f"track_actions_auto={auto_n}",
        f"weak_dims={weak_txt}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_benchmark(
    path: Path,
    duration: float = DEFAULT_DURATION,
    out_dir: Path | None = None,
    report_stem: str = "benchmark",
    mode: str | None = None,
    rpp_path: Path | None = None,
    *,
    auto_mode: bool = True,
) -> dict:
    project = load_project_context(rpp_path, path)
    result = score_rs_pass(
        path.resolve(),
        duration=duration,
        mode=mode,
        auto_mode=auto_mode,
        project=project,
    )
    if out_dir is not None:
        write_results(result, out_dir, report_stem=report_stem)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="RS-PASS + 色噪声类型 benchmark")
    ap.add_argument("input", type=Path, help="mp4 / wav / ffmpeg 可读音频")
    ap.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION,
        help=f"分析时长（秒），默认 {int(DEFAULT_DURATION)}",
    )
    ap.add_argument(
        "--mode",
        choices=("sleep", "focus"),
        default=None,
        help="评估意图；省略则按检测到的噪声类型自动选择",
    )
    ap.add_argument(
        "--no-auto-mode",
        action="store_true",
        help="不根据噪声类型自动选择 sleep/focus",
    )
    ap.add_argument(
        "--rpp",
        type=Path,
        default=None,
        help="Reaper 工程 .rpp（省略则尝试从媒体路径推断）",
    )
    ap.add_argument("--json", action="store_true", help="JSON 输出到 stdout")
    ap.add_argument("--markdown", action="store_true", help="Markdown 输出到 stdout")
    ap.add_argument("--output-dir", type=Path, help="写入 benchmark.md / benchmark.json")
    ap.add_argument("--report-stem", default="benchmark", help="报告文件名前缀")
    ap.add_argument(
        "--summary-file",
        type=Path,
        default=None,
        help="写入 key=value 摘要（供 Reaper Lua 读取）",
    )
    args = ap.parse_args()

    path = args.input.resolve()
    if not path.is_file():
        ap.error(f"文件不存在: {path}")

    result = run_benchmark(
        path,
        duration=args.duration,
        out_dir=args.output_dir,
        report_stem=args.report_stem,
        mode=args.mode,
        rpp_path=args.rpp,
        auto_mode=not args.no_auto_mode,
    )

    if args.summary_file is not None:
        write_summary(result, args.summary_file, report_stem=args.report_stem)

    if args.output_dir:
        json_path = args.output_dir / f"{args.report_stem}.json"
        nt = result.get("noise_type", {})
        print(
            f"==> RS-PASS: {result['total_score']:.1f} / 100 "
            f"({result['grade']}, {nt.get('label_zh', '?')}, "
            f"前 {result['duration_s']:.0f}s) → {json_path}"
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.markdown or not args.output_dir:
        print(render_markdown(result))


if __name__ == "__main__":
    main()
