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
