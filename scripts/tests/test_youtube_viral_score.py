"""youtube_viral_score payload 解析（mock，无网络）。"""

from scripts.aigc_lab.youtube_viral_score import _parse


def test_parse_viral_json():
    raw = """{"score":72,"verdict":"maybe","dimensions":{"rain_realism":70},"notes":["ok"]}"""
    data = _parse(raw)
    assert data["score"] == 72
    assert data["verdict"] == "maybe"
    assert data["dimensions"]["rain_realism"] == 70


def test_parse_viral_invalid():
    data = _parse("not json")
    assert data["score"] == 0
    assert data["verdict"] == "weak"
