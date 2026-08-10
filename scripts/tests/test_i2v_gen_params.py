"""图生 Jimeng 生成参数：Fast 仅 720；2.0/2.5 可 1080。"""

from scripts.aigc_lab.agent_store import (
    model_allows_1080p,
    normalize_i2v_resolution,
    resolve_i2v_gen_params,
    resolutions_for_i2v_model,
)


def test_fast_vip_only_720():
    assert not model_allows_1080p("Seedance 2.0 Fast VIP")
    assert resolutions_for_i2v_model("Seedance 2.0 Fast VIP") == ("720p",)


def test_seedance_20_25_allow_1080():
    assert model_allows_1080p("Seedance 2.0 VIP")
    assert model_allows_1080p("Seedance 2.5")
    assert resolutions_for_i2v_model("Seedance 2.0 VIP") == ("720p", "1080p")


def test_resolve_forces_720_on_fast_even_if_1080_requested():
    out = resolve_i2v_gen_params(
        {"model": "Seedance 2.0 Fast VIP", "resolution": "1080p", "generate_count": 3}
    )
    assert out["model"] == "Seedance 2.0 Fast VIP"
    assert out["resolution"] == "720P"
    assert out["aspect_ratio"] == "16:9"
    assert out["generate_count"] == 3


def test_resolve_keeps_1080_for_seedance_20():
    out = resolve_i2v_gen_params({"model": "Seedance 2.0 VIP", "resolution": "1080p"})
    assert out["resolution"] == "1080P"
    assert normalize_i2v_resolution("720") == "720P"
