from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REAPER_SCRIPTS = REPO / "Reaper" / "scripts"
if str(REAPER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(REAPER_SCRIPTS))

from media_paths import wsl_unc_path  # noqa: E402


def test_wsl_unc_path_uses_drive_for_mnt_by_default(monkeypatch) -> None:
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.delenv("RELAXASMR_MEDIA_WIN_DRIVE", raising=False)
    p = Path("/mnt/e/自然之声/to_youtube/audio/1_rain/booms/test.wav")
    assert wsl_unc_path(p) == (
        "E:\\自然之声\\to_youtube\\audio\\1_rain\\booms\\test.wav"
    )


def test_wsl_unc_path_can_force_unc_for_mnt(monkeypatch) -> None:
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setenv("RELAXASMR_MEDIA_WIN_DRIVE", "0")
    p = Path("/mnt/e/自然之声/to_youtube/test.mp4")
    assert wsl_unc_path(p) == (
        "\\\\wsl.localhost\\Ubuntu\\mnt\\e\\自然之声\\to_youtube\\test.mp4"
    )


def test_wsl_unc_path_home_uses_unc(monkeypatch) -> None:
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.delenv("RELAXASMR_MEDIA_WIN_DRIVE", raising=False)
    p = Path("/home/acele/workspace/relaxASMR/Reaper/Projects/Rain/MVI_6973.rpp")
    out = wsl_unc_path(p)
    assert out.startswith("\\\\wsl.localhost\\Ubuntu\\home\\acele\\")
