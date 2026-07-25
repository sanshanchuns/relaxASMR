"""torch_runtime：禁用 TF、按 GPU 选择 device。"""

from __future__ import annotations

import os
import types

import pytest


def test_env_disables_tensorflow_backend() -> None:
    import scripts.video_analysis.torch_runtime as tr

    assert os.environ.get("USE_TF") == "0"
    assert os.environ.get("USE_TORCH") == "1"
    assert os.environ.get("TRANSFORMERS_NO_TF") == "1"
    assert tr._BLACKWELL_MIN_MAJOR == 12


def test_resolve_clip_device_cpu_when_no_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False))

    import scripts.video_analysis.torch_runtime as tr

    monkeypatch.setattr(tr, "require_torch", lambda: fake_torch)
    assert tr.resolve_clip_device() == "cpu"


def test_resolve_clip_device_cuda_when_probe_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(
            is_available=lambda: True,
            get_device_capability=lambda _idx=0: (8, 9),
            get_device_name=lambda _idx=0: "RTX 4060 Ti",
        ),
        zeros=lambda *_a, **_k: None,
    )

    import scripts.video_analysis.torch_runtime as tr

    monkeypatch.setattr(tr, "require_torch", lambda: fake_torch)
    assert tr.resolve_clip_device() == "cuda"


def test_probe_cuda_blackwell_gives_cu128_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a, **_k):
        raise RuntimeError("no kernel image is available for execution on the device")

    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(
            is_available=lambda: True,
            get_device_capability=lambda _idx=0: (12, 0),
            get_device_name=lambda _idx=0: "RTX 5060",
        ),
        zeros=_boom,
    )

    import scripts.video_analysis.torch_runtime as tr

    monkeypatch.setattr(tr, "require_torch", lambda: fake_torch)
    with pytest.raises(RuntimeError, match="cu128"):
        tr.resolve_clip_device()
