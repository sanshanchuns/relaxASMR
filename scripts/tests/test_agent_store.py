"""agent_store：断言随 run 落盘；雨档标签走新语义。"""

from pathlib import Path

from scripts.aigc_lab.agent_store import AgentRun, create_agent_run


def test_create_run_stores_assertions_and_subjects(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.aigc_lab.agent_store._runs_dir", lambda _kind: tmp_path
    )
    monkeypatch.setattr(
        "scripts.aigc_lab.agent_store.lab_params",
        lambda _kind: {
            "model": "Seedance 2.0 Fast VIP",
            "aspect_ratio": "16:9",
            "resolution": "720P",
            "duration_sec": 6,
        },
    )
    run = create_agent_run(
        "t2v",
        prompt="雨水沿屋檐连成水柱砸进积水",
        rain_mode="storm",
        assertions=["画面中没有人物", "屋檐有连续水柱"],
        subjects=["木屋"],
    )
    assert run.dir.parent == tmp_path
    assert run.prompt.startswith("雨水沿屋檐")
    assert run.meta["assertions"] == ["画面中没有人物", "屋檐有连续水柱"]
    assert run.meta["subjects"] == ["木屋"]
    assert run.meta["rain_label"].startswith("暴雨")
    assert run.meta["duration_sec"] == 6
    assert (run.dir / "prompt.txt").is_file()


def test_format_run_line_shows_human_verdict(tmp_path):
    from gui.aigc_flow_tab import _format_run_line

    run = AgentRun(kind="t2v", run_id="r1", dir=tmp_path)
    run.meta = {"rain_mode": "heavy"}
    run.posterior = {"human": "adopt", "gate": {"ok": True}}
    line = _format_run_line(run)
    assert "✓" in line
    assert "中雨" in line
