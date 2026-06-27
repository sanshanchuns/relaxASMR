#!/usr/bin/env python3
"""从 asmr_config.lua 生成 Rain 子工程 .rpp"""

from __future__ import annotations

import argparse
import re
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from asmr_config_parser import load_asmr_config
from media_paths import (
    describe_media_mode,
    media_path_for_rpp,
    resolve_media_mode,
    wsl_unc_path,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parent
LAYER_TEMPLATE_PATH = REPO_ROOT / "Reaper" / "Projects" / "Rain" / "scripts" / "layer_template.lua"
RAIN_FX_SRC = REPO_ROOT / "Reaper" / "Projects" / "Rain" / "scripts" / "fx" / "asmr_sleep_hf_eq.jsfx"
DUMP_LUA = SCRIPTS_DIR / "dump_asmr_config.lua"

# Group 总线 JS EQ 默认参数（slider1..9）
GROUP_JS_EQ_PARAMS = [120, -3, 3500, 1.2, -5, 6000, 0.8, -4, 8000]
GROUP_JS_EQ_NAME = "relaxASMR/asmr_sleep_hf_eq.jsfx"

REACOMP_VST = [
    '      <VST "VST: ReaComp (Cockos)" reacomp.dll 0 "" 1919247213<5653547265636D726561636F6D700000> ""',
    "        bWNlcu9e7f4EAAAAAQAAAAAAAAACAAAAAAAAAAQAAAAAAAAACAAAAAAAAAACAAAAAQAAAAAAAAACAAAAAAAAAFwAAAAAAAAAAAAQAA==",
    "        776t3g3wrd4AAIA/ED74PKabxDsK16M8AAAAAAAAAAAAAIA/AAAAAAAAAAAAAAAAnNEHMwAAgD8AAAAAzcxMPQAAAAAAAAAAAAAAAAAAgD4AAAAAAAAAAAAAAAA=",
    "        AAAQAAAA",
    "      >",
]

REAEQ_VST = [
    '      <VST "VST: ReaEQ (Cockos)" reaeq.dll 0 "" 1919247729<56535472656571726561657100000000> ""',
    "        cWVlcu5e7f4CAAAAAQAAAAAAAAACAAAAAAAAAAIAAAABAAAAAAAAAAIAAAAAAAAAzQAAAAEAAAAAABAA",
    "        IQAAAAUAAAAAAAAAAQAAAAAAAAAAAFlAAAAAAAAA8D+amZmZmZnpPwEIAAAAAQAAAAAAAAAAwHJAAAAAAAAA8D8AAAAAAAAAQAEIAAAAAQAAAAAAAAAAQI9AAAAAAAAA",
    "        8D8AAAAAAAAAQAEBAAAAAQAAAJ/vruhzybNAMIH/8g6n2z+amZmZmZnpPwEEAAAAAQAAAAAAAAAAAFlAAAAAAAAA8D8AAAAAAAAAQAEBAAAAAQAAAAAAAAAAAPA/AAAA",
    "        AP0BAABcAQAAAgABAA==",
    "        AAAQAAAA",
    "      >",
]

REAVERBATe_VST = [
    '      <VST "VST: ReaVerbate (Cockos)" reaverbate.dll 0 "" 1920361016<56535472766238726561766572626174> ""',
    "        OGJ2cu9e7f4CAAAAAQAAAAAAAAACAAAAAAAAAAIAAAABAAAAAAAAAAIAAAAAAAAAKAAAAAAAAAAAABAA",
    "        776t3g3wrd5DAgA/AACAP9oEPD817P8+AACAPwAAAAAAAIA/AAAAAA==",
    "        AAAQAAAA",
    "      >",
]

# 轨级 FX：layer id → preset lines（不含 FXCHAIN 外壳）
TRACK_FX_PRESETS: dict[str, list[str]] = {
    "5_wildlife": REAVERBATe_VST,
}

# 视频轨混音时静音（-inf dB），仅最终渲染用
VIDEO_TRACK_VOL = 0.0


def load_config(config_path: Path) -> dict:
    try:
        result = subprocess.run(
            ["lua", str(DUMP_LUA), str(config_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
    except FileNotFoundError:
        pass
    return load_asmr_config(config_path)


def media_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return float(result.stdout.strip())
    return 60.0


def guid() -> str:
    return str(uuid.uuid4()).upper()


def rpp_quote_path(path_str: str) -> str:
    return path_str.replace('"', '\\"')



def source_type_for(asset: Path) -> tuple[str, str]:
    """返回 (SOURCE 类型, FILE 行尾后缀)。对齐 Demo.rpp：mp3 用 MP3 + \" 1\""""
    ext = asset.suffix.lower()
    if ext == ".mp3":
        return "MP3", " 1"
    if ext in (".wav", ".flac", ".aiff", ".aif"):
        return "WAVE", ""
    if ext in (".mp4", ".mov", ".mkv", ".webm"):
        return "VIDEO", ""
    return "WAVE", ""


def stage_media(
    asset: Path, rpp_dir: Path, media_mode: str, repo_root: Path | None = None
) -> tuple[str, str, str]:
    """返回 (RPP FILE 路径, SOURCE 类型, FILE 行尾后缀)。不复制文件，直接引用 assets。"""
    asset = asset.resolve()
    source_type, file_suffix = source_type_for(asset)
    mode = resolve_media_mode(media_mode, repo_root)

    if mode in ("wsl_unc", "assets"):
        return wsl_unc_path(asset), source_type, file_suffix

    return media_path_for_rpp(asset, rpp_dir, mode, repo_root), source_type, file_suffix


def make_track(
    name: str,
    vol: float = 1.0,
    isbus: tuple[int, int] = (0, 0),
    has_fx: bool = False,
    mute: bool = False,
    fx_preset: list[str] | None = None,
) -> str:
    track_id = guid()
    mutesolo = "1 0 0" if mute else "0 0 0"
    fx_count = 1 if (has_fx or fx_preset) else 0
    lines = [
        f"  <TRACK {{{track_id}}}",
        f"    NAME {name}",
        "    PEAKCOL 16576",
        "    BEAT -1",
        "    AUTOMODE 0",
        "    PANLAWFLAGS 3",
        f"    VOLPAN {vol} 0 -1 -1 1",
        f"    MUTESOLO {mutesolo}",
        "    IPHASE 0",
        "    PLAYOFFS 0 1",
        f"    ISBUS {isbus[0]} {isbus[1]}",
        "    BUSCOMP 0 0 0 0 0",
        "    SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0 0",
        "    FIXEDLANES 9 0 0 0 0",
        "    LANEREC -1 -1 -1 0",
        "    SEL 0",
        "    REC 0 0 1 0 0 0 0 0",
        "    VU 64",
        "    TRACKHEIGHT 0 0 0 0 0 0 0",
        "    INQ 0 0 0 0.5 100 0 0 100",
        "    NCHAN 2",
        f"    FX {fx_count}",
        f"    TRACKID {{{track_id}}}",
        "    PERF 0",
        "    MIDIOUT -1",
        "    MAINSEND 1 0",
    ]
    if fx_preset:
        lines.append("    <FXCHAIN")
        lines.append("      SHOW 0")
        lines.append("      LASTSEL 0")
        lines.append("      DOCKED 0")
        lines.append("      BYPASS 0 0 0")
        lines.extend(fx_preset)
        lines.append(f"      FLOATPOS 0 0 0 0")
        lines.append(f"      FXID {{{guid()}}}")
        lines.append("      WAK 0 0")
        lines.append("    >")
    return "\n".join(lines)


def js_eq_slider_line(params: list[float]) -> str:
    parts = [str(p) for p in params]
    while len(parts) < 64:
        parts.append("-")
    return " ".join(parts)


def make_group_fxchain_reaeq() -> list[str]:
    lines = [
        "    <FXCHAIN",
        "      SHOW 0",
        "      LASTSEL 0",
        "      DOCKED 0",
        "      BYPASS 0 0 0",
    ]
    lines.extend(REAEQ_VST)
    lines.append(f"      FLOATPOS 0 0 0 0")
    lines.append(f"      FXID {{{guid()}}}")
    lines.append("      WAK 0 0")
    lines.append("      BYPASS 0 0 0")
    lines.extend(REACOMP_VST)
    lines.extend(
        [
            "      FLOATPOS 0 0 0 0",
            f"      FXID {{{guid()}}}",
            "      WAK 0 0",
            "    >",
        ]
    )
    return lines


def make_group_fxchain(js_ref: str, params: list[float]) -> list[str]:
    slider_line = js_eq_slider_line(params)
    if any(c in js_ref for c in ("\\", "/", ":")):
        js_tag = f'"{rpp_quote_path(js_ref)}"'
    else:
        js_tag = js_ref
    lines = [
        "    <FXCHAIN",
        "      SHOW 0",
        "      LASTSEL 0",
        "      DOCKED 0",
        "      BYPASS 0 0 0",
        f"      <JS {js_tag} \"\"",
        f"        {slider_line}",
        "      >",
        f"      FLOATPOS 0 0 0 0",
        f"      FXID {{{guid()}}}",
        "      WAK 0 0",
        "      BYPASS 0 0 0",
    ]
    lines.extend(REACOMP_VST)
    lines.extend(
        [
            "      FLOATPOS 0 0 0 0",
            f"      FXID {{{guid()}}}",
            "      WAK 0 0",
            "    >",
        ]
    )
    return lines


def make_group_track(js_ref: str, params: list[float]) -> str:
    track_id = guid()
    lines = [
        f"  <TRACK {{{track_id}}}",
        "    NAME Group",
        "    PEAKCOL 16576",
        "    BEAT -1",
        "    AUTOMODE 0",
        "    PANLAWFLAGS 3",
        "    VOLPAN 1 0 -1 -1 1",
        "    MUTESOLO 0 0 0",
        "    IPHASE 0",
        "    PLAYOFFS 0 1",
        "    ISBUS 1 1",
        "    BUSCOMP 0 0 0 0 0",
        "    SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0 0",
        "    FIXEDLANES 9 0 0 0 0",
        "    LANEREC -1 -1 -1 0",
        "    SEL 0",
        "    REC 0 0 1 0 0 0 0 0",
        "    VU 64",
        "    TRACKHEIGHT 0 0 0 0 0 0 0",
        "    INQ 0 0 0 0.5 100 0 0 100",
        "    NCHAN 2",
        "    FX 1",
        f"    TRACKID {{{track_id}}}",
        "    PERF 0",
        "    MIDIOUT -1",
        "    MAINSEND 1 0",
    ]
    lines.extend(make_group_fxchain_reaeq())
    lines.append("  >")
    return "\n".join(lines)


def stage_rain_fx_assets(out_dir: Path) -> None:
    """复制 JS EQ 到子工程 scripts/fx/（模板可选）。"""
    if not RAIN_FX_SRC.is_file():
        return
    dest_dir = out_dir / "scripts" / "fx"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RAIN_FX_SRC, dest_dir / "asmr_sleep_hf_eq.jsfx")


def group_js_ref(out_dir: Path, repo_root: Path, media_mode: str) -> str:
    """RPP 内 JS 引用：优先 Effects 名，备用工程内路径。"""
    staged = out_dir / "scripts" / "fx" / "asmr_sleep_hf_eq.jsfx"
    if staged.is_file():
        mode = resolve_media_mode(media_mode, repo_root)
        if mode in ("wsl_unc", "assets"):
            return wsl_unc_path(staged)
        return media_path_for_rpp(staged, out_dir, mode, repo_root)
    return GROUP_JS_EQ_NAME


def make_item(
    name: str,
    position: float,
    length: float,
    loop: bool,
    file_path_str: str,
    source_type: str,
    vol: float = 1.0,
    iid: int = 1,
    file_suffix: str = "",
) -> str:
    iguid = guid()
    item_guid = guid()
    loop_line = "1" if loop else "0"
    return "\n".join(
        [
            "    <ITEM",
            f"      POSITION {position}",
            "      SNAPOFFS 0",
            f"      LENGTH {length}",
            f"      LOOP {loop_line}",
            "      ALLTAKES 0",
            "      FADEIN 1 0 0 1 0 0 0",
            "      FADEOUT 1 0 0 1 0 0 0",
            "      MUTE 0 0",
            "      SEL 0",
            f"      IGUID {{{iguid}}}",
            f"      IID {iid}",
            f"      NAME {name}",
            f"      VOLPAN {vol} 0 1 -1",
            "      SOFFS 0",
            "      PLAYRATE 1 1 0 -1 0 0.0025",
            "      CHANMODE 0",
            f"      GUID {{{item_guid}}}",
            f"      <SOURCE {source_type}",
            f'        FILE "{rpp_quote_path(file_path_str)}"{file_suffix}',
            "      >",
            "    >",
        ]
    )


def build_rpp(cfg: dict, repo_root: Path, rpp_dir: Path, media_mode: str = "auto") -> str:
    hours = float(cfg.get("duration_hours", 3))
    total_sec = hours * 3600
    maxprojlen = int(total_sec)

    header = [
        '<REAPER_PROJECT 0.1 "7.73/win64" 0 0',
        "  <NOTES 0 2",
        f"    {cfg.get('project_name', 'Rain')} · {hours}h · sleep series",
        "  >",
        "  RIPPLE 0 0",
        "  GROUPOVERRIDE 0 0 0 0",
        "  AUTOXFADE 128",
        "  ENVATTACH 3",
        "  POOLEDENVATTACH 0",
        "  TCPUIFLAGS 0",
        "  MIXERUIFLAGS 11 48",
        "  ENVFADESZ10 40",
        "  PEAKGAIN 1",
        "  FEEDBACK 0",
        "  PANLAW 1",
        "  PROJOFFS 0 0 0",
        f"  MAXPROJLEN 1 {maxprojlen}",
        "  GRID 3199 8 1 8 1 0 0 0",
        "  TIMEMODE 5 9 -1 60 0 0 -1 0",
        "  VIDEO_CONFIG 0 0 65792",
        "  PANMODE 3",
        "  PANLAWFLAGS 3",
        "  CURSOR 0",
        "  ZOOM 100 0 0",
        "  VZOOMEX 6 0",
        "  USE_REC_CFG 0",
        "  RECMODE 1",
        "  SMPTESYNC 0 30 100 40 1000 300 0 0 1 0 0",
        "  LOOP 0",
        "  LOOPGRAN 0 4",
        "  RECORD_PATH \"Audio Files\" \"\"",
        "  <RECORD_CFG",
        "    ZXZhdxgAAQ==",
        "  >",
        "  <APPLYFX_CFG",
        "  >",
        "  RENDER_FILE \"\"",
        "  RENDER_PATTERN \"\"",
        "  RENDER_FMT 0 2 0",
        "  RENDER_1X 0",
        "  RENDER_RANGE 1 0 0 0 1000",
        "  RENDER_RESAMPLE 3 0 1",
        "  RENDER_ADDTOPROJ 0",
        "  RENDER_STEMS 0",
        "  RENDER_DITHER 0",
        "  RENDER_TRIM 0.000001 0.000001 0 0",
        "  TIMELOCKMODE 0",
        "  TEMPOENVLOCKMODE 1",
        "  ITEMMIX 1",
        "  DEFPITCHMODE 589824 0",
        "  TAKELANE 1",
        "  SAMPLERATE 48000 1 0",
        "  <RENDER_CFG",
        "    ZXZhdxgAAQ==",
        "  >",
        "  LOCK 1",
        "  <METRONOME 6 2",
        "    VOL 0.25 0.125",
        "    BEATLEN 4",
        "    FREQ 1760 880 1",
        "    SAMPLES \"\" \"\" \"\" \"\"",
        "    SPLIGNORE 0 0",
        "    SPLDEF 2 660 \"\" 0 \"\"",
        "    SPLDEF 3 440 \"\" 0 \"\"",
        "    PATTERN 0 169",
        "    PATTERNSTR ABBB",
        "    MULT 1",
        "  >",
        "  GLOBAL_AUTO -1",
        "  TEMPO 60 4 4 1",
        "  PLAYRATE 1 0 0.25 4",
        "  SELECTION 0 0",
        "  SELECTION2 0 0",
        "  MASTERAUTOMODE 0",
        "  MASTERTRACKHEIGHT 0 0",
        "  MASTERPEAKCOL 16576",
        "  MASTERMUTESOLO 0",
        "  MASTERTRACKVIEW 1 0.6667 0.5 0.5 0 0 0 0 0 0 0 0 0 0 1",
        "  MASTERHWOUT 0 0 1 0 0 0 0 -1",
        "  MASTER_NCH 2 2",
        "  MASTER_VOLUME 1 0 -1 -1 1",
        "  MASTER_PANMODE 3",
        "  MASTER_PANLAWFLAGS 3",
        "  MASTER_FX 0",
        "  MASTER_SEL 0",
        "  <MASTERPLAYSPEEDENV",
        "    EGUID {9803FC77-4787-4218-9C71-A57DA34F2F8C}",
        "    ACT 0 -1",
        "    VIS 0 1 1",
        "    LANEHEIGHT 0 0",
        "    ARM 0",
        "    DEFSHAPE 0 -1 -1",
        "  >",
        "  <TEMPOENVEX",
        "    EGUID {63E74D85-0E6A-48A5-9090-8BD519357BB8}",
        "    ACT 0 -1",
        "    VIS 1 0 1",
        "    LANEHEIGHT 0 0",
        "    ARM 0",
        "    DEFSHAPE 1 -1 -1",
        "  >",
        "  RULERHEIGHT 86 86",
        "  RULERLANE 1 4 \"\" 0 -1 0",
        "  RULERLANE 2 8 \"\" 0 -1 0",
        "  <PROJBAY",
        "  >",
    ]

    tracks_by_num: dict[int, list[str]] = {i: [] for i in range(1, 8)}
    track_names: dict[int, str] = {}
    track_vols: dict[int, float] = {}
    iid = 1

    video = cfg.get("video")
    if video:
        track_names[video["track"]] = video.get("id", "video")
        track_vols[video["track"]] = VIDEO_TRACK_VOL
        vp = repo_root / video["path"]
        file_ref, src_type, file_suffix = stage_media(vp, rpp_dir, media_mode, repo_root)
        vp_len = media_duration(vp)
        tracks_by_num[video["track"]].append(
            make_item(
                vp.name,
                0,
                vp_len,
                True,
                file_ref,
                src_type,
                VIDEO_TRACK_VOL,
                iid,
                file_suffix,
            )
        )
        iid += 1

    for layer in cfg.get("scatter_layers", []):
        t = layer["track"]
        track_names[t] = layer.get("id", layer.get("name", f"track{t}"))
        track_vols[t] = float(layer.get("vol", 1.0))
        rel = layer["paths"][0]
        ap = repo_root / rel
        file_ref, src_type, file_suffix = stage_media(ap, rpp_dir, media_mode, repo_root)
        tracks_by_num[t].append(
            make_item(
                ap.name,
                0,
                media_duration(ap),
                False,
                file_ref,
                src_type,
                float(layer.get("vol", 1.0)),
                iid,
                file_suffix,
            )
        )
        iid += 1

    for layer in cfg.get("loop_layers", []):
        t = layer["track"]
        track_names[t] = layer.get("id", layer.get("name", f"track{t}"))
        track_vols[t] = float(layer.get("vol", 1.0))
        rel = layer["paths"][0]
        ap = repo_root / rel
        file_ref, src_type, file_suffix = stage_media(ap, rpp_dir, media_mode, repo_root)
        ap_len = media_duration(ap)
        tracks_by_num[t].append(
            make_item(
                ap.name,
                0,
                ap_len,
                True,
                file_ref,
                src_type,
                float(layer.get("vol", 1.0)),
                iid,
                file_suffix,
            )
        )
        iid += 1

    for layer in load_layer_template():
        t = layer["track"]
        if t not in track_names:
            track_names[t] = layer["id"]
            track_vols.setdefault(t, 1.0)

    body: list[str] = []

    js_ref = group_js_ref(rpp_dir, repo_root, media_mode)
    body.append(make_group_track(js_ref, GROUP_JS_EQ_PARAMS))

    track_fx_by_name: dict[str, list[str]] = dict(TRACK_FX_PRESETS)

    video_track_num = cfg.get("video", {}).get("track")
    for t in sorted(track_names.keys()):
        name = track_names[t]
        vol = track_vols.get(t, 1.0)
        if t == video_track_num:
            isbus = (2, -1)
            mute = True
        else:
            isbus = (0, 0)
            mute = False
        body.append(
            make_track(
                name,
                vol,
                isbus=isbus,
                mute=mute,
                fx_preset=track_fx_by_name.get(name),
            )
        )
        for item in tracks_by_num[t]:
            body.append(item)
        body.append("  >")

    footer = ["  <EXTENSIONS", "  >", ">"]
    return "\n".join(header + body + footer) + "\n"


def load_layer_template() -> list[dict]:
    text = LAYER_TEMPLATE_PATH.read_text(encoding="utf-8")
    layers = []
    for track, lid, name in re.findall(
        r"track\s*=\s*(\d+),\s*id\s*=\s*\"([^\"]+)\",\s*name\s*=\s*\"([^\"]+)\"",
        text,
    ):
        layers.append({"track": int(track), "id": lid, "name": name})
    return layers


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Rain subproject RPP")
    parser.add_argument(
        "--config",
        type=Path,
        help="path to asmr_config.lua",
    )
    parser.add_argument(
        "--scene",
        type=str,
        help="scene id under Rain/subprojects/<scene>/scripts/asmr_config.lua",
    )
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--media-mode",
        choices=("auto", "wsl_unc", "assets", "relative", "absolute"),
        default="auto",
        help="auto=按系统选择（Mac→absolute，Win/WSL→wsl_unc）；或显式指定",
    )
    args = parser.parse_args()

    if args.config:
        config_path = args.config
        out_dir = config_path.parent.parent
    elif args.scene:
        out_dir = (
            args.repo
            / "Reaper"
            / "Projects"
            / "Rain"
            / "subprojects"
            / args.scene
        )
        config_path = out_dir / "scripts" / "asmr_config.lua"
    else:
        parser.error("need --config or --scene")

    cfg = load_config(config_path)
    scene_id = cfg.get("scene_id", args.scene or "subproject")
    rpp_path = out_dir / f"{scene_id}.rpp"

    stage_rain_fx_assets(out_dir)

    mode_label = describe_media_mode(args.media_mode, args.repo)
    print(f"媒体路径: {mode_label}")

    rpp_path.write_text(
        build_rpp(cfg, args.repo, out_dir, args.media_mode),
        encoding="utf-8",
    )
    print(f"Wrote {rpp_path}")


if __name__ == "__main__":
    main()
