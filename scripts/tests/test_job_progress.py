from gui.job_progress import parse_progress_pct
from gui.reaper_launch import format_job_progress


def test_format_job_progress_unknown() -> None:
    text = format_job_progress(12.0, 0)
    assert "Remaining: ~…" in text
    assert "(…)" in text


def test_format_job_progress_mid() -> None:
    text = format_job_progress(60.0, 50)
    assert "Elapsed: 00:01:00" in text
    assert "Remaining: ~00:01:00" in text
    assert "(50%)" in text


def test_parse_progress_pct() -> None:
    assert parse_progress_pct("Elapsed: 00:16:46  Remaining: ~01:43:03  (14%)") == 14
    assert parse_progress_pct("Elapsed: 00:01:00  Remaining: ~00:00:05  (99%+)") == 99
    assert parse_progress_pct("no percent") is None
