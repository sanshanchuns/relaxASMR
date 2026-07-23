"""导出 staging 检测与 finalize。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scripts.config import staging_export as se


def test_base_url_is_network_mount_by_ip() -> None:
    with patch("scripts.config.staging_export.base_url", return_value=Path("/Volumes/192.168.3.128/自然之声/to_youtube")):
        assert se.base_url_is_network_mount() is True


def test_base_url_is_network_mount_local_path() -> None:
    with patch("scripts.config.staging_export.base_url", return_value=Path("/mnt/e/自然之声/to_youtube")):
        with patch("scripts.config.staging_export._filesystem_type", return_value="9p"):
            assert se.base_url_is_network_mount() is False


def test_base_url_is_network_mount_cifs() -> None:
    with patch("scripts.config.staging_export.base_url", return_value=Path("/mnt/nas/to_youtube")):
        with patch("scripts.config.staging_export._filesystem_type", return_value="cifs"):
            assert se.base_url_is_network_mount() is True


def test_use_export_staging_env_override() -> None:
    with patch.dict("os.environ", {"RELAXASMR_STAGING": "1"}):
        assert se.use_export_staging() is True
    with patch.dict("os.environ", {"RELAXASMR_STAGING": "0"}):
        assert se.use_export_staging() is False


def test_use_export_staging_collaboration_machine() -> None:
    with patch("scripts.config.staging_export._read_user_config", return_value={"collaboration_machine": True}):
        assert se.use_export_staging() is True
    with patch("scripts.config.staging_export._read_user_config", return_value={"collaboration_machine": False}):
        assert se.use_export_staging() is False


def test_finalize_export_move(tmp_path: Path) -> None:
    local = tmp_path / "a.wav"
    final = tmp_path / "out" / "a.wav"
    local.write_bytes(b"wav")
    result = se.finalize_export(local, final)
    assert result == final.resolve()
    assert final.is_file()
    assert not local.exists()


def test_patch_and_restore_rpp_render_file(tmp_path: Path) -> None:
    rpp = tmp_path / "test.rpp"
    rpp.write_text(
        "  RENDER_FILE /mnt/e/自然之声/to_youtube/export\n  RENDER_PATTERN $project_3h\n",
        encoding="utf-8",
    )
    original = se.patch_rpp_render_file(rpp, "\\\\wsl.localhost\\Ubuntu\\tmp\\export")
    text = rpp.read_text(encoding="utf-8")
    assert "\\\\wsl.localhost\\Ubuntu\\tmp\\export" in text
    se.restore_rpp_render_file(rpp, original)
    assert rpp.read_text(encoding="utf-8") == (
        "  RENDER_FILE /mnt/e/自然之声/to_youtube/export\n  RENDER_PATTERN $project_3h\n"
    )


def test_stage_input_file(tmp_path: Path) -> None:
    src = tmp_path / "nas" / "mix.wav"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"wav-data")
    with patch("scripts.config.staging_export.local_staging_dir", return_value=tmp_path / "staging"):
        staged = se.stage_input_file(src)
    assert staged.is_file()
    assert staged.read_bytes() == b"wav-data"


def test_unique_wav_paths_from_rpp() -> None:
    text = (
        'FILE "\\\\nas\\a\\one.wav"\n'
        'FILE "\\\\nas\\b\\two.wav"\n'
        'FILE "\\\\nas\\a\\one.wav"\n'
        'FILE "\\\\nas\\c\\vid.mp4"\n'
    )
    assert se.unique_wav_paths_from_rpp(text) == [
        "\\\\nas\\a\\one.wav",
        "\\\\nas\\b\\two.wav",
    ]


def test_patch_rpp_for_local_render_unc_path() -> None:
    text = '  RENDER_FILE \\\\wsl.localhost\\Ubuntu\\mnt\\e\\export\n'
    render_dir = "\\\\wsl.localhost\\Ubuntu\\home\\acele\\workspace\\relaxASMR\\tmp\\export"
    patched = se.patch_rpp_for_local_render(text, wav_replacements={}, render_dir=render_dir)
    assert render_dir in patched
    assert "mnt\\e\\export" not in patched


def test_patch_rpp_for_local_render() -> None:
    text = (
        '  RENDER_FILE \\\\nas\\export\n'
        'FILE "\\\\nas\\audio\\rain.wav"\n'
        'FILE "\\\\nas\\audio\\rain.wav"\n'
    )
    patched = se.patch_rpp_for_local_render(
        text,
        wav_replacements={"\\\\nas\\audio\\rain.wav": "\\\\local\\sources\\rain.wav"},
        render_dir="\\\\local\\out",
    )
    assert 'FILE "\\\\local\\sources\\rain.wav"' in patched
    assert patched.count('FILE "\\\\local\\sources\\rain.wav"') == 2
    assert "RENDER_FILE \\\\local\\out" in patched
    assert "\\\\nas\\audio\\rain.wav" not in patched


def test_stage_upload_mp4(tmp_path: Path) -> None:
    src = tmp_path / "MVI_1000_3h_fhd.mp4"
    src.write_bytes(b"mp4-data")
    with patch("scripts.config.staging_export.local_staging_dir", return_value=tmp_path / "staging"):
        local = se.stage_upload_mp4(src)
    assert local.is_file()
    assert local.read_bytes() == b"mp4-data"
    assert local.parent.name == "upload"


def test_stage_upload_mp4_with_log(tmp_path: Path) -> None:
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x" * 1024)
    logs: list[str] = []
    with patch("scripts.config.staging_export.local_staging_dir", return_value=tmp_path / "staging"):
        se.stage_upload_mp4(src, on_log=logs.append)
    assert any("正在复制" in line for line in logs)
    assert any("复制完成" in line or "硬链" in line for line in logs)


def test_rpp_staging_for_render_restores_rpp(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    reaper_scripts = repo / "Reaper" / "scripts"
    reaper_scripts.mkdir(parents=True)
    (reaper_scripts / "media_paths.py").write_text(
        "def resolve_media_mode(m, r): return 'absolute'\n"
        "def wsl_unc_path(p): return str(p)\n",
        encoding="utf-8",
    )
    (reaper_scripts / "repair_rpp_paths.py").write_text(
        "def resolve_asset_path(old, repo, rpp_dir): "
        "from pathlib import Path; p = Path(rpp_dir) / Path(old).name; "
        "return p if p.is_file() else None\n",
        encoding="utf-8",
    )

    nas = tmp_path / "nas"
    nas.mkdir()
    wav = nas / "rain.wav"
    wav.write_bytes(b"pcm")

    rpp = repo / "Reaper" / "Projects" / "Rain" / "test.rpp"
    rpp.parent.mkdir(parents=True)
    original = (
        '  RENDER_FILE "/nas/export"\n'
        f'FILE "/nas/{wav.name}"\n'
    )
    rpp.write_text(original, encoding="utf-8")

    with patch("scripts.config.staging_export.REPO_ROOT", repo):
        with patch("scripts.config.staging_export.local_staging_dir", return_value=repo / "tmp" / "export"):
            with patch("scripts.config.staging_export.render_dir_for_rpp", return_value="/tmp/export"):
                with patch(
                    "scripts.config.staging_export.staged_path_for_rpp",
                    return_value="/tmp/export/sources/rain.wav",
                ):
                    with se.rpp_staging_for_render(rpp, repo):
                        during = rpp.read_text(encoding="utf-8")
                        assert "/tmp/export/sources/rain.wav" in during
                    assert rpp.read_text(encoding="utf-8") == original
