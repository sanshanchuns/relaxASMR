"""三档雨强：id 沿用旧值，语义与运动量区间是新的。"""

from scripts.aigc_lab.rain_modes import (
    RAIN_MODE_ORDER,
    motion_range,
    normalize_rain_mode,
    rain_label,
    rain_mode,
)


def test_ids_unchanged_so_old_runs_need_no_migration():
    assert RAIN_MODE_ORDER == ("light_mod", "heavy", "storm")


def test_labels_remapped_to_drizzle_moderate_downpour():
    assert rain_label("light_mod").startswith("小雨")
    assert rain_label("heavy").startswith("中雨")
    assert rain_label("storm").startswith("暴雨")


def test_chinese_aliases_resolve():
    assert normalize_rain_mode("小雨") == "light_mod"
    assert normalize_rain_mode("中雨") == "heavy"
    assert normalize_rain_mode("暴雨") == "storm"
    assert normalize_rain_mode("drizzle") == "light_mod"
    assert normalize_rain_mode("downpour") == "storm"


def test_unknown_falls_back_to_default():
    assert normalize_rain_mode("") == "heavy"
    assert normalize_rain_mode("玄雨") == "heavy"


def test_motion_ranges_increase_with_rain():
    lo_l, _ = motion_range("light_mod")
    lo_m, _ = motion_range("heavy")
    lo_s, _ = motion_range("storm")
    assert lo_l < lo_m < lo_s


def test_every_mode_has_a_baseline_for_the_llm():
    for mode_id in RAIN_MODE_ORDER:
        assert len(rain_mode(mode_id).baseline) > 20
