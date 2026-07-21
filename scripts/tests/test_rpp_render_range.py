"""RPP 渲染范围修正（Entire Project）。"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "Reaper" / "scripts"))

from generate_subproject import (
    GROUP_FADE_IN_SEC,
    RPP_RENDER_BOUNDS_ENTIRE_PROJECT,
    build_rpp,
    ensure_rpp_full_project_render,
)


def test_ensure_rpp_full_project_render(tmp_path: Path) -> None:
    rpp = tmp_path / "test.rpp"
    rpp.write_text(
        "\n".join(
            [
                "<REAPER_PROJECT",
                "  MAXPROJLEN 1 10800",
                "  RENDER_RANGE 2 0 0 0 1000",
                "  RENDER_PATTERN $project_3h",
                "  SELECTION 10 0",
                "  SELECTION2 10 0",
                ">",
            ]
        ),
        encoding="utf-8",
    )
    assert ensure_rpp_full_project_render(rpp, duration_hours=5.0)
    text = rpp.read_text(encoding="utf-8")
    assert f"RENDER_RANGE {RPP_RENDER_BOUNDS_ENTIRE_PROJECT} 0 0 0 1000" in text
    assert "MAXPROJLEN 1 18000" in text
    assert "RENDER_PATTERN $project_5h" in text
    assert "SELECTION 300 0" in text
    assert "SELECTION2 300 0" in text


def test_build_rpp_uses_entire_project() -> None:
    cfg = {"duration_hours": 2.5, "project_name": "T", "loop_layers": [], "scatter_layers": []}
    rpp = build_rpp(cfg, REPO, REPO / "Reaper" / "Projects" / "Rain", "auto")
    assert f"RENDER_RANGE {RPP_RENDER_BOUNDS_ENTIRE_PROJECT} 0 0 0 1000" in rpp
    assert "SELECTION 300 0" in rpp
    assert "RENDER_PATTERN $project_2.5h" in rpp


def test_build_rpp_group_realimit() -> None:
    cfg = {"duration_hours": 3.0, "project_name": "T", "loop_layers": [], "scatter_layers": []}
    rpp = build_rpp(cfg, REPO, REPO / "Reaper" / "Projects" / "Rain", "auto")
    assert "ReaLimit" in rpp
    assert "realimit.dll" in rpp
    assert "ReaComp" not in rpp
    assert "AwAAAAEAAAAAAAAAAAAAAAAAAAAAAPC/Ag" in rpp
    assert "BYPASS 0 0 0" in rpp.split("NAME Group")[1].split("<TRACK")[0]


def test_build_rpp_1_rain_flat_no_volenv() -> None:
    cfg = {"duration_hours": 3.0, "project_name": "T", "loop_layers": [], "scatter_layers": []}
    rpp = build_rpp(cfg, REPO, REPO / "Reaper" / "Projects" / "Rain", "auto")
    rain_section = rpp.split("NAME 1_rain")[1].split("<TRACK")[0]
    assert "<VOLENV2" not in rain_section


def test_build_rpp_group_fade_in() -> None:
    cfg = {"duration_hours": 3.0, "project_name": "T", "loop_layers": [], "scatter_layers": []}
    rpp = build_rpp(cfg, REPO, REPO / "Reaper" / "Projects" / "Rain", "auto")
    group_section = rpp.split("NAME Group")[1].split("<TRACK")[0]
    assert "PT 0 0 0" in group_section
    assert f"PT {GROUP_FADE_IN_SEC:g} 1 0" in group_section
    assert "PT 10800 1 0" in group_section


def test_build_rpp_2_impact_loops_to_project_length(tmp_path: Path, monkeypatch) -> None:
    wav = tmp_path / "hit.wav"
    wav.write_bytes(b"x")

    monkeypatch.setattr(
        "generate_subproject.resolve_media_asset",
        lambda path_str: Path(path_str),
    )
    monkeypatch.setattr("generate_subproject.media_duration", lambda _p: 12.5)
    monkeypatch.setattr(
        "generate_subproject.stage_media",
        lambda ap, *_args: (str(ap), "WAV", ""),
    )

    cfg = {
        "duration_hours": 3.0,
        "project_name": "T",
        "loop_layers": [
            {"track": 2, "id": "2_impact", "name": "impact", "vol": 0.5, "paths": [str(wav)]},
        ],
        "scatter_layers": [],
    }
    rpp = build_rpp(cfg, REPO, REPO / "Reaper" / "Projects" / "Rain", "absolute")
    impact_section = rpp.split("NAME 2_impact")[1].split("<TRACK")[0]
    assert "LOOP 1" in impact_section
    assert "LENGTH 10800" in impact_section
    assert "POSITION 0" in impact_section
    assert impact_section.count("<ITEM") == 1


def test_build_rpp_3_random_scatter_count(tmp_path: Path, monkeypatch) -> None:
    boom = tmp_path / "wind.wav"
    boom.write_bytes(b"x")

    monkeypatch.setattr(
        "generate_subproject.resolve_media_asset",
        lambda path_str: Path(path_str),
    )
    monkeypatch.setattr("generate_subproject.media_duration", lambda _p: 8.0)
    monkeypatch.setattr(
        "generate_subproject.stage_media",
        lambda ap, *_args: (str(ap), "WAV", ""),
    )

    cfg = {
        "duration_hours": 3.0,
        "project_name": "T",
        "loop_layers": [],
        "scatter_layers": [
            {
                "track": 3,
                "id": "3_random",
                "name": "random",
                "paths": [str(boom)],
                "count": 100,
                "min_gap_min": 5,
                "max_gap_min": 15,
                "randomness": 0.6,
            },
        ],
    }
    rpp = build_rpp(cfg, REPO, REPO / "Reaper" / "Projects" / "Rain", "absolute")
    random_section = rpp.split("NAME 3_random")[1].split("<TRACK")[0]
    assert random_section.count("<ITEM") == 100


def test_ensure_rpp_mix_envelopes(tmp_path: Path) -> None:
    rpp = tmp_path / "mix.rpp"
    rpp.write_text(
        "\n".join(
            [
                "<REAPER_PROJECT",
                "  MAXPROJLEN 1 10800",
                "  <TRACK {G}",
                "    NAME Group",
                "    MAINSEND 1 0",
                "  >",
                "  <TRACK {R}",
                "    NAME 1_rain",
                "    <VOLENV2",
                "      ACT 1 -1",
                "      PT 0 1 0",
                "      PT 10800 0.9 0",
                "    >",
                "  >",
                ">",
            ]
        ),
        encoding="utf-8",
    )
    ensure_rpp_full_project_render(rpp, duration_hours=3.0)
    text = rpp.read_text(encoding="utf-8")
    rain_section = text.split("NAME 1_rain")[1].split("<TRACK")[0]
    group_section = text.split("NAME Group")[1].split("<TRACK")[0]
    assert "<VOLENV2" not in rain_section
    assert "PT 0 0 0" in group_section
    assert f"PT {GROUP_FADE_IN_SEC:g} 1 0" in group_section

