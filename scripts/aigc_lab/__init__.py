"""AIGC 文生视频实验台：样本入库、自动评分、原子化 prompt。"""

from .prompt_atoms import (
    DEFAULT_RAIN_MODE,
    DEFAULT_SCENES,
    RAIN_MODES,
    SLOT_ORDER,
    baseline_prompt,
    compose_prompt,
    format_table,
    normalize_rain_mode,
    replace_failed_atoms,
    rewrite_atomic,
)
from .score import ScoreError, score_run
from .store import T2vRun, attach_run_video, create_run, list_runs, load_run
from .tag_pools import (
    failed_tags_from_scores,
    load_pools,
    load_scene_pool,
    merge_into_pools,
    qualified_tags_from_scores,
)

__all__ = [
    "DEFAULT_RAIN_MODE",
    "DEFAULT_SCENES",
    "RAIN_MODES",
    "SLOT_ORDER",
    "ScoreError",
    "T2vRun",
    "attach_run_video",
    "baseline_prompt",
    "compose_prompt",
    "create_run",
    "failed_tags_from_scores",
    "format_table",
    "list_runs",
    "load_pools",
    "load_run",
    "load_scene_pool",
    "merge_into_pools",
    "normalize_rain_mode",
    "qualified_tags_from_scores",
    "replace_failed_atoms",
    "rewrite_atomic",
    "score_run",
]
