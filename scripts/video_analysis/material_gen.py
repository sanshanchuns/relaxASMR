from pathlib import Path
import json
import time

from scripts.video_upload.material_store import SCHEMA_VERSION, write_material_json


def generate_youtube_material(video_path: Path, material_dir: Path) -> Path:
    """生成占位 YouTube 物料 JSON（后续由 generate_youtube_material 正式产出）。"""
    material_dir.mkdir(parents=True, exist_ok=True)

    base_name = video_path.name.split("_loop")[0] if "_loop" in video_path.name else video_path.stem

    json_path = material_dir / f"{base_name}_material.json"

    record = {
        "schema_version": SCHEMA_VERSION,
        "scene_id": base_name,
        "video_name": video_path.name,
        "title_en": f"Relaxing Rain Sounds for Sleep, Study & Focus | {base_name} [4K]",
        "description_en": (
            "Enjoy this 3-hour long relaxing rain video. Perfect for deep sleep, meditation, or focus.\n"
            "The gentle pitter-patter of raindrops will help you wash away stress and find inner peace."
        ),
        "title_zh": "",
        "description_zh": "",
        "tags": [
            "RainSounds",
            "RelaxingRain",
            "SleepNoise",
            "ASMRRain",
            "NatureSounds",
            "FocusMusic",
        ],
    }

    time.sleep(1)
    write_material_json(json_path, record)
    return json_path
