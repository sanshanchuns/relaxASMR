"""AIGC 文生/图生 Agent 管线 run 落盘（独立于旧 t2v_lab）。"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from scripts.config.paths import (
    agent_i2v_lab_dir,
    agent_i2v_runs_dir,
    agent_t2v_lab_dir,
    agent_t2v_runs_dir,
)

Kind = Literal["t2v", "i2v"]

I2V_JIMENG_PARAMS: dict[str, str | int] = {
    "model": "Seedance 2.0 Fast VIP",
    "aspect_ratio": "16:9",
    "resolution": "720P",
    "duration_sec": 5,
    "generate_count": 1,
    # 全能参考：同系列异构；勿用首尾帧（同图首+尾会锁死成「几乎同一张图」）
    "ref_mode": "全能参考",
}

#: 图生顶栏可选模型（与即梦网页下拉文案对齐）
I2V_MODEL_CHOICES: tuple[str, ...] = (
    "Seedance 2.0 Fast VIP",
    "Seedance 2.0 VIP",
    "Seedance 2.5",
)


def normalize_i2v_resolution(value: str | None) -> str:
    raw = (value or "720P").strip().upper().replace(" ", "")
    raw = raw.replace("P", "") + "P"
    return "1080P" if raw == "1080P" else "720P"


def model_allows_1080p(model: str) -> bool:
    """Fast VIP / Fast 仅 720；Seedance 2.0 / 2.5 才有 1080p。"""
    m = (model or "").strip()
    if "Fast" in m or "fast" in m:
        return False
    return "2.5" in m or "2.0" in m or "Seedance" in m


def resolutions_for_i2v_model(model: str) -> tuple[str, ...]:
    return ("720p", "1080p") if model_allows_1080p(model) else ("720p",)


def resolve_i2v_gen_params(params: dict | None = None) -> dict[str, str | int]:
    """合并默认档与 lab params；Fast 强制 720P。"""
    merged: dict[str, str | int] = {**I2V_JIMENG_PARAMS}
    if params:
        for key in (
            "model",
            "aspect_ratio",
            "resolution",
            "duration_sec",
            "generate_count",
            "ref_mode",
        ):
            if key in params and params[key] not in (None, ""):
                merged[key] = params[key]
    model = str(merged.get("model") or I2V_JIMENG_PARAMS["model"])
    if model == "Seedance 2.0":
        model = "Seedance 2.0 VIP"
    if model not in I2V_MODEL_CHOICES:
        model = str(I2V_JIMENG_PARAMS["model"])
    merged["model"] = model
    merged["aspect_ratio"] = "16:9"
    res = normalize_i2v_resolution(str(merged.get("resolution") or "720P"))
    if not model_allows_1080p(model):
        res = "720P"
    merged["resolution"] = res
    try:
        merged["duration_sec"] = max(1, min(15, int(merged.get("duration_sec") or 5)))
    except (TypeError, ValueError):
        merged["duration_sec"] = 5
    try:
        merged["generate_count"] = max(1, min(10, int(merged.get("generate_count") or 1)))
    except (TypeError, ValueError):
        merged["generate_count"] = 1
    return merged


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_run_id(seed: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    h = hashlib.sha256(seed.encode()).hexdigest()[:8]
    return f"{ts}_{h}"


@dataclass
class AgentRun:
    kind: Kind
    run_id: str
    dir: Path
    prompt: str = ""
    meta: dict = field(default_factory=dict)
    review: dict = field(default_factory=dict)
    viral_score: dict = field(default_factory=dict)
    posterior: dict = field(default_factory=dict)

    @property
    def prompt_path(self) -> Path:
        return self.dir / "prompt.txt"

    @property
    def video_path(self) -> Path:
        return self.dir / "video.mp4"

    @property
    def meta_path(self) -> Path:
        return self.dir / "meta.json"

    @property
    def review_path(self) -> Path:
        return self.dir / "review.json"

    @property
    def viral_path(self) -> Path:
        return self.dir / "viral_score.json"

    @property
    def ref_image_path(self) -> Path:
        return self.dir / "ref_image.png"

    @property
    def posterior_path(self) -> Path:
        return self.dir / "posterior.json"

    def save_prompt(self, text: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.prompt_path.write_text(text.strip() + "\n", encoding="utf-8")
        self.prompt = text.strip()

    def save_meta(self, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.meta = dict(data)

    def save_review(self, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.review_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.review = dict(data)

    def save_viral(self, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.viral_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.viral_score = dict(data)

    def update_meta(self, **updates: object) -> None:
        data = dict(self.meta or {})
        data.update(updates)
        self.save_meta(data)


def _lab_dir(kind: Kind) -> Path:
    return agent_t2v_lab_dir() if kind == "t2v" else agent_i2v_lab_dir()


def _runs_dir(kind: Kind) -> Path:
    return agent_t2v_runs_dir() if kind == "t2v" else agent_i2v_runs_dir()


def lab_params(kind: Kind) -> dict:
    path = _lab_dir(kind) / "params.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_lab_params(kind: Kind, updates: dict) -> Path:
    path = _lab_dir(kind) / "params.json"
    data = lab_params(kind)
    data.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def create_agent_run(
    kind: Kind,
    *,
    prompt: str,
    rain_mode: str,
    slots: dict[str, list[str]] | None = None,
    assertions: list[str] | None = None,
    subjects: list[str] | None = None,
    scene_keywords: str = "",
    duration_sec: int | None = None,
    ref_image: Path | None = None,
    review: dict | None = None,
    series_goal: str = "",
) -> AgentRun:
    from scripts.aigc_lab.rain_modes import normalize_rain_mode, rain_label
    from scripts.aigc_lab.youtube_competitor_pool import series_goal_for_rain_mode

    mode = normalize_rain_mode(rain_mode)
    goal = series_goal or series_goal_for_rain_mode(mode)
    seed = f"{kind}|{scene_keywords}|{mode}|{prompt}"
    run_id = _make_run_id(seed)
    run_dir = _runs_dir(kind) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    params = lab_params(kind)
    if kind == "i2v":
        gen = resolve_i2v_gen_params(params)
        dur = int(duration_sec if duration_sec is not None else gen["duration_sec"])
    else:
        gen = params
        dur = int(duration_sec if duration_sec is not None else params.get("duration_sec", 6))
    run = AgentRun(kind=kind, run_id=run_id, dir=run_dir)
    run.save_prompt(prompt)
    if ref_image and Path(ref_image).is_file():
        dest = run.ref_image_path
        if Path(ref_image).suffix.lower() in {".jpg", ".jpeg"}:
            dest = run.dir / "ref_image.jpg"
        shutil.copy2(ref_image, dest)
        ref_rel = dest.name
    else:
        ref_rel = ""
    run.save_meta(
        {
            "run_id": run_id,
            "kind": kind,
            "created_at": _now_iso(),
            "model": gen.get("model", "Seedance 2.0 Fast VIP"),
            "aspect_ratio": gen.get("aspect_ratio", "16:9"),
            "resolution": gen.get("resolution", "720P"),
            "duration_sec": dur,
            "ref_mode": gen.get("ref_mode", "") if kind == "i2v" else "",
            "rain_mode": mode,
            "rain_label": rain_label(mode),
            "series_goal": goal,
            "scene_keywords": scene_keywords,
            "slots": slots or {},
            "assertions": [
                str(a).strip() for a in (assertions or []) if str(a).strip()
            ],
            "subjects": [str(s).strip() for s in (subjects or []) if str(s).strip()],
            "ref_image": ref_rel,
            "confirmed": True,
        }
    )
    if review:
        run.save_review(review)
    return run


def load_agent_run(kind: Kind, run_id: str) -> AgentRun:
    run_dir = _runs_dir(kind) / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run 不存在: {kind}/{run_id}")
    run = AgentRun(kind=kind, run_id=run_id, dir=run_dir)
    if run.prompt_path.is_file():
        run.prompt = run.prompt_path.read_text(encoding="utf-8").strip()
    if run.meta_path.is_file():
        run.meta = json.loads(run.meta_path.read_text(encoding="utf-8"))
    if run.review_path.is_file():
        run.review = json.loads(run.review_path.read_text(encoding="utf-8"))
    if run.viral_path.is_file():
        run.viral_score = json.loads(run.viral_path.read_text(encoding="utf-8"))
    if run.posterior_path.is_file():
        run.posterior = json.loads(run.posterior_path.read_text(encoding="utf-8"))
    return run


def list_agent_runs(kind: Kind) -> list[AgentRun]:
    return list_agent_runs_light(kind)


def list_agent_runs_light(kind: Kind) -> list[AgentRun]:
    """列表用：只读 meta / viral，不读 prompt 全文。"""
    root = _runs_dir(kind)
    if not root.is_dir():
        return []
    runs: list[AgentRun] = []
    for path in sorted(root.iterdir(), reverse=True):
        if not path.is_dir():
            continue
        run = AgentRun(kind=kind, run_id=path.name, dir=path)
        try:
            if run.meta_path.is_file():
                run.meta = json.loads(run.meta_path.read_text(encoding="utf-8"))
            if run.viral_path.is_file():
                run.viral_score = json.loads(run.viral_path.read_text(encoding="utf-8"))
            if run.review_path.is_file():
                run.review = json.loads(run.review_path.read_text(encoding="utf-8"))
            if run.posterior_path.is_file():
                run.posterior = json.loads(
                    run.posterior_path.read_text(encoding="utf-8")
                )
        except (OSError, json.JSONDecodeError):
            continue
        runs.append(run)
    return runs
