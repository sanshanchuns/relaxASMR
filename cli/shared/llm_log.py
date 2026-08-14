"""把进程内 LLM / 流水线日志路由到当前回调（如 GUI 日志区）。

``cli/agy/`` 内部用 ``emit_llm_log`` 打日志；GUI 可用 ``llm_log_context`` 注入回调。
无回调时默认静默，避免刷屏；调试可设 ``LLM_LOG_STDOUT=1``。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from contextvars import ContextVar, Token

LogCallback = Callable[[str], None]

_log_callback: ContextVar[LogCallback | None] = ContextVar("llm_log_callback", default=None)


def set_llm_log_callback(callback: LogCallback | None) -> Token:
    return _log_callback.set(callback)


def reset_llm_log_callback(token: Token) -> None:
    _log_callback.reset(token)


class llm_log_context:
    """Temporarily route ``emit_llm_log`` to *callback* (thread-local via contextvar)."""

    def __init__(self, callback: LogCallback | None) -> None:
        self._callback = callback
        self._token: Token | None = None

    def __enter__(self) -> llm_log_context:
        self._token = set_llm_log_callback(self._callback)
        return self

    def __exit__(self, *_args: object) -> None:
        if self._token is not None:
            reset_llm_log_callback(self._token)


def emit_llm_log(message: str) -> None:
    """Send to active callback when set; otherwise silent (unless LLM_LOG_STDOUT=1)."""
    text = (message or "").rstrip()
    if not text:
        return
    callback = _log_callback.get()
    if callback is not None:
        callback(text)
        return
    flag = os.environ.get("LLM_LOG_STDOUT", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        print(text, flush=True)
