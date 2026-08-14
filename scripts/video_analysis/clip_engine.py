import logging
from pathlib import Path
from typing import Any, Callable, Tuple

from PIL import Image

from scripts.video_analysis.analyze import CLOSE_NAMES, DISTANT_NAMES, SPACE_NAMES, VSTParams
from scripts.video_analysis.torch_runtime import require_torch, resolve_clip_device

logging.getLogger("transformers").setLevel(logging.ERROR)

CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"
_clip_model = None
_clip_processor = None
_device = None


def get_clip_components():
    global _clip_model, _clip_processor, _device
    require_torch()
    from transformers import CLIPModel, CLIPProcessor

    if _clip_model is None:
        _device = resolve_clip_device()
        _clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME).to(_device)
        # use_fast=True：避免 transformers 默认慢速 ImageProcessor 的启动警告
        _clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME, use_fast=True)
    return _clip_model, _clip_processor, _device

DISTANT_PROMPTS = {
    910: "远方是风吹动竹林或草丛的沙沙声 (Distant rustling bamboo or grass)",
    820: "远方是空旷山谷传来的低沉雷雨轰鸣 (Distant low hollow echo from a valley)",
    980: "远方是连绵浓密的森林雨幕 (Distant thick forest shower)",
    870: "远方是开阔平静的湖泊或水面 (Distant calm lake or water)",
    840: "远方是城市街道白噪声般的阵雨 (Distant broadband shower in a city)"
}

SPACE_PROMPTS = {
    580: "有屋檐、窗户或建筑遮挡的半封闭避雨空间 (Sheltered space looking out from a window or roof)",
    590: "被茂密树林和高大树冠完全遮盖的森林深处 (Deep dense forest entirely covered by trees)",
    610: "两旁有建筑物遮挡的城市街道、小巷或公路 (Urban street or alleyway surrounded by buildings)",
    530: "被树冠遮挡的森林空间，可见缝隙天光或林下开阔感 (Forest space under tree canopy with filtered sky light)",
}

CLOSE_PROMPTS = {
    120: "雨滴打在传统建筑的瓦片屋顶、砖墙或亭台屋檐上 (Raindrops hitting traditional building tile roof, brick wall or pavilion eaves)",
    100: "雨滴打在茂密的植物大叶片或芭蕉叶上 (Raindrops hitting lush large leaves or tropical plants)",
    150: "雨滴打在开阔的水面、池塘或溪流上 (Raindrops hitting open water, lake, or pond)",
    290: "雨滴打在自然石头、岩石或铺设的石板小径上 (Raindrops hitting natural stones, rocks, or paved stone path)",
    110: "雨滴打在稀疏的草地、泥土或低矮植物上 (Raindrops hitting sparse grass, dirt, or ground)",
    250: "雨滴打在金属铁皮屋顶、车辆或遮雨棚上 (Raindrops hitting metal roof or shelter)",
    190: "雨滴打在人工建造的平整木板栈道、木桥或木地板上 (Raindrops hitting man-made flat wooden boardwalk, wooden bridge or wooden planks)"
}

RAIN_PROMPTS = {
    "drizzle": "极其轻柔的毛毛细雨，零星滴落，几近停止 (Very light drizzle, sparse gentle drops)",
    "light": "淅淅沥沥的小雨，温和绵长，雨丝细腻 (Gentle light rain)",
    "medium": "中等强度的普通降雨，雨势连绵，地面有明显水花 (Moderate steady rainfall with visible splashes)",
    "heavy": "倾盆暴雨，雨势猛烈密集，视线模糊 (Heavy torrential downpour, intense storm)"
}

WETNESS_PROMPTS = {
    "dry": "地面略显干燥，仅有少许水迹，刚开始下雨 (Ground is slightly dry with few water marks, rain just started)",
    "wet": "地面完全湿透，潮湿泥泞或有大面积积水倒影 (Ground is completely wet, muddy or flooded with reflections)"
}

def analyze_dimension(image, candidates: dict, model, processor, device):
    keys = list(candidates.keys())
    texts = list(candidates.values())
    inputs = processor(text=texts, images=image, return_tensors="pt", padding=True).to(device)
    torch = require_torch()
    with torch.no_grad():
        outputs = model(**inputs)
        probs = outputs.logits_per_image.softmax(dim=1).cpu().numpy()[0]
    best_idx = probs.argmax()
    return keys[best_idx], texts[best_idx], float(probs[best_idx])

def _layer_label(l_val: int, names: dict) -> str:
    if l_val in names:
        en, cn = names[l_val]
        return f"{cn} {en}"
    return f"Unknown({l_val})"

def analyze_and_map_with_clip(image_path: str, on_progress=None):
    if on_progress:
        on_progress("正在加载 CLIP 视觉模型...")
    model, processor, device = get_clip_components()
    
    if on_progress:
        on_progress("正在读取画面...")
    image = Image.open(image_path).convert("RGB")
    
    results = {}
    
    if on_progress:
        on_progress("正在进行 CLIP 多维度空间匹配 (1/5: 远景)...")
    dist_key, dist_desc, dist_prob = analyze_dimension(image, DISTANT_PROMPTS, model, processor, device)
    results["l3"] = {"key": dist_key, "desc": dist_desc, "prob": dist_prob}
    
    if on_progress:
        on_progress("正在进行 CLIP 多维度空间匹配 (2/5: 空间)...")
    spc_key, spc_desc, spc_prob = analyze_dimension(image, SPACE_PROMPTS, model, processor, device)
    results["l2"] = {"key": spc_key, "desc": spc_desc, "prob": spc_prob}
    
    if on_progress:
        on_progress("正在进行 CLIP 多维度空间匹配 (3/5: 近景)...")
    cls_key, cls_desc, cls_prob = analyze_dimension(image, CLOSE_PROMPTS, model, processor, device)
    results["l1"] = {"key": cls_key, "desc": cls_desc, "prob": cls_prob}
    
    if on_progress:
        on_progress("正在进行 CLIP 多维度空间匹配 (4/5: 雨势)...")
    rain_key, rain_desc, rain_prob = analyze_dimension(image, RAIN_PROMPTS, model, processor, device)
    results["rain"] = {"key": rain_key, "desc": rain_desc, "prob": rain_prob}
    
    if on_progress:
        on_progress("正在进行 CLIP 多维度空间匹配 (5/5: 湿度)...")
    wet_key, wet_desc, wet_prob = analyze_dimension(image, WETNESS_PROMPTS, model, processor, device)
    results["wetness"] = {"key": wet_key, "desc": wet_desc, "prob": wet_prob}
    
    # Evocative Naming Logic (matching RainVST preset style)
    loc_en, loc_cn = "Unknown Location", "未知场景"
    if spc_key == 590: # Forest
        if cls_key == 100: loc_en, loc_cn = "Leafy Jungle", "芭蕉密林"
        elif cls_key == 150: loc_en, loc_cn = "Forest Pond", "密林池塘"
        elif cls_key == 110: loc_en, loc_cn = "Woodland Moss", "密林草地"
        elif cls_key == 290: loc_en, loc_cn = "Rocky Forest Path", "密林石板小径"
        elif cls_key == 190: loc_en, loc_cn = "Forest Boardwalk", "密林木栈道"
        else: loc_en, loc_cn = "Deep Forest", "幽深密林"
    elif spc_key == 580: # Shelter
        if cls_key == 120: loc_en, loc_cn = "Pavilion Eaves", "亭台屋檐"
        elif cls_key == 250: loc_en, loc_cn = "Metal Shelter", "铁皮雨棚"
        elif cls_key == 190: loc_en, loc_cn = "Wooden Porch", "木质门廊"
        elif cls_key == 290: loc_en, loc_cn = "Stone Patio", "石板庭院"
        else: loc_en, loc_cn = "Sheltered Balcony", "避雨阳台"
    elif spc_key == 610: # Street
        if cls_key == 290: loc_en, loc_cn = "Cobblestone Alley", "石板小巷"
        elif cls_key == 250: loc_en, loc_cn = "Urban Bus Stop", "城市公交站"
        else: loc_en, loc_cn = "City Street", "城市街道"
    elif spc_key == 530: # Open
        if cls_key == 150: loc_en, loc_cn = "Open Lake", "开阔湖面"
        elif cls_key == 110: loc_en, loc_cn = "Meadow Field", "旷野草甸"
        else: loc_en, loc_cn = "Open Landscape", "开阔原野"
        
    rain_en, rain_cn = "Rain", "降雨"
    if rain_key == "drizzle": rain_en, rain_cn = "Whispering Drizzle", "微风细雨"
    elif rain_key == "light": rain_en, rain_cn = "Gentle Rain", "淅沥小雨"
    elif rain_key == "medium": rain_en, rain_cn = "Steady Shower", "连绵秋雨"
    elif rain_key == "heavy": rain_en, rain_cn = "Stormy Downpour", "狂风暴雨"
    
    scene_en = f"{loc_en} {rain_en}"
    scene_cn = f"{loc_cn}{rain_cn}"
    
    if on_progress:
        pass

    # Base params mapping (default balanced)
    rfdn = 0.5
    rfin = 0.5
    sucd = 0.5
    if rain_key == "drizzle":
        rfdn = 0.35; rfin = 0.05; sucd = 0.8
    elif rain_key == "light":
        rfdn = 0.5; rfin = 0.15; sucd = 0.6
    elif rain_key == "medium":
        rfdn = 0.7; rfin = 0.45; sucd = 0.4
    elif rain_key == "heavy":
        rfdn = 0.95; rfin = 0.85; sucd = 0.2
        
    rffc = 0.8 if wet_key == "wet" else 0.4
    
    
    if on_progress:
        # Just to keep the user informed
        from scripts.video_analysis.analyze import DISTANT_NAMES, SPACE_NAMES, CLOSE_NAMES
        l3_en, l3_cn = DISTANT_NAMES.get(dist_key, ("Unknown", "未知"))
        l2_en, l2_cn = SPACE_NAMES.get(spc_key, ("Unknown", "未知"))
        l1_en, l1_cn = CLOSE_NAMES.get(cls_key, ("Unknown", "未知"))
        on_progress(f"CLIP 分析完成，输出 [{l3_cn} + {l2_cn} + {l1_cn}]")
            
    return [], results

def generate_ai_report(video_id: str, p: VSTParams, ai_results: dict) -> str:
    """Generate Markdown report for AI multi-dimensional analysis."""
    lines = [
        f"# {video_id} RAIN VST AI 多维度解耦分析",
        "",
        f"![首帧]({video_id}.jpg)",
        "",
        "## AI 场景降维推断 (Zero-Shot CLIP)",
        "本分析通过零样本视觉大语言模型，直接将画面特征映射至 RAIN VST 的控制维度。",
        "",
        "### 1. Close (近景材质层)",
        f"- **最佳匹配**: `{ai_results['l1']['desc']}`",
        f"- **置信度**: {ai_results['l1']['prob']*100:.1f}%",
        f"- **映射结果**: `l1 = {p.l1}` ({p.l1_name})",
        "",
        "### 2. Space (空间环境层)",
        f"- **最佳匹配**: `{ai_results['l2']['desc']}`",
        f"- **置信度**: {ai_results['l2']['prob']*100:.1f}%",
        f"- **映射结果**: `l2 = {p.l2}` ({p.l2_name})",
        "",
        "### 3. Distant (远景氛围层)",
        f"- **最佳匹配**: `{ai_results['l3']['desc']}`",
        f"- **置信度**: {ai_results['l3']['prob']*100:.1f}%",
        f"- **映射结果**: `l3 = {p.l3}` ({p.l3_name})",
        "",
        "### 4. Rainfall (降雨形态)",
        f"- **雨量**: `{ai_results['rain']['desc']}` ({ai_results['rain']['prob']*100:.1f}%)",
        f"- **湿度**: `{ai_results['wetness']['desc']}` ({ai_results['wetness']['prob']*100:.1f}%)",
        f"- **映射结果**: `Density={p.rfdn:.2f}`, `Intensity={p.rfin:.2f}`, `Wetness={p.rffc:.2f}`, `Drops={p.sucd:.2f}`",
        "",
        "## VST 最终参数总结",
        f"> ✅ 动态合成预设: **{p.scene_cn}**",
        "",
        "| 参数层级 | 参数值 | 说明 |",
        "|---------|---------|------|",
        f"| **远景** | {p.l3_name} (l3={p.l3}) | AI 环境底噪推断 |",
        f"| **空间** | {p.l2_name} (l2={p.l2}) | AI 空间反射推断 |",
        f"| **近景** | {p.l1_name} (l1={p.l1}) | AI 接触材质推断 |",
        f"| **雨量** | 密度={p.rfdn:.2f} 强度={p.rfin:.2f} | 动态降雨强度映射 |",
        f"| **混合** | 湿度={p.rffc:.2f} Blend={p.spbl:.2f} | 空间湿度与远近比例 |",
        f"| **全局** | 高通={p.glhp:.2f} 低通={p.gllp:.2f} | AI 空间频段雕刻 |"
    ]
    return "\n".join(lines)
