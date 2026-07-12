"""步骤 2 rain clip/vlm 候选匹配。"""

from __future__ import annotations

from pathlib import Path

from gui.core_controller import get_matches_for_keys
from scripts.config.common_constants import (
    close_preset_tag,
    format_rain_preset_display_name,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


def test_close_preset_tag_maps_wood_thin_to_wood_roof() -> None:
    assert close_preset_tag(190) == "WoodRoof"


def test_close_preset_tag_does_not_map_plastic_to_foliage() -> None:
    assert close_preset_tag(240) == "PlasticRoof"


def test_get_matches_requires_full_three_layer_match(tmp_path: Path) -> None:
    partial = tmp_path / "14_GentleSwish_FoliageDense_Concrete_C2_极轻密集_近贴.wav"
    _touch(partial)
    assert get_matches_for_keys(910, 590, 190, [partial]) == []


def test_get_matches_returns_empty_when_no_hit(tmp_path: Path) -> None:
    wrong = tmp_path / "01_AiryBreeze_FoliageCanopy_Concrete_C5_中雨极湿_近贴.wav"
    _touch(wrong)
    assert get_matches_for_keys(910, 590, 190, [wrong]) == []


def test_format_rain_preset_display_name() -> None:
    stem = "14_GentleSwish_FoliageDense_WoodRoof_C2_极轻密集_近贴"
    text = format_rain_preset_display_name(stem)
    assert "GentleSwish / FoliageDense / WoodRoof" in text
    assert "C2" in text


def test_get_matches_for_keys_dense_forest_wood_planks(tmp_path: Path) -> None:
    wrong = tmp_path / "01_AiryBreeze_FoliageCanopy_Concrete_C5_中雨极湿_近贴.wav"
    right = tmp_path / "14_GentleSwish_FoliageDense_WoodRoof_C2_极轻密集_近贴.wav"
    alt = tmp_path / "14_GentleSwish_FoliageDense_WoodRoof_C3_小阵雨_中距.wav"
    _touch(wrong)
    _touch(right)
    _touch(alt)

    matches = get_matches_for_keys(910, 590, 190, [wrong, right, alt])
    stems = [Path(m["wav"]).stem for m in matches]

    assert stems[0] == right.stem
    assert all("FoliageDense" in s for s in stems)
    assert all("WoodRoof" in s for s in stems)
    assert all("GentleSwish" in s for s in stems)
    assert wrong.stem not in stems
