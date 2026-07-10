"""统一的域知识字典注册表（Domain Registry）。

存放系统中各种模型（如 CLIP、VLM、RAIN VST）使用的基础配置字典，
供 GUI 和分析脚本统一调用，实现业务逻辑解耦。
"""

# ---------------------------------------------------------------------------
# Layer name lookups — real RAIN VST internal IDs
# ---------------------------------------------------------------------------
# Mapping: l_value → (english_name, chinese_name)

DISTANT_NAMES: dict[int, tuple[str, str]] = {
    800: ("Airy Breeze", "空灵微风"),
    810: ("Airy Flow", "空灵气流"),
    930: ("Balanced Flow", "均衡气流"),
    820: ("Balanced Sizzle", "均衡沙沙"),
    830: ("Breezy Hiss", "微风嘶响"),
    840: ("Broadband Shower", "宽频阵雨"),
    850: ("Cold Stream", "寒流雨声"),
    860: ("Dense Stream", "密集雨流"),
    870: ("Distant Veil", "远方雨幕"),
    880: ("Echo River", "河谷回声"),
    890: ("Expansive Shower", "辽阔阵雨"),
    940: ("Flowing Rumble", "流动轰鸣"),
    900: ("Forest Whisper", "森林低语"),
    910: ("Gentle Swish", "轻柔沙响"),
    920: ("Immersive Fuzz", "沉浸雨幕"),
    950: ("Slow Waterfall", "缓瀑雨声"),
    960: ("Spooky Whisper", "幽暗低语"),
    970: ("Strong Hiss", "强烈嘶响"),
    980: ("Thick Shower", "浓密阵雨"),
    990: ("Warm Buzz", "温暖嗡鸣"),
}

SPACE_NAMES: dict[int, tuple[str, str]] = {
    580: ("Building Canopy", "楼宇雨棚"),
    600: ("Building Gutter", "建筑排水槽"),
    500: ("Building Overflow", "建筑溢水"),
    510: ("Building Rooftops", "楼顶雨声"),
    530: ("Foliage Canopy", "树冠"),
    590: ("Foliage Dense", "茂密树林"),
    560: ("Inner Yard", "庭院"),
    570: ("Metal Tanks", "金属储罐"),
    610: ("Street Dense", "密集街区"),
    620: ("Street Drain", "街道排水沟"),
    540: ("Street Tarmac", "柏油路面"),
    630: ("Urban Alley", "城市小巷"),
    520: ("Walls Concrete", "混凝土墙"),
    640: ("Wood Deck", "木平台"),
    550: ("Workshop Yard", "工坊院落"),
}

CLOSE_NAMES: dict[int, tuple[str, str]] = {
    120: ("Brick Diffuse", "砖墙（漫反射）"),
    290: ("Concrete", "混凝土"),
    170: ("Concrete Diffuse", "混凝土（漫反射）"),
    100: ("Foliage Lush", "茂密植被"),
    110: ("Foliage Yielding", "稀疏植被"),
    280: ("Glass Roof", "玻璃屋顶"),
    270: ("Glass Thin", "薄玻璃"),
    260: ("Glass Tonal", "共振玻璃"),
    210: ("Stone Echoing", "回声石墙"),
    130: ("Metal Diffuse", "金属（漫反射）"),
    200: ("Metal Roof", "金属屋顶"),
    250: ("Metal Thin", "薄金属板"),
    220: ("Metal Tonal", "共振金属"),
    240: ("Plastic Roof", "塑料屋顶"),
    160: ("Plastic Thin", "薄塑料板"),
    140: ("Plastic Tonal", "共振塑料"),
    150: ("Water", "水面"),
    230: ("Wood Roof", "木屋顶"),
    190: ("Wood Thin", "薄木板"),
    180: ("Wood Tonal", "共振木材"),
}

CLIMATE_NAMES: dict[int, str] = {
    1: "C1 极轻细雨 近贴",
    2: "C2 小阵雨 中距",
    3: "C3 中雨 均衡",
    4: "C4 中雨 极湿 近贴",
    5: "C5 中雨 极湿 远方",
    6: "C6 大雨 密集 极湿 近贴",
    7: "C7 大雨 密集 极湿 远方",
    8: "C8 中雨 密集 干燥 远方",
    9: "C9 极轻 密集 极湿 近贴"
}
