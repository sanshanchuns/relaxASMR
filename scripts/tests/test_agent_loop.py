"""agent_loop：图生审核、JSON 解析与冲突 UI 映射。"""

from scripts.aigc_lab.agent_loop import (
    ConsensusComparison,
    ReviewIssue,
    ReviewResult,
    build_draft_prompt,
    comparison_to_ui,
    conflict_tag_set,
    parse_draft_json,
    parse_slots_json,
    review_result_to_ui,
    run_agent_review_loop,
    run_i2v_consensus_loop,
)
from scripts.aigc_lab.prompt_atoms import apply_i2v_fixed_slots
from scripts.aigc_lab.youtube_competitor_pool import series_goal_for_rain_mode


def test_parse_slots_json_basic():
    slots = parse_slots_json(
        '{"subject":["香蕉树"],"action":["雨打叶片"],'
        '"environment":["林下"],"camera":["固定镜头"],'
        '"style":["写实"],"constraints":["无人物"]}'
    )
    assert slots["subject"] == ["香蕉树"]
    assert slots["camera"] == ["固定镜头"]


def test_parse_draft_json_rain_mode():
    rain, slots = parse_draft_json(
        '{"rain_mode":"storm","subject":["树"],"action":["雨"],'
        '"environment":["林"],"camera":["固定"],"style":["写实"],"constraints":["无"]}'
    )
    assert rain == "storm"
    assert slots["subject"] == ["树"]


def test_parse_slots_json_zh_keys_and_fence():
    text = """```json
{"主体":["树干"],"动作":"水珠滚落","环境":["雾气"],"镜头":["平视"],"风格":["documentary"],"约束":["无字幕"]}
```"""
    slots = parse_slots_json(text)
    assert slots["subject"] == ["树干"]
    assert slots["action"] == ["水珠滚落"]


def test_conflict_tag_set():
    fails = conflict_tag_set(
        [{"slot": "action", "tag": "剧烈摆动"}, {"slot": "", "tag": "香蕉树"}]
    )
    assert "剧烈摆动" in fails["action"]
    assert "香蕉树" in fails["subject"]


def test_comparison_to_ui_missing_slot():
    cmp = ConsensusComparison(
        agreed=False,
        missing=[{"slot": "camera", "side": "gemini", "description": "缺少构图异构描述"}],
        conflict_tags=[{"slot": "action", "tag": "模糊动作", "side": "jimeng"}],
    )
    jimeng = {
        "subject": ["叶"],
        "action": ["模糊动作"],
        "environment": ["林"],
        "camera": [],
        "style": ["写实"],
        "constraints": ["无"],
    }
    conflicts, fail_slots = comparison_to_ui(cmp, jimeng)
    assert conflicts == [{"slot": "action", "tag": "模糊动作"}]
    assert "camera" in fail_slots


def test_review_result_to_ui_missing_specific_change():
    review = ReviewResult(
        verdict="revise",
        missing=["camera：缺少针对参考图枝条方向的具体异构修改"],
        issues=[ReviewIssue(slot="camera", tag="", problem="未写镜像或斜向插入")],
    )
    slots = {
        "subject": ["阔叶"],
        "action": ["雨打"],
        "environment": ["林"],
        "camera": ["固定镜头"],
        "style": ["写实"],
        "constraints": ["勿复制构图"],
    }
    conflicts, fail_slots = review_result_to_ui(review, slots)
    assert "camera" in fail_slots


def test_run_loop_mock_agree_round1():
    draft = (
        '{"subject":["香蕉树"],"action":["雨打叶片"],'
        '"environment":["林下"],"camera":["固定"],'
        '"style":["写实"],"constraints":["无人物"]}'
    )

    def jimeng(prompt, images):
        del prompt, images
        return draft

    def review(slots):
        del slots
        return ReviewResult(verdict="pass")

    result = run_agent_review_loop(
        kind="t2v",
        rain_mode="storm",
        scene_keywords="雨林",
        jimeng_fn=jimeng,
        review_fn=review,
    )
    assert result.agreed
    assert len(result.rounds) == 1
    assert result.slots["subject"] == ["香蕉树"]


def test_run_loop_mock_three_rounds_conflict():
    def jimeng(prompt, images):
        del images, prompt
        return (
            '{"subject":["A"],"action":["动"],"environment":["环"],'
            '"camera":["镜"],"style":["风"],"constraints":["约"]}'
        )

    def review(slots):
        del slots
        return ReviewResult(
            verdict="revise",
            issues=[ReviewIssue(slot="action", tag="动", problem="太含糊")],
            conflict_tags=[{"slot": "action", "tag": "动"}],
        )

    result = run_agent_review_loop(
        kind="t2v",
        rain_mode="heavy",
        scene_keywords="池塘",
        jimeng_fn=jimeng,
        review_fn=review,
    )
    assert not result.agreed
    assert len(result.rounds) == 3
    assert result.unresolved_conflicts
    assert "动" in conflict_tag_set(result.unresolved_conflicts)["action"]


def test_build_draft_contains_rain():
    text = build_draft_prompt(rain_mode="storm", scene_keywords="原始热带雨林")
    assert "暴雨" in text
    assert "原始热带雨林" in text


def test_build_draft_i2v_rain_from_image():
    text = build_draft_prompt(
        rain_mode="storm",
        scene_keywords="",
        kind="i2v",
    )
    assert "雨ASMR图生" in text
    assert "rain_mode" in text
    assert "heavy" in text
    assert "共享规则" not in text
    assert len(text) < 500


def test_apply_i2v_fixed_slots_passthrough():
    raw = {
        "subject": ["森林小径"],
        "action": ["细雨打叶"],
        "environment": ["密林"],
        "camera": ["平视", "背景虚化"],
        "style": ["documentary"],
        "constraints": ["无字幕"],
    }
    slots = apply_i2v_fixed_slots(raw)
    assert slots == raw


def test_i2v_review_agree_round1():
    draft = (
        '{"rain_mode":"heavy","subject":["小径"],"action":["雨打"],"environment":["林"],'
        '"camera":["焦点在前景叶片","枝条从左向右伸展"],"style":["写实"],"constraints":["无字幕"]}'
    )

    def jimeng(prompt, images):
        del prompt, images
        return draft

    def review(slots, rain):
        del slots, rain
        return ReviewResult(verdict="pass")

    result = run_i2v_consensus_loop(
        jimeng_fn=jimeng,
        review_fn=review,
    )
    assert result.agreed
    assert result.rain_mode == "heavy"
    assert result.series_goal == series_goal_for_rain_mode("heavy")
    assert len(result.rounds) == 1
    assert result.rounds[0].review.get("verdict") == "pass"


def test_i2v_review_three_rounds_use_jimeng_final():
    draft_a = (
        '{"rain_mode":"heavy","subject":["A"],"action":["动"],"environment":["环"],'
        '"camera":["镜"],"style":["风"],"constraints":["约"]}'
    )
    n = {"i": 0}

    def jimeng(prompt, images):
        del prompt, images
        n["i"] += 1
        return draft_a

    def review(slots, rain):
        del slots, rain
        return ReviewResult(
            verdict="revise",
            issues=[ReviewIssue(slot="action", tag="动", problem="太含糊")],
            conflict_tags=[{"slot": "action", "tag": "动"}],
            missing=["camera：缺少针对参考图的具体异构修改"],
        )

    result = run_i2v_consensus_loop(
        jimeng_fn=jimeng,
        review_fn=review,
    )
    assert not result.agreed
    assert n["i"] == 3
    assert result.slots["subject"] == ["A"]
    assert "动" in conflict_tag_set(result.unresolved_conflicts)["action"]
    assert "camera" in result.fail_slots


def test_i2v_opens_jimeng_browser_once(monkeypatch):
    """三轮审核复用同一 JimengAgentSession，不反复开关浏览器。"""
    draft = (
        '{"rain_mode":"heavy","subject":["A"],"action":["动"],"environment":["环"],'
        '"camera":["镜"],"style":["风"],"constraints":["约"]}'
    )
    opens = {"n": 0}
    chats = {"n": 0}

    class FakeSession:
        def __enter__(self):
            opens["n"] += 1
            return self

        def __exit__(self, *args):
            return None

        def chat(self, prompt, images=None, **kwargs):
            del prompt, images, kwargs
            chats["n"] += 1
            return draft

    monkeypatch.setattr(
        "scripts.aigc_lab.agent_loop._open_jimeng_session",
        lambda **_kw: FakeSession(),
    )

    def review(slots, rain):
        del slots, rain
        return ReviewResult(
            verdict="revise",
            issues=[ReviewIssue(slot="action", tag="动", problem="太含糊")],
            conflict_tags=[{"slot": "action", "tag": "动"}],
        )

    result = run_i2v_consensus_loop(review_fn=review)
    assert not result.agreed
    assert opens["n"] == 1
    assert chats["n"] == 3


def test_i2v_handbook_questions_archived():
    draft = (
        '{"rain_mode":"heavy","subject":["叶"],"action":["雨打"],"environment":["林"],'
        '"camera":["焦点对准前景叶片","背景虚化","浅景深"],"style":["写实"],"constraints":["无"]}'
    )
    archived: list[dict] = []

    def jimeng(prompt, images):
        del images
        if "answers JSON" in prompt or "Gemini 疑问" in prompt:
            return (
                '{"answers":[{"question":"为什么还要浅景深？",'
                '"answer":"标明光学虚化而非雨雾","title":"浅景深"}]}'
            )
        return draft

    def review(slots, rain):
        del slots, rain
        return ReviewResult(
            verdict="pass",
            questions=["为什么还要浅景深？"],
        )

    def handbook(questions, slots, rain):
        del slots, rain
        archived.extend({"question": q, "answer": "标明光学虚化而非雨雾", "title": "浅景深"} for q in questions)
        return list(archived)

    result = run_i2v_consensus_loop(
        jimeng_fn=jimeng,
        review_fn=review,
        handbook_fn=handbook,
    )
    assert result.agreed
    assert archived
    assert result.handbook_qa
    assert "浅景深" in result.handbook_qa[0].get("title", "")


def test_parse_handbook_answers_json():
    from scripts.aigc_lab.agent_loop import parse_handbook_answers_json

    text = (
        '{"answers":[{"question":"为什么还要浅景深？",'
        '"answer":"光学虚化","title":"浅景深"}]}'
    )
    out = parse_handbook_answers_json(text, questions=["为什么还要浅景深？"])
    assert len(out) == 1
    assert out[0]["answer"] == "光学虚化"


def test_i2v_revise_prompt_includes_review_issues():
    review = ReviewResult(
        verdict="revise",
        issues=[
            ReviewIssue(
                slot="camera",
                tag="固定镜头",
                problem="未写相对参考图枝条方向的具体异构（如镜像为左→右）",
            )
        ],
        missing=["camera：缺少具体构图修改"],
    )
    text = build_draft_prompt(
        rain_mode="heavy",
        kind="i2v",
        prior_slots={
            "subject": ["叶"],
            "action": [],
            "environment": [],
            "camera": ["固定镜头"],
            "style": [],
            "constraints": [],
        },
        prior_rain_mode="heavy",
        prior_issues=review,
    )
    assert "审核问题" in text or "修订" in text
    assert "镜像" in text
    assert "固定镜头" in text
