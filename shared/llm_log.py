"""Route in-process LLM / pipeline logs to GUI (or stdout when unset).

与 ``economist/shared/llm_log.py`` 保持一致：``cli/agy/`` 内部用 ``emit_llm_log``
打日志，因此这里必须提供同名同签名的实现，否则 ``import agy`` 会 ModuleNotFoundError。
"""

from __future__ import annotations

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
    """Send to active GUI callback when set; otherwise print to stdout."""
    text = (message or "").rstrip()
    if not text:
        return
    callback = _log_callback.get()
    if callback is not None:
        callback(text)
    else:
        print(text, flush=True)
