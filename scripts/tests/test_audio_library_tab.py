"""素材库 boom 宫格：2_impact 同时列出 sounds/ 与 booms/。"""

from pathlib import Path

from gui.audio_library_tab import (
    list_boom_wavs,
    resolve_boom_dirs,
    wav_display_title,
)
from scripts.audio.booms_16bit import booms_16bit_path_for


def test_impact_lists_sounds_then_booms(tmp_path: Path, monkeypatch) -> None:
    layer = tmp_path / "2_impact"
    sounds = layer / "sounds"
    booms = layer / "booms"
    sounds.mkdir(parents=True)
    booms.mkdir(parents=True)
    (sounds / "中雨_水滴.wav").write_bytes(b"s")
    (booms / "QP01 0017 Stream sparkling.wav").write_bytes(b"b")
    (booms / "not-a-wav.txt").write_text("x")

    monkeypatch.setattr(
        "scripts.config.paths.audio_layer_dir",
        lambda layer_id: sounds if layer_id == "2_impact" else tmp_path / layer_id,
    )
    monkeypatch.setattr(
        "gui.audio_library_tab.audio_booms_dir",
        lambda layer_id: booms if layer_id == "2_impact" else tmp_path / layer_id / "booms",
    )

    dirs = resolve_boom_dirs(layer_id="2_impact")
    assert dirs == [sounds, booms]

    wavs = list_boom_wavs("2_impact")
    assert [p.name for p in wavs] == [
        "中雨_水滴.wav",
        "QP01 0017 Stream sparkling.wav",
    ]
    assert wav_display_title(wavs[0], multi_dir=True) == "sounds/中雨_水滴"
    assert wav_display_title(wavs[1], multi_dir=True) == "booms/QP01 0017 Stream sparkling"
    assert booms_16bit_path_for(wavs[0]) is None
    assert booms_16bit_path_for(wavs[1]) == booms.parent / "booms_16bit" / wavs[1].name


def test_rain_only_lists_booms(tmp_path: Path, monkeypatch) -> None:
    booms = tmp_path / "1_rain" / "booms"
    sounds = tmp_path / "1_rain" / "sounds"
    booms.mkdir(parents=True)
    sounds.mkdir(parents=True)
    (booms / "rain.wav").write_bytes(b"b")
    (sounds / "ignored.wav").write_bytes(b"s")

    monkeypatch.setattr(
        "gui.audio_library_tab.audio_booms_dir",
        lambda layer_id: tmp_path / layer_id / "booms",
    )

    wavs = list_boom_wavs("1_rain")
    assert [p.name for p in wavs] == ["rain.wav"]
    assert wav_display_title(wavs[0]) == "rain"
