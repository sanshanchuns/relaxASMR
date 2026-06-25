#!/usr/bin/env python3
"""使用 ElevenLabs Sound Effects API 生成音效，输出到 assets/api_sound/。

每个条目生成：
  api_<id>.wav   — 音频（PCM 转 WAV）
  api_<id>.json  — 描述词与生成参数

文档: https://elevenlabs.io/docs/eleven-api/guides/cookbooks/sound-effects
环境变量: ELEVENLABS_API_KEY
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
API_SOUND_DIR = REPO_ROOT / "assets" / "api_sound"
DEFAULT_PROMPTS = SCRIPT_DIR / "prompts.json"

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


def generate_pcm(
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


def pcm_sample_rate(output_format: str) -> int:
    if output_format.startswith("pcm_"):
        return int(output_format.split("_", 1)[1])
    return 44100


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 44100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def api_paths(slug: str) -> tuple[Path, Path]:
    base = f"api_{slug}"
    return API_SOUND_DIR / f"{base}.wav", API_SOUND_DIR / f"{base}.json"


def next_numeric_slug() -> str:
    existing = set()
    for p in API_SOUND_DIR.glob("api_*.wav"):
        stem = p.stem  # api_xxx
        existing.add(stem[4:])  # remove api_
    n = 1
    while f"{n:03d}" in existing:
        n += 1
    return f"{n:03d}"


def write_sidecar(
    json_path: Path,
    meta: dict,
) -> None:
    json_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_item_params(item: dict, defaults: dict) -> dict:
    return {
        "text": item["text"],
        "duration_seconds": item.get("duration_seconds", defaults.get("duration_seconds")),
        "loop": item.get("loop", defaults.get("loop", False)),
        "prompt_influence": item.get("prompt_influence", defaults.get("prompt_influence", 0.3)),
        "model_id": item.get("model_id", defaults.get("model_id", "eleven_text_to_sound_v2")),
        "output_format": item.get("output_format", defaults.get("output_format", "pcm_44100")),
    }


def save_generation(
    client: ElevenLabs,
    slug: str,
    params: dict,
    meta_extra: dict,
    *,
    dry_run: bool,
) -> dict:
    wav_path, json_path = api_paths(slug)
    entry = {
        "slug": slug,
        "text": params["text"],
        "wav_path": str(wav_path.relative_to(REPO_ROOT)),
        "json_path": str(json_path.relative_to(REPO_ROOT)),
        **meta_extra,
    }

    if dry_run:
        entry["status"] = "dry_run"
        return entry

    if wav_path.is_file():
        print(f"  跳过(已存在): {wav_path.name}")
        entry["status"] = "skipped"
        return entry

    try:
        print(f"  生成: api_{slug}...")
        pcm = generate_pcm(client, **params)
        sample_rate = pcm_sample_rate(params["output_format"])
        wav_bytes = pcm_to_wav(pcm, sample_rate)
        API_SOUND_DIR.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(wav_bytes)
        meta = {
            "text": params["text"],
            "slug": slug,
            "duration_seconds": params["duration_seconds"],
            "loop": params["loop"],
            "prompt_influence": params["prompt_influence"],
            "model_id": params["model_id"],
            "output_format": params["output_format"],
            "sample_rate": sample_rate,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": "elevenlabs",
            **meta_extra,
        }
        write_sidecar(json_path, meta)
        entry["status"] = "generated"
        entry["bytes"] = len(wav_bytes)
        time.sleep(0.5)
    except Exception as exc:
        print(f"  ✗ 失败 api_{slug}: {exc}", file=sys.stderr)
        entry["status"] = "failed"
        entry["error"] = str(exc)

    return entry


def run_from_config(
    config_path: Path,
    *,
    ids: list[str] | None,
    dry_run: bool,
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
    print(f"输出: {API_SOUND_DIR}")
    print(f"条目: {len(targets)}")

    client = None if dry_run else make_client()
    manifest: list[dict] = []

    for item in targets:
        slug = item.get("id") or safe_slug(item["text"][:40])
        params = resolve_item_params(item, defaults)
        entry = save_generation(
            client,
            slug,
            params,
            {
                "id": item.get("id"),
                "layer": item.get("layer"),
                "series": item.get("series"),
            },
            dry_run=dry_run,
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
    duration_seconds: float | None,
    loop: bool,
    prompt_influence: float,
    model_id: str,
    output_format: str,
    dry_run: bool,
) -> None:
    params = {
        "text": text,
        "duration_seconds": duration_seconds,
        "loop": loop,
        "prompt_influence": prompt_influence,
        "model_id": model_id,
        "output_format": output_format,
    }
    use_slug = slug or next_numeric_slug()

    if dry_run:
        wav_path, json_path = api_paths(use_slug)
        print(f"[dry-run] api_{use_slug}")
        print(f"  text={text}")
        print(f"  wav={wav_path}")
        print(f"  json={json_path}")
        return

    client = make_client()
    entry = save_generation(client, use_slug, params, {}, dry_run=False)
    if entry.get("status") == "generated":
        print(f"已保存: {entry['wav_path']}")
        print(f"描述: {entry['json_path']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ElevenLabs → assets/api_sound/api_xx.wav")
    parser.add_argument("text", nargs="?", help="单条提示词（英文效果更好）")
    parser.add_argument("--config", default=str(DEFAULT_PROMPTS), help="prompts.json 路径")
    parser.add_argument("--all", action="store_true", help="生成配置中全部条目")
    parser.add_argument("--id", action="append", help="指定 prompts.json 中的 id")
    parser.add_argument("--slug", help="单条模式文件名后缀（默认自动编号 api_001）")
    parser.add_argument("--list", action="store_true", help="列出配置中的条目")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不调用 API")
    parser.add_argument("--duration", type=float, help="时长秒数 (0.5~30)")
    parser.add_argument("--loop", action="store_true", help="生成可无缝循环的音效")
    parser.add_argument("--no-loop", action="store_true", help="禁用循环")
    parser.add_argument("--prompt-influence", type=float, default=0.35)
    parser.add_argument("--model-id", default="eleven_text_to_sound_v2")
    parser.add_argument(
        "--output-format",
        default="pcm_44100",
        help="API 输出格式，默认 pcm_44100 转 WAV",
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
            print(f"  api_{sid}: [{p.get('series')}/{p.get('layer')}] {p['text'][:70]}")
        return

    loop = True if args.loop else False if args.no_loop else True

    if args.text:
        run_single(
            args.text,
            slug=args.slug,
            duration_seconds=args.duration,
            loop=loop,
            prompt_influence=args.prompt_influence,
            model_id=args.model_id,
            output_format=args.output_format,
            dry_run=args.dry_run,
        )
        return

    if args.all or args.id:
        if not config_path.is_file():
            print(f"Error: 找不到 {config_path}", file=sys.stderr)
            sys.exit(1)
        manifest = run_from_config(config_path, ids=args.id, dry_run=args.dry_run)
        ok = sum(1 for x in manifest if x.get("status") in ("generated", "skipped", "dry_run"))
        print(f"\n完成。处理 {ok}/{len(manifest)} 条。")
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
