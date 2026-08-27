"""主体关键词拆分与常用池。"""

from scripts.aigc_lab.subject_pool import (
    ALL_SUBJECTS,
    SUBJECT_GROUPS,
    format_subjects,
    split_subjects,
)


def test_split_handles_mixed_separators():
    assert split_subjects("小船、木屋 池塘,大叶子") == ["小船", "木屋", "池塘", "大叶子"]


def test_split_dedupes_and_skips_blanks():
    assert split_subjects("木屋，木屋、  ") == ["木屋"]


def test_format_roundtrip():
    items = split_subjects("小船、木屋")
    assert format_subjects(items) == "小船、木屋"


def test_pool_includes_man_made():
    names = set(ALL_SUBJECTS)
    assert {"小船", "木屋屋檐", "池塘", "大叶芭蕉"} <= names
    groups = {g for g, _ in SUBJECT_GROUPS}
    assert "人造物" in groups
