"""离线测试：差异化物料模版选择与 VLM 上下文。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from video_export.metadata_vlm import (  # noqa: E402
    build_metadata_prompt,
    enrich_layer_context,
    select_title_template,
)
from video_export.viral_metadata import (  # noqa: E402
    build_varied_forest_rain_copy,
    scene_rain_from_vlm,
)


SAMPLE_SCENE = {
    "scene_key": "grove_pond",
    "place_zh_short": "林间荷塘",
    "place_en_short": "Forest Lotus Grove",
    "place_zh_long": "林间荷塘雨景",
    "place_en_long": "misty forest grove by a lotus pond",
    "bullet_zh": "🪷 雾气荷塘 · 雨后林木 · 静谧湿地",
    "bullet_en": "🪷 Misty lotus pond · rain-wet forest · quiet wetland",
    "tags_en": ["forest grove", "lotus pond"],
    "thumb_place": "forest grove by a misty lotus pond",
    "misty": True,
}

SAMPLE_META = {
    "duration_s": 10800,
    "duration_human": "3小时",
    "duration_en": "3 hours",
    "width": 3840,
    "height": 2160,
    "fps": 30,
}


class TestMetadataVariation(unittest.TestCase):
    def test_select_title_template_deterministic(self):
        a = select_title_template("MVI_6918")
        b = select_title_template("MVI_6918")
        c = select_title_template("MVI_6919")
        self.assertEqual(a, b)
        self.assertIn(a, {"T1", "T2", "T3", "T4"})
        self.assertIn(c, {"T1", "T2", "T3", "T4"})

    def test_scene_rain_from_vlm_layers(self):
        ctx = enrich_layer_context({"l1_key": 100, "l2_key": 590, "l3_key": 900, "climate_key": "light"})
        phrase = scene_rain_from_vlm(ctx, SAMPLE_SCENE)
        self.assertIsNotNone(phrase)
        self.assertIn("Foliage Lush", phrase)
        self.assertIn("Foliage Dense", phrase)

    def test_different_seeds_produce_different_copy(self):
        copy_a = build_varied_forest_rain_copy(
            SAMPLE_SCENE,
            SAMPLE_META,
            video_seed="MVI_6918",
            show_4k=True,
            vlm_ctx=enrich_layer_context({"l1_key": 100, "l2_key": 590, "l3_key": 900}),
        )
        copy_b = build_varied_forest_rain_copy(
            SAMPLE_SCENE,
            SAMPLE_META,
            video_seed="MVI_6921",
            show_4k=True,
            vlm_ctx=enrich_layer_context({"l1_key": 150, "l2_key": 560, "l3_key": 840}),
        )
        self.assertNotEqual(copy_a["title_en"], copy_b["title_en"])
        self.assertNotEqual(copy_a["description_en"], copy_b["description_en"])

    def test_prompt_contains_template_and_format(self):
        prompt = build_metadata_prompt(
            SAMPLE_SCENE,
            SAMPLE_META,
            enrich_layer_context({"l1_key": 100, "l2_key": 590, "l3_key": 900}),
            video_seed="MVI_6918",
            show_4k=True,
            template_id="T1",
        )
        self.assertIn("T1", prompt)
        self.assertIn("3 Hours 4K Rain Loop ASMR", prompt)
        self.assertIn("NOT black screen", prompt)
        self.assertIn("title_en", prompt)


if __name__ == "__main__":
    unittest.main()
