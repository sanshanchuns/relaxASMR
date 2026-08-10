"""Seedance 手册存档。"""

from pathlib import Path

from scripts.aigc_lab.seedance_handbook import (
    append_handbook_qa,
    existing_question_fps,
    question_fingerprint,
    seedance_handbook_path,
)


def test_append_handbook_dedupe(tmp_path, monkeypatch):
    path = tmp_path / "Seedance2.0手册.md"
    monkeypatch.setattr(
        "scripts.aigc_lab.seedance_handbook.seedance_handbook_path",
        lambda: path,
    )
    assert append_handbook_qa(
        question="为什么还要浅景深？",
        answer="因为要标明光学虚化而非雨雾。",
        title="浅景深",
    )
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "浅景深" in text
    assert "光学虚化" in text
    # 同题不重复
    assert not append_handbook_qa(
        question="为什么还要浅景深？",
        answer="另一版答案",
    )
    assert path.read_text(encoding="utf-8").count("**问：**") == 1
    fps = existing_question_fps(path)
    assert question_fingerprint("为什么还要浅景深？") in fps


def test_seedance_handbook_path_under_aigc():
    p = seedance_handbook_path()
    assert p.name == "Seedance2.0手册.md"
    assert p.parent.name == "aigc" or "aigc" in str(p)
