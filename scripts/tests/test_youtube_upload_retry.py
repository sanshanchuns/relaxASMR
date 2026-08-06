"""YouTube 大文件上传重试判定。"""

from __future__ import annotations

import ssl

from scripts.video_upload.youtube_upload import (
    _configure_resumable_upload_http,
    _is_retryable_upload_error,
)


def test_retryable_ssl_eof() -> None:
    err = ssl.SSLError("EOF occurred in violation of protocol (_ssl.c:2437)")
    assert _is_retryable_upload_error(err)


def test_retryable_oserror_message() -> None:
    err = OSError("EOF occurred in violation of protocol (_ssl.c:2437)")
    assert _is_retryable_upload_error(err)


def test_non_retryable_value_error() -> None:
    assert not _is_retryable_upload_error(ValueError("bad title"))


def test_configure_resumable_upload_http_excludes_308() -> None:
    import httplib2

    http = httplib2.Http()
    _configure_resumable_upload_http(http)
    assert 308 not in http.redirect_codes
    assert 301 in http.redirect_codes


def test_verify_uploaded_video_accepts_uploaded() -> None:
    from unittest.mock import MagicMock

    from scripts.video_upload.youtube_upload import verify_uploaded_video

    service = MagicMock()
    service.videos.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "status": {"uploadStatus": "uploaded"},
                "contentDetails": {"duration": "PT3H1S"},
                "processingDetails": {"processingStatus": "processing"},
            }
        ]
    }
    item = verify_uploaded_video(service, "abc", attempts=1, delay_sec=0)
    assert item["status"]["uploadStatus"] == "uploaded"


def test_verify_uploaded_video_rejects_stuck_draft() -> None:
    from unittest.mock import MagicMock

    import pytest

    from scripts.video_upload.youtube_upload import verify_uploaded_video

    service = MagicMock()
    service.videos.return_value.list.return_value.execute.return_value = {
        "items": [{"status": {"uploadStatus": "deleted"}}]
    }
    with pytest.raises(RuntimeError, match="未确认上传完成"):
        verify_uploaded_video(service, "abc", attempts=2, delay_sec=0)


def test_wait_for_processing_started() -> None:
    from unittest.mock import MagicMock

    from scripts.video_upload.youtube_upload import wait_for_processing_started

    service = MagicMock()
    service.videos.return_value.list.return_value.execute.side_effect = [
        {
            "items": [
                {
                    "status": {"uploadStatus": "uploaded"},
                    "processingDetails": {"processingStatus": ""},
                }
            ]
        },
        {
            "items": [
                {
                    "status": {"uploadStatus": "uploaded"},
                    "processingDetails": {"processingStatus": "processing"},
                }
            ]
        },
    ]
    status = wait_for_processing_started(service, "abc", attempts=3, delay_sec=0)
    assert status == "processing"
