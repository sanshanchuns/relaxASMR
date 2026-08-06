"""学习池合入。"""

from __future__ import annotations

from scripts.aigc_lab import tag_pools as tp


def test_merge_into_pools_overwrites_duplicate(tmp_path, monkeypatch) -> None:
    pool_file = tmp_path / "learned_pools.json"
    pool_file.write_text(
        '{"subject": ["已有标签", "其他"], "action": [], '
        '"environment": [], "camera": [], "style": [], "constraints": []}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "pools_path", lambda: pool_file)

    added, updated, pools = tp.merge_into_pools(
        {
            "subject": ["已有标签", "已有标签", "新标签"],
            "action": [],
            "environment": [],
            "camera": [],
            "style": [],
            "constraints": [],
        }
    )

    assert added["subject"] == ["新标签"]
    assert updated["subject"] == ["已有标签"]
    assert pools["subject"] == ["其他", "已有标签", "新标签"]
    assert pools["subject"].count("已有标签") == 1
