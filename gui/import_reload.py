"""每次从磁盘重新加载脚本模块（避免 GUI 长驻时用到旧代码）。"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO_ROOT / "scripts"


def _ensure_scripts_path() -> None:
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))


def load_module(path: Path, module_name: str) -> ModuleType:
    """从任意 .py 路径加载（用于无包内相对导入的脚本）。"""
    path = path.resolve()
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_scripts_module(dotted: str) -> ModuleType:
    """加载 scripts/ 下包模块，如 video_upload.youtube_upload。"""
    _ensure_scripts_path()
    if dotted in sys.modules:
        return importlib.reload(sys.modules[dotted])
    return importlib.import_module(dotted)
