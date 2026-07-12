from gui.upload_progress import format_transfer_progress, should_refresh_upload_progress


def test_should_refresh_upload_progress_first() -> None:
    assert should_refresh_upload_progress(0, -1) is True


def test_should_refresh_upload_progress_one_percent_step() -> None:
    assert should_refresh_upload_progress(5, 4) is True
    assert should_refresh_upload_progress(5, 5) is False


def test_should_refresh_upload_progress_final_percent() -> None:
    assert should_refresh_upload_progress(95, 94) is True
    assert should_refresh_upload_progress(96, 95) is True
    assert should_refresh_upload_progress(100, 99) is True
    assert should_refresh_upload_progress(100, 100) is False


def test_format_transfer_progress() -> None:
    text = format_transfer_progress(125.0, 50)
    assert text.startswith("Elapsed: 00:02:05")
    assert "Remaining: ~00:02:05" in text
    assert "(50%)" in text

    assert "(…)" in format_transfer_progress(0.0, 0)
