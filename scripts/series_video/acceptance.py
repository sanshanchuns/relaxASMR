"""产物验收编排：把客观测量和 Gemini 评审串起来，结论写回条目。

职责划分刻意分开，方便单独测试和单独替换：

* :mod:`video_probe` —— 只做客观测量（抽帧、运动量），不认识业务对象
* :mod:`review`      —— 只做 Gemini 评审，不认识磁盘布局
* 本模块            —— 编排两者、决定放行还是标记、落盘到 ``BatchMeta``

顺序固定：先跑免费的客观测量，运动量不合格就直接标记，**不再花钱**送评审；
只有客观那关过了才送 Gemini 看抽帧。
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from scripts.series_video.review import Review, review_video_frames
from scripts.series_video.series import get_series
from scripts.series_video.store import BatchMeta, SeriesItem
from scripts.series_video.video_probe import VideoProbeError, probe_video

LogFn = Callable[[str], None]


@dataclass
class Acceptance:
    """一次产物验收的合并结论。"""

    ok: bool
    motion_score: float = 0.0
    issues: list[str] = field(default_factory=list)
    review: Review = field(default_factory=Review)

    @property
    def summary(self) -> str:
        state = "通过" if self.ok else "不通过"
        detail = f"：{'；'.join(self.issues)}" if self.issues else ""
        return f"验收{state}（运动量 {self.motion_score:.1f}）{detail}"


def accept_video(
    meta: BatchMeta,
    item: SeriesItem,
    video_path: Path,
    *,
    log_fn: LogFn | None = None,
) -> Acceptance:
    """验收一条刚生成的视频，结论写进 ``item`` 并 ``meta.save()``。

    不合格**不删文件**：视频是花钱买的，留在盘上让人自己看一眼再决定重出还是将就。
    """
    log = log_fn or (lambda _m: None)
    spec = get_series(meta.series_id)
    review = Review()
    tmp_dir = Path(tempfile.mkdtemp(prefix="accept_frames_"))
    try:
        probe = probe_video(
            video_path,
            motion_range=spec.frame_motion,
            frames_dir=tmp_dir,
            log_fn=log_fn,
        )
        issues = list(probe.issues)
        if probe.ok:
            review = review_video_frames(
                probe.frames,
                meta.series_id,
                motion_score=probe.motion_score,
                prompt=item.video_prompt,
                log_fn=log_fn,
            )
            if review.blocked:
                issues.extend(review.issues or ["Gemini 判定不合格"])
        else:
            log("[视频验收] 客观运动量已不合格，跳过 Gemini 评审（省一次调用）")
    except VideoProbeError as exc:
        # 没装 ffmpeg / 文件坏了：验收本身失败不等于产物不合格，记一笔就放行。
        log(f"[视频验收] 无法测量，跳过：{exc}")
        item.video_review = Review(issues=[f"验收未执行：{exc}"]).to_dict()
        meta.save()
        return Acceptance(ok=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    item.video_motion = round(probe.motion_score, 2)
    item.video_review = review.to_dict()
    item.video_error = "；".join(issues) if issues else ""
    meta.save()

    result = Acceptance(
        ok=not issues,
        motion_score=probe.motion_score,
        issues=issues,
        review=review,
    )
    log(f"[视频验收] {video_path.name} · {result.summary}")
    return result
