import hashlib
import json
import os
import re
from pathlib import Path

DEFAULT_GEMINI_MODELS = [
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
]

_KEY_NAMES = ["GEMINI_API_KEY", "GEMINI_JAPAN_API_KEY", "GEMINI_USA_API_KEY"]


def load_gemini_api_keys(*, skip_japan: bool = True) -> list[tuple[str, str]]:
    """Return [(key_name, key_value), ...] in priority order."""
    api_keys: dict[str, str] = {}
    for name in _KEY_NAMES:
        if os.environ.get(name):
            api_keys[name] = os.environ[name]

    zshrc_path = os.path.expanduser("~/.zshrc")
    if os.path.exists(zshrc_path):
        with open(zshrc_path, encoding="utf-8") as f:
            for line in f:
                if not line.startswith("export "):
                    continue
                match = re.match(r'export\s+([A-Z_]+)="?(.*?)"?$', line.strip())
                if match and match.group(1) in _KEY_NAMES:
                    name = match.group(1)
                    if name not in api_keys:
                        api_keys[name] = match.group(2)

    out: list[tuple[str, str]] = []
    for name in _KEY_NAMES:
        if name not in api_keys:
            continue
        if skip_japan and name == "GEMINI_JAPAN_API_KEY":
            continue
        out.append((name, api_keys[name]))
    return out


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def call_gemini_vision_json(
    prompt: str,
    image_path: Path,
    *,
    on_progress=None,
    models: list[str] | None = None,
) -> dict:
    """Send image + prompt to Gemini; parse JSON response."""
    try:
        from google import genai
        from PIL import Image
    except ImportError as e:
        raise RuntimeError(f"VLM 依赖缺失: {e}") from e

    available_keys = load_gemini_api_keys()
    if not available_keys:
        raise RuntimeError("未配置任何 GEMINI API KEY (包括通用、JAPAN、USA)")

    try:
        img = Image.open(image_path)
    except Exception as e:
        raise RuntimeError(f"无法打开画面图片: {e}") from e

    models_to_try = models or DEFAULT_GEMINI_MODELS
    errors: list[str] = []

    for key_name, key_val in available_keys:
        try:
            msg = f"正在尝试使用 {key_name} 请求大模型..."
            if on_progress:
                on_progress(msg)
            else:
                print(f"vlm_engine: {msg}")

            client = genai.Client(api_key=key_val)
            response = None
            last_err: Exception | None = None

            for model_name in models_to_try:
                try:
                    if on_progress:
                        on_progress(f"  -> 尝试模型: {model_name} ...")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[prompt, img],
                    )
                    break
                except Exception as me:
                    last_err = me

            if response is None:
                raise last_err or RuntimeError("无可用模型")

            text = _strip_json_fence(response.text)
            return json.loads(text)
        except Exception as e:
            err_msg = f"{key_name} 请求失败: {e}"
            if on_progress:
                on_progress(f"  -> {err_msg}")
            else:
                print(f"vlm_engine: {err_msg}")
            errors.append(err_msg)

    raise RuntimeError("所有 API Key 均测试失败: " + "; ".join(errors))


def analyze_with_vlm(image_path: Path, on_progress=None) -> dict:
    """
    Uses Gemini to analyze a single video frame and map it to sound-library dimension IDs.
    Returns a dictionary with 'l3_key', 'l2_key', 'l1_key', and 'climate_key'.
    """
    prompt = """
You are a professional Foley Artist and Audio Director.
Analyze the provided single video frame and assign the best matching acoustic parameters from our rain library.

Here are the available parameter choices with their internal IDs:

1. Close Layer (Foreground Material hit by rain):
100: Foliage Lush (茂密植被)
110: Foliage Yielding (稀疏植被/泥地)
290: Concrete (混凝土/石板路)
170: Concrete Diffuse (漫反射粗糙石面)
210: Stone Echoing (回声石墙/山洞)
230: Wood Roof (木屋顶/木板栈道)
190: Wood Thin (薄木板/木地板)
180: Wood Tonal (共振木材/木桥)
150: Water (水面/水洼)
280: Glass Roof (玻璃屋顶/窗户)
200: Metal Roof (金属屋顶)

2. Space Layer (Environment):
530: Foliage Canopy (树冠遮挡下的环境)
590: Foliage Dense (茂密森林深处)
580: Building Canopy (楼宇雨棚/屋檐下)
610: Street Dense (密集街区/两旁有建筑物)
520: Walls Concrete (混凝土高墙环绕)
560: Inner Yard (庭院)
640: Wood Deck (木平台)

3. Distant Layer (Background Atmosphere):
800: Airy Breeze (空灵微风，白噪声底噪)
840: Broadband Shower (宽频阵雨，城市或空旷地带的远景雨声)
980: Thick Shower (浓密阵雨，森林远景)
870: Distant Veil (远方雨幕)
910: Gentle Swish (轻柔沙响，风吹草动)
820: Balanced Sizzle (均衡雷雨轰鸣或山谷回声)
900: Forest Whisper (森林低语)
880: Echo River (河谷回声或远方水流)

4. Climate (Rain Intensity):
drizzle: Very light rain, occasional drips
light: Gentle continuous rain
medium: Standard balanced rain
heavy: Heavy pouring storm

Analyze the scene thoroughly. Are there fences, stone paths, grass, trees? Is it a dense forest or urban street? What is the distance of the atmospheric noise?
Return your answer ONLY as a raw JSON object with NO markdown formatting. It must contain the exact numeric ID for the layers, and the string for climate.

Example:
{
  "l1_key": 290,
  "l2_key": 560,
  "l3_key": 840,
  "climate_key": "medium"
}
"""
    data = call_gemini_vision_json(prompt, image_path, on_progress=on_progress)
    return {
        "l3_key": data.get("l3_key", 840),
        "l2_key": data.get("l2_key", 590),
        "l1_key": data.get("l1_key", 100),
        "climate_key": data.get("climate_key", "medium"),
    }


def seed_rng(seed: str):
    """Deterministic RNG from string seed (shared by metadata modules)."""
    import random

    h = int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16)
    return random.Random(h)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        res = analyze_with_vlm(Path(sys.argv[1]))
        print(json.dumps(res, indent=2))
