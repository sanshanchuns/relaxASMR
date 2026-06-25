#!/usr/bin/env python3
"""使用 ElevenLabs Sound Effects API 生成音效，输出到 assets/api_sound/<category>/。

每个条目生成：
  api_<id>.mp3   — API PCM 原声经 ffmpeg 转 MP3（仅格式转换）
  api_<id>.json  — 描述词、响度校验与生成参数

文档: https://elevenlabs.io/docs/eleven-api/guides/cookbooks/sound-effects
环境变量: ELEVENLABS_API_KEY
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
API_SOUND_DIR = REPO_ROOT / "assets" / "api_sound"
DEFAULT_PROMPTS = SCRIPT_DIR / "prompts.json"
API_FORMAT = "pcm_44100"

try:
    from audition import analyze_loudness, play_audio, update_sidecar_loudness
except ImportError:
    analyze_loudness = None  # type: ignore[misc, assignment]
    play_audio = None  # type: ignore[misc, assignment]
    update_sidecar_loudness = None  # type: ignore[misc, assignment]

try:
    from elevenlabs import ElevenLabs
except ImportError:
    ElevenLabs = None  # type: ignore[misc, assignment]


def safe_slug(text: str, max_len: int = 60) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"[^\w\-]+", "_", cleaned, flags=re.UNICODE)
    cleaned = cleaned.strip("._") or "untitled"
    return cleaned[:max_len]


def load_prompts_config(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "defaults": data.get("defaults", {}),
        "prompts": data.get("prompts", []),
    }


def get_api_key() -> str:
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "未找到 ELEVENLABS_API_KEY。请先 source ~/.zshrc 或 export。"
        )
    return key


def make_client() -> ElevenLabs:
    if ElevenLabs is None:
        raise RuntimeError("请先安装依赖: pip install -r requirements.txt")
    return ElevenLabs(api_key=get_api_key())


def generate_audio(
    client: ElevenLabs,
    text: str,
    *,
    output_format: str,
    loop: bool,
    duration_seconds: float | None,
    prompt_influence: float,
    model_id: str,
) -> bytes:
    audio = client.text_to_sound_effects.convert(
        text=text,
        output_format=output_format,
        loop=loop,
        duration_seconds=duration_seconds,
        prompt_influence=prompt_influence,
        model_id=model_id,
    )
    if isinstance(audio, (bytes, bytearray)):
        return bytes(audio)
    if hasattr(audio, "read"):
        return audio.read()
    chunks: list[bytes] = []
    for chunk in audio:
        chunks.append(chunk)
    return b"".join(chunks)


def pcm_sample_rate(api_format: str) -> int:
    if api_format.startswith("pcm_"):
        return int(api_format.split("_", 1)[1])
    return 44100


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 44100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def write_pcm_to_file(
    pcm_bytes: bytes,
    dest: Path,
    *,
    file_format: str,
    sample_rate: int,
    mp3_bitrate: int,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if file_format == "mp3":
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
                "-i", "pipe:0",
                "-codec:a", "libmp3lame", "-b:a", f"{mp3_bitrate}k",
                str(dest),
            ],
            input=pcm_bytes,
            check=True,
        )
        return
    if file_format == "wav":
        dest.write_bytes(pcm_to_wav(pcm_bytes, sample_rate))
        return
    raise ValueError(f"未知 file_format: {file_format}")


def resolve_file_format(item: dict, defaults: dict) -> str:
    fmt = item.get("file_format") or defaults.get("file_format") or "mp3"
    legacy = item.get("output_format") or defaults.get("output_format")
    if legacy and str(legacy).startswith("mp3"):
        fmt = "mp3"
    if legacy and str(legacy).startswith("pcm"):
        fmt = "wav"
    return fmt


def resolve_category(item: dict, defaults: dict) -> str:
    cat = item.get("category") or defaults.get("category") or item.get("layer") or "misc"
    return safe_slug(str(cat), max_len=40)


def api_paths(slug: str, category: str, ext: str) -> tuple[Path, Path]:
    base = f"api_{slug}"
    cat_dir = API_SOUND_DIR / category
    return cat_dir / f"{base}.{ext}", cat_dir / f"{base}.json"


def next_numeric_slug() -> str:
    existing: set[str] = set()
    for p in API_SOUND_DIR.rglob("api_*.*"):
        if p.suffix.lower() in (".mp3", ".wav", ".m4a"):
            stem = p.stem
            if stem.startswith("api_"):
                existing.add(stem[4:])
    n = 1
    while f"{n:03d}" in existing:
        n += 1
    return f"{n:03d}"


def write_sidecar(json_path: Path, meta: dict) -> None:
    json_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_item_params(item: dict, defaults: dict) -> dict:
    file_format = resolve_file_format(item, defaults)
    return {
        "text": item["text"],
        "duration_seconds": item.get("duration_seconds", defaults.get("duration_seconds")),
        "loop": item.get("loop", defaults.get("loop", False)),
        "prompt_influence": item.get("prompt_influence", defaults.get("prompt_influence", 0.3)),
        "model_id": item.get("model_id", defaults.get("model_id", "eleven_text_to_sound_v2")),
        "api_format": API_FORMAT,
        "file_format": file_format,
        "mp3_bitrate": int(item.get("mp3_bitrate", defaults.get("mp3_bitrate", 128))),
    }


def save_generation(
    client: ElevenLabs,
    slug: str,
    category: str,
    params: dict,
    meta_extra: dict,
    *,
    dry_run: bool,
    force: bool,
    play: bool,
) -> dict:
    ext = params["file_format"]
    audio_path, json_path = api_paths(slug, category, ext)
    entry = {
        "slug": slug,
        "category": category,
        "text": params["text"],
        "audio_path": str(audio_path.relative_to(REPO_ROOT)),
        "json_path": str(json_path.relative_to(REPO_ROOT)),
        **meta_extra,
    }

    if dry_run:
        entry["status"] = "dry_run"
        return entry

    if audio_path.is_file() and not force:
        print(f"  跳过(已存在): {category}/api_{slug}.{ext}")
        entry["status"] = "skipped"
        if analyze_loudness:
            loudness = analyze_loudness(audio_path)
            entry["loudness"] = loudness
            if loudness.get("verdict") == "fail":
                print(f"    ⚠ 已存在文件响度异常 max={loudness.get('max_volume_db')} dB，建议 --force")
        return entry

    try:
        print(f"  生成: {category}/api_{slug}.{ext}...")
        api_params = {
            "text": params["text"],
            "output_format": params["api_format"],
            "loop": params["loop"],
            "duration_seconds": params["duration_seconds"],
            "prompt_influence": params["prompt_influence"],
            "model_id": params["model_id"],
        }
        pcm = generate_audio(client, **api_params)
        sample_rate = pcm_sample_rate(params["api_format"])
        write_pcm_to_file(
            pcm,
            audio_path,
            file_format=params["file_format"],
            sample_rate=sample_rate,
            mp3_bitrate=params["mp3_bitrate"],
        )
        loudness = analyze_loudness(audio_path) if analyze_loudness else {}
        meta = {
            "text": params["text"],
            "slug": slug,
            "category": category,
            "duration_seconds": params["duration_seconds"],
            "loop": params["loop"],
            "prompt_influence": params["prompt_influence"],
            "model_id": params["model_id"],
            "api_format": params["api_format"],
            "file_format": params["file_format"],
            "mp3_bitrate": params["mp3_bitrate"],
            "sample_rate": sample_rate,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": "elevenlabs",
            "post_process": "format_only",
            "loudness": loudness,
            **meta_extra,
        }
        write_sidecar(json_path, meta)
        entry["status"] = "generated"
        entry["bytes"] = audio_path.stat().st_size
        entry["loudness"] = loudness

        verdict = loudness.get("verdict")
        mx = loudness.get("max_volume_db")
        if verdict == "fail":
            print(f"    ⚠ 响度异常 max={mx} dB（近乎无声），请试听并 --force 重生成", file=sys.stderr)
            entry["status"] = "generated_silent"
        elif verdict == "warn":
            print(f"    ⚠ 响度偏低 max={mx} dB，建议试听")
        else:
            print(f"    响度 OK max={mx} dB")

        if play and play_audio:
            play_audio(audio_path)

        time.sleep(0.5)
    except Exception as exc:
        print(f"  ✗ 失败 {category}/api_{slug}: {exc}", file=sys.stderr)
        entry["status"] = "failed"
        entry["error"] = str(exc)

    return entry


def run_from_config(
    config_path: Path,
    *,
    ids: list[str] | None,
    dry_run: bool,
    force: bool,
    play: bool,
) -> list[dict]:
    cfg = load_prompts_config(config_path)
    defaults = cfg["defaults"]
    prompts = cfg["prompts"]

    if ids:
        targets = [p for p in prompts if p.get("id") in ids]
        unknown = set(ids) - {p.get("id") for p in targets}
        if unknown:
            print(f"Warning: 未知 id: {', '.join(sorted(unknown))}", file=sys.stderr)
    else:
        targets = prompts

    print(f"配置: {config_path}")
    print(f"输出: {API_SOUND_DIR}/<category>/")
    print(f"条目: {len(targets)}")

    client = None if dry_run else make_client()
    manifest: list[dict] = []

    for item in targets:
        slug = item.get("id") or safe_slug(item["text"][:40])
        category = resolve_category(item, defaults)
        params = resolve_item_params(item, defaults)
        entry = save_generation(
            client,
            slug,
            category,
            params,
            {
                "id": item.get("id"),
                "layer": item.get("layer"),
                "series": item.get("series"),
                "scene": item.get("scene"),
            },
            dry_run=dry_run,
            force=force,
            play=play,
        )
        manifest.append(entry)

    API_SOUND_DIR.mkdir(parents=True, exist_ok=True)
    index_path = API_SOUND_DIR / "index.json"
    index_data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": str(config_path),
        "items": manifest,
    }
    if not dry_run:
        index_path.write_text(
            json.dumps(index_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"index: {index_path}")

    return manifest


def run_single(
    text: str,
    *,
    slug: str | None,
    category: str,
    duration_seconds: float | None,
    loop: bool,
    prompt_influence: float,
    model_id: str,
    output_format: str,
    file_format: str,
    dry_run: bool,
    force: bool,
    play: bool,
) -> None:
    params = {
        "text": text,
        "duration_seconds": duration_seconds,
        "loop": loop,
        "prompt_influence": prompt_influence,
        "model_id": model_id,
        "api_format": API_FORMAT,
        "file_format": file_format,
        "mp3_bitrate": 128,
    }
    use_slug = slug or next_numeric_slug()
    cat = safe_slug(category)

    if dry_run:
        audio_path, json_path = api_paths(use_slug, cat, file_format)
        print(f"[dry-run] {cat}/api_{use_slug}.{file_format}")
        print(f"  api={API_FORMAT} → file={file_format}")
        print(f"  text={text}")
        print(f"  audio={audio_path}")
        print(f"  json={json_path}")
        return

    client = make_client()
    entry = save_generation(
        client, use_slug, cat, params, {}, dry_run=False, force=force, play=play,
    )
    if entry.get("status") in ("generated", "generated_silent"):
        print(f"已保存: {entry['audio_path']}")
        print(f"描述: {entry['json_path']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ElevenLabs → assets/api_sound/<category>/api_xx.mp3",
    )
    parser.add_argument("text", nargs="?", help="单条提示词（英文效果更好）")
    parser.add_argument("--config", default=str(DEFAULT_PROMPTS), help="prompts.json 路径")
    parser.add_argument("--all", action="store_true", help="生成配置中全部条目")
    parser.add_argument("--id", action="append", help="指定 prompts.json 中的 id")
    parser.add_argument("--slug", help="单条模式文件名后缀（默认自动编号 api_001）")
    parser.add_argument("--category", default="misc", help="单条模式分类子目录")
    parser.add_argument("--list", action="store_true", help="列出配置中的条目")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不调用 API")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    parser.add_argument("--play", action="store_true", help="生成后自动播放试听")
    parser.add_argument("--duration", type=float, help="时长秒数 (0.5~30)")
    parser.add_argument("--loop", action="store_true", help="生成可无缝循环的音效")
    parser.add_argument("--no-loop", action="store_true", help="禁用循环")
    parser.add_argument("--prompt-influence", type=float, default=0.35)
    parser.add_argument("--model-id", default="eleven_text_to_sound_v2")
    parser.add_argument(
        "--file-format",
        default="mp3",
        choices=["mp3", "wav"],
        help="落地格式（API 固定 pcm_44100，mp3 仅 ffmpeg 转码）",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (SCRIPT_DIR / config_path).resolve()

    if args.list:
        if not config_path.is_file():
            print(f"Error: 找不到 {config_path}", file=sys.stderr)
            sys.exit(1)
        cfg = load_prompts_config(config_path)
        for p in cfg["prompts"]:
            sid = p.get("id", "?")
            cat = resolve_category(p, cfg["defaults"])
            print(f"  {cat}/api_{sid}: [{p.get('series')}/{p.get('layer')}] {p['text'][:70]}")
        return

    loop = True if args.loop else False if args.no_loop else True

    if args.text:
        run_single(
            args.text,
            slug=args.slug,
            category=args.category,
            duration_seconds=args.duration,
            loop=loop,
            prompt_influence=args.prompt_influence,
            model_id=args.model_id,
            output_format=args.file_format,
            file_format=args.file_format,
            dry_run=args.dry_run,
            force=args.force,
            play=args.play,
        )
        return

    if args.all or args.id:
        if not config_path.is_file():
            print(f"Error: 找不到 {config_path}", file=sys.stderr)
            sys.exit(1)
        manifest = run_from_config(
            config_path, ids=args.id, dry_run=args.dry_run, force=args.force, play=args.play,
        )
        ok = sum(1 for x in manifest if x.get("status") in ("generated", "skipped", "dry_run"))
        print(f"\n完成。处理 {ok}/{len(manifest)} 条。")
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
