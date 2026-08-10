"""Agent GUI session 持久化单测。"""

from __future__ import annotations

import json

from scripts.aigc_lab.agent_loop import loop_result_from_review_json
from scripts.aigc_lab.agent_session import (
    empty_session,
    load_agent_session,
    save_agent_session,
    session_path,
)
from scripts.aigc_lab.prompt_atoms import SLOT_ORDER


def test_agent_session_roundtrip(tmp_path, monkeypatch) -> None:
    from scripts.config import paths

    root = tmp_path / "aigc"
    t2v = root / "agent_t2v_lab"
    t2v.mkdir(parents=True)
    monkeypatch.setattr(paths, "agent_t2v_lab_dir", lambda: t2v)

    data = empty_session()
    data["rain_mode"] = "storm"
    data["scene_keywords"] = "雨林"
    data["ref_image"] = "/tmp/ref.png"
    data["slots"] = {k: [f"{k}_tag"] for k in SLOT_ORDER}
    data["selected_run_id"] = "run_001"
    data["status"] = "审核通过 · 可确认生成"
    data["loop_review"] = {
        "agreed": True,
        "rounds": [
            {
                "round": 1,
                "source": "jimeng_agent",
                "draft_slots": data["slots"],
                "draft_raw": "{}",
                "review": {"verdict": "ok"},
            }
        ],
        "final_slots": data["slots"],
        "unresolved_conflicts": [],
    }
    data["confirmed"] = False

    save_agent_session("t2v", data)
    loaded = load_agent_session("t2v")
    assert loaded is not None
    assert loaded["rain_mode"] == "storm"
    assert loaded["selected_run_id"] == "run_001"
    assert loaded["loop_review"]["agreed"] is True
    assert loaded["confirmed"] is False
    assert session_path("t2v").is_file()


def test_loop_result_from_review_json() -> None:
    slots = {k: ["a"] for k in SLOT_ORDER}
    review = {
        "agreed": False,
        "rounds": [
            {
                "round": 2,
                "source": "revise",
                "draft_slots": slots,
                "draft_raw": "raw",
                "review": {"verdict": "revise"},
            }
        ],
        "final_slots": slots,
        "unresolved_conflicts": [{"slot": "主体", "tag": "x"}],
    }
    result = loop_result_from_review_json(review)
    assert result is not None
    assert result.agreed is False
    assert len(result.rounds) == 1
    assert result.rounds[0].round == 2
    assert result.unresolved_conflicts[0]["tag"] == "x"
