"""后验三层：客观闸门判定、断言解析、人工裁决与一致率。"""

import json
from pathlib import Path

import pytest

from scripts.aigc_lab.agent_store import AgentRun
from scripts.aigc_lab.posterior import (
    HUMAN_ADOPT,
    HUMAN_REJECT,
    AssertionVerdict,
    Gate,
    Posterior,
    PosteriorError,
    _parse_verdicts,
    assertions_of,
    load_posterior,
    machine_human_agreement,
    run_gate,
    set_human_verdict,
)
from scripts.aigc_lab.rain_modes import STILL_FLOOR
from scripts.aigc_lab.video_probe import Dynamics


def _run(tmp_path: Path, **meta) -> AgentRun:
    run = AgentRun(kind="t2v", run_id="r1", dir=tmp_path)
    run.save_meta({"rain_mode": "heavy", **meta})
    return run


def _fake_dynamics(monkeypatch, motion=10.0, flicker=0.5, cut_ratio=1.2):
    monkeypatch.setattr(
        "scripts.aigc_lab.posterior.measure_dynamics",
        lambda _p: Dynamics(motion_score=motion, flicker=flicker, cut_ratio=cut_ratio),
    )


def test_gate_passes_when_motion_matches_rain_mode(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    _fake_dynamics(monkeypatch, motion=10.0)
    gate = run_gate(video, rain_mode="heavy")
    assert gate.ok and not gate.issues


def test_gate_flags_near_still_video(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    _fake_dynamics(monkeypatch, motion=STILL_FLOOR - 0.5)
    gate = run_gate(video, rain_mode="heavy")
    assert not gate.ok
    assert "静止" in gate.issues[0]


def test_gate_flags_rain_mode_slip(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    _fake_dynamics(monkeypatch, motion=3.0)
    gate = run_gate(video, rain_mode="storm")
    assert not gate.ok
    assert "雨强不足" in " ".join(gate.issues)


def test_gate_flags_flicker_and_cut(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    _fake_dynamics(monkeypatch, motion=10.0, flicker=9.0, cut_ratio=8.0)
    gate = run_gate(video, rain_mode="heavy")
    joined = " ".join(gate.issues)
    assert "忽明忽暗" in joined and "硬切" in joined


def test_gate_rejects_missing_video(tmp_path):
    with pytest.raises(PosteriorError):
        run_gate(tmp_path / "nope.mp4", rain_mode="heavy")


def test_missing_verdict_defaults_to_no():
    text = json.dumps({"results": [{"index": 1, "verdict": "yes", "confidence": 0.9}]})
    out = _parse_verdicts(text, ["断言一", "断言二"])
    assert [v.verdict for v in out] == ["yes", "no"]
    assert out[1].note


def test_hit_rate_counts_partial_as_half():
    p = Posterior(
        assertions=[
            AssertionVerdict("a", "yes"),
            AssertionVerdict("b", "partial"),
            AssertionVerdict("c", "no"),
        ]
    )
    assert p.hit_rate == pytest.approx(0.5)


def test_human_verdict_persists_and_survives_reload(tmp_path):
    run = _run(tmp_path)
    set_human_verdict(run, HUMAN_REJECT, "雨太小")
    again = load_posterior(run)
    assert again.human == HUMAN_REJECT
    assert again.human_note == "雨太小"


def test_unknown_human_verdict_rejected(tmp_path):
    with pytest.raises(PosteriorError):
        set_human_verdict(_run(tmp_path), "maybe")


def test_agreement_only_counts_judged_runs():
    judged_ok = Posterior(
        gate=Gate(ok=True),
        assertions=[AssertionVerdict("a", "yes")],
        human=HUMAN_ADOPT,
    )
    judged_conflict = Posterior(
        gate=Gate(ok=True),
        assertions=[AssertionVerdict("a", "yes")],
        human=HUMAN_REJECT,
    )
    unjudged = Posterior(gate=Gate(ok=True))
    assert machine_human_agreement([judged_ok, judged_conflict, unjudged]) == (1, 2)


def test_assertions_read_from_meta(tmp_path):
    run = _run(tmp_path, assertions=["画面中没有人物", " ", "屋檐有连续水柱"])
    assert assertions_of(run) == ["画面中没有人物", "屋檐有连续水柱"]
