import json
import tempfile
import unittest
from pathlib import Path

from scripts.video_upload.material_store import (
    build_material_record,
    load_material_metadata,
    resolve_material_in_dir,
    resolve_material_path_for_scene,
    write_material_json,
)
from scripts.video_upload.parse_youtube_md import parse_youtube_md


SAMPLE_MD = """# YouTube 物料 · `MVI_6999_loop.mp4`

## 中文标题

测试中文标题

## English Title

Test English Title

## English Description

Line one of description.

Line two of description.

## 标签 Tags

Rain, Sleep, ASMR

## 视频信息

| 项 | 值 |
|----|-----|
| 文件 | `MVI_6999_loop.mp4` |
"""


class MaterialStoreTests(unittest.TestCase):
    def test_json_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MVI_6999_material.json"
            record = build_material_record(
                scene_id="MVI_6999",
                video_name="MVI_6999_loop.mp4",
                youtube_copy={
                    "title_zh": "中文",
                    "title_en": "English",
                    "description_zh": "说明",
                    "description_en": "Description body",
                    "tags": ["a", "b"],
                },
                meta={"duration_s": 10800, "width": 3840, "height": 2160},
                thumb_title="RAIN ASMR",
                thumb_subtitle="Forest Pond",
            )
            write_material_json(path, record)
            loaded = load_material_metadata(path)
            self.assertEqual(loaded["title_en"], "English")
            self.assertEqual(loaded["description_en"], "Description body")
            self.assertEqual(loaded["tags"], ["a", "b"])
            self.assertEqual(loaded["video_name"], "MVI_6999_loop.mp4")

    def test_md_fallback_matches_parse_youtube_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "MVI_6999_material.md"
            md_path.write_text(SAMPLE_MD, encoding="utf-8")
            from_md = parse_youtube_md(md_path)
            from_loader = load_material_metadata(md_path)
            self.assertEqual(from_loader["title_en"], from_md["title_en"])
            self.assertEqual(from_loader["description_en"], from_md["description_en"])
            self.assertEqual(from_loader["tags"], from_md["tags"])
            self.assertEqual(from_loader["video_name"], from_md["video_name"])

    def test_resolve_material_path_prefers_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "MVI_6999_material.md").write_text(SAMPLE_MD, encoding="utf-8")
            json_path = root / "MVI_6999_material.json"
            write_material_json(
                json_path,
                {"schema_version": 1, "scene_id": "MVI_6999", "title_en": "JSON wins"},
            )
            resolved = resolve_material_path_for_scene(root, "MVI_6999")
            assert resolved is not None
            self.assertEqual(resolved.suffix, ".json")
            self.assertEqual(load_material_metadata(resolved)["title_en"], "JSON wins")

    def test_resolve_material_in_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "MVI_7000_material.json").write_text(
                json.dumps({"schema_version": 1, "title_en": "ok"}),
                encoding="utf-8",
            )
            found = resolve_material_in_dir(root)
            assert found is not None
            self.assertTrue(found.name.endswith("_material.json"))


if __name__ == "__main__":
    unittest.main()
