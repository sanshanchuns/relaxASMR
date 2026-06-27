"""声源单一性检测：文件名含 ≥3 类独立声源或混合关键词 → 拒绝入库。"""

from __future__ import annotations

import re

SOUND_TYPE_PATTERNS: list[tuple[str, str]] = [
    ("rain", r"rain|drizzle|downpour|shower|毛毛雨|小雨|大雨|暴雨|下雨|雨声"),
    ("wind", r"\bwind\b|breeze|gust|微风|风声|howling"),
    ("bird", r"\bbird\b|robin|sparrow|\bowl\b|crow|woodpecker|鸟鸣|鸟叫|鸟声"),
    ("water_flow", r"stream|creek|river|brook|flowing water|流水|溪流|河流|小河"),
    ("water_drip", r"drip|dripping|滴水"),
    ("water_lake", r"lake|pond|wetland|湖水|池塘|湿地"),
    ("ocean", r"ocean|surf|wave|海浪|潮汐"),
    ("forest", r"forest|jungle|woodland|树林|森林|山林"),
    ("insect", r"cricket|cicada|katydid|\binsect\b|蟋蟀|蝉鸣|虫鸣|知了"),
    ("frog", r"frog|蛙鸣|青蛙"),
    ("fire", r"fire|crackle|fireplace|篝火|炉火|噼啪"),
    ("thunder", r"thunder|雷声|打雷"),
    ("traffic", r"traffic|highway|car pass|车流|城市|交通|urban"),
    ("human", r"voice|crowd|keyboard|clock|人群|说话"),
    ("leaves", r"leaves|foliage|vegetation|树叶|落叶|植被"),
    ("grass", r"grass|lawn|草坪|草地"),
    ("snow", r"snow|雪"),
    ("animal", r"deer|fox|wolf|horse|cow|sheep|dog|动物"),
]

MIX_REJECT_PATTERNS: list[str] = [
    r"\bmix\b",
    r"mixed",
    r"blend",
    r"compilation",
    r"montage",
    r"collage",
    r"various",
    r"assorted",
    r"multiple",
    r"background mix",
    r"ambience mix",
    r"nature mix",
    r"soundscape",
    r"混合",
    r"多种",
    r"综合",
    r"大全",
    r"合集",
    r"氛围混合",
    r"背景声混合",
    r"环境混合",
    r"大自然.*混合",
    r"混合背景",
]


def normalize(text: str) -> str:
    return re.sub(r"[_\s,，、]+", " ", text.lower())


def sound_type_tags(name: str) -> set[str]:
    n = normalize(name)
    found: set[str] = set()
    for tag, pat in SOUND_TYPE_PATTERNS:
        if re.search(pat, n, re.I):
            found.add(tag)
    return found


def independent_buckets(tags: set[str]) -> set[str]:
    """
    合并同场景附属标签：有 rain 时 forest/leaves/grass 视为雨景附属，不单独计类。
    """
    buckets: set[str] = set()
    has_rain = "rain" in tags

    for t in tags:
        if t == "rain":
            buckets.add("rain")
        elif t == "thunder":
            buckets.add("storm")
        elif t in ("bird", "insect", "frog", "animal"):
            buckets.add("wildlife")
        elif t in ("water_flow", "water_drip", "water_lake", "ocean"):
            buckets.add("water")
        elif t == "wind":
            buckets.add("wind")
        elif t in ("forest", "leaves", "grass"):
            if not has_rain:
                buckets.add("environment")
        elif t in ("fire", "human", "traffic"):
            buckets.add("human")
    return buckets


def purity_check(name: str, max_buckets: int = 2) -> tuple[bool, str]:
    """
    单一性：独立声源桶 ≤ max_buckets（默认 2，即 ≥3 类拒绝）。
    """
    n = normalize(name)
    for pat in MIX_REJECT_PATTERNS:
        if re.search(pat, n, re.I):
            return False, f"mix-keyword: {pat}"

    tags = sound_type_tags(name)
    buckets = independent_buckets(tags)
    if len(buckets) > max_buckets:
        detail = f"buckets({len(buckets)}): {', '.join(sorted(buckets))}"
        if tags:
            detail += f" [tags: {', '.join(sorted(tags))}]"
        return False, detail
    return True, ""


def is_pure_single_source(name: str) -> bool:
    ok, _ = purity_check(name)
    return ok
