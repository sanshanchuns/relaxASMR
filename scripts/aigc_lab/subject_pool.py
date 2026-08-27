"""受雨主体候选池。

产品范围是「雨 ASMR」，不限于纯自然：小船、木屋这类人造物同样是好主体，
它们的硬表面能给出自然植被给不了的雨声与视觉落点（屋檐水柱、船板积水）。

这里只是给 GUI 提供快速勾选项，用户随时可以自己敲关键词。
"""

from __future__ import annotations

#: (分组名, 主体列表)
SUBJECT_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "水面",
        ("池塘", "溪流浅滩", "水洼", "荷叶水面", "苔石溪涧"),
    ),
    (
        "植物",
        ("大叶芭蕉", "蕨类丛", "竹林", "针叶枝条", "苔藓岩壁", "野草地"),
    ),
    (
        "人造物",
        ("小船", "木屋屋檐", "木栈道", "旧木窗", "瓦片屋顶", "石阶", "铁皮雨棚", "帆布顶棚"),
    ),
    (
        "地面",
        ("落叶层", "泥土小径", "碎石地", "青石板路"),
    ),
)

ALL_SUBJECTS: tuple[str, ...] = tuple(
    s for _group, items in SUBJECT_GROUPS for s in items
)


def split_subjects(text: str) -> list[str]:
    """把用户输入的一行关键词拆成主体列表（顿号/逗号/空格分隔）。"""
    raw = str(text or "")
    for sep in ("、", "，", ",", ";", "；", "/", "|", "\n", "\t"):
        raw = raw.replace(sep, " ")
    seen: set[str] = set()
    out: list[str] = []
    for part in raw.split(" "):
        item = part.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def format_subjects(subjects: list[str] | tuple[str, ...] | None) -> str:
    items = [str(s).strip() for s in (subjects or []) if str(s).strip()]
    return "、".join(items)
