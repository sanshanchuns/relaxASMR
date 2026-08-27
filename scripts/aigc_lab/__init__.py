"""AIGC 抽卡实验台：三档提示词、后验、run 落盘。"""

from .posterior import PosteriorError, run_posterior, set_human_verdict
from .prompt_gen import PromptGenError, generate_rain_prompts
from .rain_modes import DEFAULT_RAIN_MODE, RAIN_MODES, normalize_rain_mode

__all__ = [
    "DEFAULT_RAIN_MODE",
    "RAIN_MODES",
    "PosteriorError",
    "PromptGenError",
    "generate_rain_prompts",
    "normalize_rain_mode",
    "run_posterior",
    "set_human_verdict",
]
