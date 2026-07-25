"""PyTorch / CLIP 运行时：禁用 TensorFlow 后端，按 GPU 选择 device（4060 / 5060 通用）。"""

from __future__ import annotations

import os

# CLIP 仅用 PyTorch；transformers 默认会尝试 import tensorflow，与 numpy 2.x 冲突
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

_BLACKWELL_MIN_MAJOR = 12  # sm_120 (RTX 50 系)


def require_torch():
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "CLIP 分析需要 PyTorch。请按 GPU 安装（二选一）：\n"
            "  RTX 50 系 (5060 等): pip install torch torchvision "
            "--index-url https://download.pytorch.org/whl/cu128\n"
            "  RTX 40 系及以下 (4060 等): pip install torch torchvision\n"
            "  无 GPU: pip install torch --index-url https://download.pytorch.org/whl/cpu\n"
            "详见 scripts/video_analysis/requirements.txt"
        ) from exc
    return torch


def _cuda_capability() -> tuple[int, int] | None:
    torch = require_torch()
    if not torch.cuda.is_available():
        return None
    return torch.cuda.get_device_capability(0)


def _probe_cuda() -> None:
    """验证当前 PyTorch 能在本机 GPU 上跑 kernel；失败时给出按代际的安装提示。"""
    torch = require_torch()
    if not torch.cuda.is_available():
        return
    cap = _cuda_capability()
    name = torch.cuda.get_device_name(0)
    try:
        torch.zeros(1, device="cuda")
    except RuntimeError as exc:
        msg = str(exc).lower()
        if cap and cap[0] >= _BLACKWELL_MIN_MAJOR:
            hint = (
                f"检测到 {name} (sm_{cap[0]}{cap[1]})，当前 PyTorch 不支持 Blackwell。\n"
                "请执行：pip install torch torchvision "
                "--index-url https://download.pytorch.org/whl/cu128"
            )
        elif "no kernel image" in msg or "not compatible" in msg:
            hint = (
                f"CUDA 初始化失败 ({name})：{exc}\n"
                "RTX 50 系: pip install torch torchvision "
                "--index-url https://download.pytorch.org/whl/cu128\n"
                "RTX 40 系: pip install torch torchvision"
            )
        else:
            hint = f"CUDA 初始化失败 ({name})：{exc}"
        raise RuntimeError(hint) from exc


def resolve_clip_device() -> str:
    """返回 CLIP 推理 device：cuda 可用且 kernel 正常时用 GPU，否则 cpu。"""
    torch = require_torch()
    if not torch.cuda.is_available():
        return "cpu"
    _probe_cuda()
    return "cuda"
