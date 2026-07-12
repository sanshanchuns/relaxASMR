"""视觉场景锁定与文案校验测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from video_export.visual_scene import (  # noqa: E402
    _cv_scene_key,
    resolve_visual_scene,
    sanitize_copy_for_visual,
    validate_copy_against_visual,
)


SAMPLE_SCENE = {
    "scene_key": "grove_path",
    "place_en_short": "Rainy Forest Path",
    "place_en_long": "rainy forest grove along a stone path",
    "place_zh_short": "林间小径",
    "place_zh_long": "林间小径雨景",
    "misty": False,
}

SNAP_6989 = Path("/mnt/e/自然之声/to_youtube/material/MVI_6989_snapshot_raw.jpg")


class TestVisualScene(unittest.TestCase):
    def test_cv_scene_key_pond_not_path(self):
        cv = {
            "scene_type": "stream",
            "water_detected": True,
            "water_score": 19.0,
            "green_pct": 30,
            "foliage_density": 40,
        }
        self.assertEqual(_cv_scene_key(cv), "grove_pond")

    def test_validate_rejects_path_when_no_path(self):
        visual = {
            "vlm_visual": {
                "has_path": False,
                "has_water": True,
                "setting_en": "forest pond with lily pads",
                "forbidden_in_copy_en": ["path"],
            }
        }
        bad_copy = {
            "title_en": "Rain on Forest Grove Path",
            "description_en": "rain on a hidden stone path",
            "title_zh": "林间小径雨声",
            "description_zh": "石径雨声",
        }
        hits = validate_copy_against_visual(bad_copy, visual)
        self.assertTrue(hits)

    def test_sanitize_removes_path_terms(self):
        visual = {
            "vlm_visual": {
                "has_path": False,
                "has_water": True,
                "setting_en": "forest pond with lily pads",
                "setting_zh": "林间池塘荷叶",
            }
        }
        bad = {
            "title_en": "Deep Sleep With Forest Grove Path",
            "description_en": "stone path in the forest",
            "title_zh": "林间小径",
            "description_zh": "石板小径",
            "scene_rain_en": "Rain on Forest Path",
        }
        fixed = sanitize_copy_for_visual(bad, visual)
        self.assertNotIn("path", fixed["title_en"].lower())
        self.assertNotIn("小径", fixed["title_zh"])

    @unittest.skipUnless(SNAP_6989.is_file(), "MVI_6989 snapshot not on disk")
    def test_resolve_6989_not_path(self):
        """6989 应为 pond 类场景，不应保留 grove_path。"""
        scene, visual = resolve_visual_scene(
            SNAP_6989,
            SAMPLE_SCENE,
            scene_id="MVI_6989",
            material_dir=SNAP_6989.parent,
            use_vlm_visual=False,
            on_progress=None,
        )
        key = visual.get("resolved_scene_key", scene["scene_key"])
        self.assertNotIn("path", key)
        self.assertIn("pond", key)


if __name__ == "__main__":
    unittest.main()
