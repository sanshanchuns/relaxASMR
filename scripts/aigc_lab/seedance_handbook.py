"""Seedance 2.0 提示词手册：Gemini 疑问 × Jimeng Agent 答复存档。"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.config.paths import aigc_dir

_HANDBOOK_NAME = "Seedance2.0手册.md"
_ENTRY_SPLIT = re.compile(r"\n## ")
_Q_LINE = re.compile(r"^\*\*问[：:]\*\*\s*(.+)$", re.MULTILINE)


def seedance_handbook_path() -> Path:
    return aigc_dir() / _HANDBOOK_NAME


def _normalize_question(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


def question_fingerprint(question: str) -> str:
    return hashlib.sha1(_normalize_question(question).encode("utf-8")).hexdigest()[:16]


def _ensure_header(path: Path) -> None:
    if path.is_file() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Seedance 2.0 提示词手册\n\n"
        "> Gemini 对提示词的疑问，经 Jimeng Agent 答复后存档于此。"
        "同题不重复写入；可供后续审核引用。\n\n",
        encoding="utf-8",
    )


def load_handbook_text(*, max_chars: int = 6000) -> str:
    path = seedance_handbook_path()
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n…（手册已截断）"


def existing_question_fps(path: Path | None = None) -> set[str]:
    p = path or seedance_handbook_path()
    if not p.is_file():
        return set()
    raw = p.read_text(encoding="utf-8")
    fps: set[str] = set()
    for m in _Q_LINE.finditer(raw):
        fps.add(question_fingerprint(m.group(1)))
    return fps


def format_handbook_entry(*, question: str, answer: str, title: str = "") -> str:
    q = (question or "").strip()
    a = (answer or "").strip()
    heading = (title or "").strip() or _short_title(q)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (
        f"## {heading}\n\n"
        f"_存档日期：{stamp}_\n\n"
        f"**问：** {q}\n\n"
        f"**答：** {a}\n\n"
        f"---\n\n"
    )


def _short_title(question: str) -> str:
    q = re.sub(r"\s+", " ", (question or "").strip())
    if len(q) <= 36:
        return q or "未命名疑问"
    return q[:34] + "…"


def append_handbook_qa(
    *,
    question: str,
    answer: str,
    title: str = "",
) -> bool:
    """追加一条问答。问题已存在则跳过，返回是否写入。"""
    q = (question or "").strip()
    a = (answer or "").strip()
    if not q or not a:
        return False
    path = seedance_handbook_path()
    _ensure_header(path)
    fp = question_fingerprint(q)
    if fp in existing_question_fps(path):
        return False
    path.write_text(
        path.read_text(encoding="utf-8") + format_handbook_entry(question=q, answer=a, title=title),
        encoding="utf-8",
    )
    return True


def append_handbook_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    """批量追加；返回实际新写入的条目。"""
    written: list[dict[str, str]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        q = str(item.get("question") or "").strip()
        a = str(item.get("answer") or "").strip()
        title = str(item.get("title") or "").strip()
        if append_handbook_qa(question=q, answer=a, title=title):
            written.append({"question": q, "answer": a, "title": title})
    return written


__all__ = [
    "append_handbook_entries",
    "append_handbook_qa",
    "existing_question_fps",
    "format_handbook_entry",
    "load_handbook_text",
    "question_fingerprint",
    "seedance_handbook_path",
]
