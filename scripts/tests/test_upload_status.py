"""步骤 5 上传状态文案。"""

from pathlib import Path

from gui.upload_status import (
    format_media_rel_path,
    format_step5_upload_label,
    is_uploaded_cfg_entry,
    mp4_path_from_upload_entry,
)


def test_is_uploaded_cfg_entry() -> None:
    assert is_uploaded_cfg_entry(True)
    assert is_uploaded_cfg_entry({"mp4": "/a/b.mp4"})
    assert not is_uploaded_cfg_entry(False)
    assert not is_uploaded_cfg_entry(None)


def test_mp4_path_from_upload_entry() -> None:
    assert mp4_path_from_upload_entry({"mp4": "/x/y.mp4"}) == "/x/y.mp4"
    assert mp4_path_from_upload_entry(True) is None


def test_format_media_rel_path_export(tmp_path: Path) -> None:
    export_root = tmp_path / "export"
    base_root = tmp_path
    mp4 = export_root / "MVI_7004_3h_fhd.mp4"
    mp4.parent.mkdir(parents=True)
    mp4.touch()
    assert format_media_rel_path(mp4, export_root=export_root, base_root=base_root) == (
        "export/MVI_7004_3h_fhd.mp4"
    )


def test_format_step5_upload_label() -> None:
    assert format_step5_upload_label(
        uploaded=True,
        rel_path="export/MVI_7004_3h_fhd.mp4",
    ) == "已上传：export/MVI_7004_3h_fhd.mp4"
    assert format_step5_upload_label(
        uploaded=False,
        rel_path="export/MVI_7004_3h_fhd.mp4",
        custom=True,
    ) == "待上传：export/MVI_7004_3h_fhd.mp4（自定义）"
