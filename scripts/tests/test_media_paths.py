from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
REAPER_SCRIPTS = REPO / "Reaper" / "scripts"
if str(REAPER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(REAPER_SCRIPTS))

from media_paths import wsl_unc_path  # noqa: E402


def test_wsl_unc_path_uses_drive_for_drvfs_mnt(monkeypatch) -> None:
    """本机盘符挂载（非 CIFS）仍写成 E:\\..."""
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.delenv("RELAXASMR_MEDIA_WIN_DRIVE", raising=False)
    p = Path("/mnt/e/自然之声/to_youtube/audio/1_rain/booms/test.wav")
    with patch("media_paths._cifs_windows_unc", return_value=None):
        assert wsl_unc_path(p) == (
            "E:\\自然之声\\to_youtube\\audio\\1_rain\\booms\\test.wav"
        )


def test_wsl_unc_path_cifs_mnt_uses_nas_unc(monkeypatch) -> None:
    """协作机：/mnt/e 为 CIFS 时写成 \\\\192.168.3.128\\e\\...，不能写 E:\\"""
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.delenv("RELAXASMR_MEDIA_WIN_DRIVE", raising=False)
    p = Path("/mnt/e/自然之声/to_youtube/audio/1_rain/booms/BI24.湿地雨林.wav")
    # /proc/mounts 格式（不是 mount 命令输出）
    mounts = (
        "C:\\ /mnt/c 9p rw,noatime 0 0\n"
        "//192.168.3.128/e /mnt/e cifs rw,relatime 0 0\n"
    )
    with patch("media_paths.Path.read_text", return_value=mounts):
        with patch.object(Path, "resolve", return_value=p):
            out = wsl_unc_path(p)
    assert out == (
        "\\\\192.168.3.128\\e\\自然之声\\to_youtube\\audio\\1_rain\\booms\\BI24.湿地雨林.wav"
    )
    assert not out.startswith("E:")


def test_wsl_unc_path_can_force_unc_for_mnt(monkeypatch) -> None:
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setenv("RELAXASMR_MEDIA_WIN_DRIVE", "0")
    p = Path("/mnt/e/自然之声/to_youtube/test.mp4")
    with patch("media_paths._cifs_windows_unc", return_value=None):
        assert wsl_unc_path(p) == (
            "\\\\wsl.localhost\\Ubuntu\\mnt\\e\\自然之声\\to_youtube\\test.mp4"
        )


def test_wsl_unc_path_home_uses_unc(monkeypatch) -> None:
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.delenv("RELAXASMR_MEDIA_WIN_DRIVE", raising=False)
    p = Path("/home/acele/workspace/relaxASMR/Reaper/Projects/Rain/MVI_6973.rpp")
    out = wsl_unc_path(p)
    assert out.startswith("\\\\wsl.localhost\\Ubuntu\\home\\acele\\")
