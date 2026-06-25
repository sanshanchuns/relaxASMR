#!/usr/bin/env python3
"""校验 / 试听 assets/api_sound 下的 API 生成音效。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
API_SOUND_DIR = REPO_ROOT / "assets" / "api_sound"

# 与 generate.py 保持一致
LOUDNESS_FAIL_DB = -48.0
LOUDNESS_WARN_DB = -36.0


def analyze_loudness(audio_path: Path) -> dict:
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(audio_path),
        "-af", "volumedetect", "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return {"error": "ffmpeg not found", "status": "error"}

    text = result.stderr
    loudness: dict = {"status": "ok"}
    for line in text.splitlines():
        if "mean_volume:" in line:
            loudness["mean_volume_db"] = float(line.split("mean_volume:")[1].split("dB")[0].strip())
        if "max_volume:" in line:
            loudness["max_volume_db"] = float(line.split("max_volume:")[1].split("dB")[0].strip())

    if "max_volume_db" not in loudness:
        loudness["status"] = "error"
        loudness["error"] = "volumedetect failed"
        return loudness

    mx = loudness["max_volume_db"]
    if mx < LOUDNESS_FAIL_DB:
        loudness["verdict"] = "fail"
    elif mx < LOUDNESS_WARN_DB:
        loudness["verdict"] = "warn"
    else:
        loudness["verdict"] = "pass"
    return loudness


def play_audio(audio_path: Path) -> bool:
    for player in ("ffplay", "mpv", "play"):
        if subprocess.run(["which", player], capture_output=True).returncode != 0:
            continue
        cmd = [player, str(audio_path)]
        if player == "ffplay":
            cmd = ["ffplay", "-nodisp", "-autoexit", str(audio_path)]
        print(f"播放: {audio_path}")
        subprocess.run(cmd, check=False)
        return True
    print("未找到 ffplay / mpv / play，请手动试听", file=sys.stderr)
    return False


def find_audio_files(target: str | None) -> list[Path]:
    if target:
        p = Path(target)
        if not p.is_absolute():
            p = REPO_ROOT / p
        if p.is_file():
            return [p]
        if p.is_dir():
            return sorted(p.rglob("api_*.mp3")) + sorted(p.rglob("api_*.wav"))
        # slug or id
        slug = target.replace("api_", "")
        found = list(API_SOUND_DIR.rglob(f"api_{slug}.*"))
        return [f for f in found if f.suffix.lower() in (".mp3", ".wav")]
    return sorted(API_SOUND_DIR.rglob("api_*.mp3")) + sorted(API_SOUND_DIR.rglob("api_*.wav"))


def update_sidecar_loudness(audio_path: Path, loudness: dict) -> None:
    json_path = audio_path.with_suffix(".json")
    if not json_path.is_file():
        return
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    meta["loudness"] = loudness
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def run_check(files: list[Path], *, play: bool, update_json: bool) -> int:
    fails = 0
    for audio_path in files:
        rel = audio_path.relative_to(REPO_ROOT)
        loudness = analyze_loudness(audio_path)
        if update_json:
            update_sidecar_loudness(audio_path, loudness)
        verdict = loudness.get("verdict", "error")
        mx = loudness.get("max_volume_db", "?")
        icon = {"pass": "OK", "warn": "WARN", "fail": "FAIL", "error": "ERR"}[verdict]
        print(f"[{icon}] {rel}  max={mx} dB")
        if verdict in ("fail", "error"):
            fails += 1
            if loudness.get("error"):
                print(f"       {loudness['error']}")
        elif verdict == "warn":
            print(f"       音量偏低，建议重生成或手调增益")
        if play:
            play_audio(audio_path)
    return fails


def main() -> None:
    parser = argparse.ArgumentParser(description="试听 / 校验 api_sound 响度")
    parser.add_argument("target", nargs="?", help="路径、slug 或 id（默认检查全部）")
    parser.add_argument("--play", action="store_true", help="检查后播放")
    parser.add_argument("--play-only", action="store_true", help="只播放，不检查")
    parser.add_argument("--update-json", action="store_true", help="将响度写回 sidecar json")
    args = parser.parse_args()

    files = find_audio_files(args.target)
    if not files:
        print("未找到音频文件", file=sys.stderr)
        sys.exit(1)

    if args.play_only:
        for f in files:
            play_audio(f)
        return

    fails = run_check(files, play=args.play, update_json=args.update_json)
    if fails:
        print(f"\n{ fails } 个文件响度异常（max < {LOUDNESS_FAIL_DB} dB），请 --force 重生成")
        sys.exit(1)


if __name__ == "__main__":
    main()
