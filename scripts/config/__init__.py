"""全项目共享配置：路径、域常量。"""

from scripts.config.common_constants import (
    CLIMATE_NAMES,
    CLOSE_NAMES,
    DISTANT_NAMES,
    SPACE_NAMES,
)
from scripts.config.paths import (
    REPO_ROOT,
    audio_dir,
    audio_layer_dir,
    base_url,
    export_dir,
    material_dir,
)

__all__ = [
    "CLIMATE_NAMES",
    "CLOSE_NAMES",
    "DISTANT_NAMES",
    "REPO_ROOT",
    "SPACE_NAMES",
    "audio_dir",
    "audio_layer_dir",
    "base_url",
    "export_dir",
    "material_dir",
]
