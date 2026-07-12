from gui.reaper_launch import format_job_progress


def test_format_job_progress_tail() -> None:
    text = format_job_progress(120.0, 99, tail=True)
    assert "99%+" in text
    assert "Remaining: ~…" in text
    assert "00:02:00" in text


def test_format_job_progress_mid() -> None:
    text = format_job_progress(100.0, 50)
    assert "(50%)" in text
    assert "Remaining: ~00:01:40" in text
