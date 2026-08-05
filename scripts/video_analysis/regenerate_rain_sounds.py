#!/usr/bin/env python3
"""从 preset_db 重新渲染 1_rain/sounds（42s 渲染 → optimize 裁 30s → 安装 sounds）。

目录：
  最终产物  baseURL/audio/1_rain/sounds/
  临时 WAV  工程根目录 tmp/rain_regen/{regen_raw,regen_trimmed}（裁切/安装后删除）
  preset_db   scripts/video_analysis/preset_db/
    natural_rain_rpps/render_jobs/   — 42s 渲染工程
    natural_rain_regen/              — manifest.json、trim_report.json
    natural_rain_attachments/        — batch_render_regen.lua

流程：
  1. prepare  — 生成 render_jobs/*.rpp + batch_render_regen.lua + manifest.json
  2. render     — Reaper 渲染 regen_raw/*.wav（42s）
  3. trim       — optimize → regen_trimmed/，成功后删除对应 regen_raw
  4. install    — regen_trimmed/ → sounds/，成功后删除 regen_trimmed

用法（仓库根目录）:
  python3 -m scripts.video_analysis.regenerate_rain_sounds prepare
  python3 -m scripts.video_analysis.regenerate_rain_sounds render --batch-size 50
  python3 -m scripts.video_analysis.regenerate_rain_sounds trim --mode optimize
  python3 -m scripts.video_analysis.regenerate_rain_sounds install
  python3 -m scripts.video_analysis.regenerate_rain_sounds pipeline   # 全流程
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.config.paths import audio_dir, audio_layer_dir  # noqa: E402
from gui.reaper_launch import render_reaper_project, run_reaper_lua, wsl_to_windows_path  # noqa: E402
from scripts.video_analysis.rain_sound_loop import (  # noqa: E402
    detect_silence_bounds,
    loop_seam_score,
    trim_wav_auto,
    trim_wav_best_window,
    trim_wav_fixed,
)

LAYER_ID = "1_rain"
PRESET_DB = REPO / "scripts" / "video_analysis" / "preset_db"
RPPS_SRC = PRESET_DB / "natural_rain_rpps"
RENDER_JOBS = RPPS_SRC / "render_jobs"
REGEN_META = PRESET_DB / "natural_rain_regen"
ATTACH = PRESET_DB / "natural_rain_attachments"
BATCH_LUA = ATTACH / "batch_render_regen.lua"
SESSION_LUA = REGEN_META / "batch_session.lua"
WORK_TMP = REPO / "tmp" / "rain_regen"

# 临时 WAV 在工程 tmp/（本地盘，避免 E: 来回读写）；RPP/Lua/报告在 preset_db
DEFAULT_RENDER_S = 42.0
DEFAULT_OUTPUT_S = 30.0
DEFAULT_SEARCH_MARGIN = 2.0


def _raw_dir() -> Path:
    """42s Reaper 渲染输出（工程 tmp，完成后删除）。"""
    return WORK_TMP / "regen_raw"


def _trimmed_dir() -> Path:
    """30s optimize 裁切 staging（安装前，工程 tmp）。"""
    return WORK_TMP / "regen_trimmed"


def _jobs_dir() -> Path:
    return RENDER_JOBS


def _sounds_dir() -> Path:
    return audio_layer_dir(LAYER_ID)


def _manifest_path() -> Path:
    return REGEN_META / "manifest.json"


def _trim_report_path() -> Path:
    return REGEN_META / "trim_report.json"


def _repair_dir() -> Path:
    return REGEN_META / "repair"


def _repair_report_path() -> Path:
    return REGEN_META / "repair_report.json"


RENDER_RANGE_RE = re.compile(
    r"^(\s*RENDER_RANGE\s+0\s+)0\.0\s+10\.0(\s+0\s+1000\s*)$",
    re.MULTILINE,
)
RENDER_FILE_RE = re.compile(r"^(\s*RENDER_FILE\s+\").*?(\"\s*)$", re.MULTILINE)


def _ensure_regen_dirs() -> None:
    for d in (RENDER_JOBS, REGEN_META, _raw_dir(), _trimmed_dir()):
        d.mkdir(parents=True, exist_ok=True)


def _wavs_for_manifest(wavs: list[Path], manifest: dict) -> list[Path]:
    stems = manifest.get("job_stems") or []
    if not stems:
        return wavs
    by_name = {w.name: w for w in wavs}
    ordered = [by_name[f"{s}.wav"] for s in stems if f"{s}.wav" in by_name]
    return ordered or wavs


def _all_job_stems() -> list[str]:
    manifest = _load_manifest()
    stems = manifest.get("job_stems") or []
    if stems:
        return stems
    return sorted(p.stem for p in RENDER_JOBS.glob("*.rpp"))


def _pending_stems() -> list[str]:
    sounds = _sounds_dir()
    return [s for s in _all_job_stems() if not (sounds / f"{s}.wav").is_file()]


def _apply_batch_stems_filter(items: list, stems: list[str] | None, *, key) -> list:
    if not stems:
        return items
    allow = set(stems)
    return [x for x in items if key(x) in allow]


def _installable_trimmed_wavs(
    manifest: dict,
    limit: int = 0,
    *,
    batch_stems: list[str] | None = None,
) -> list[Path]:
    trimmed = _trimmed_dir()
    if batch_stems:
        wavs = [trimmed / f"{s}.wav" for s in batch_stems]
        wavs = [p for p in wavs if p.is_file()]
    else:
        wavs = sorted(
            p for p in trimmed.glob("*.wav")
            if p.is_file() and not p.name.startswith("_")
        )
        wavs = _wavs_for_manifest(wavs, manifest)
    if limit:
        wavs = wavs[:limit]
    return wavs


def _temp_wav_dirs() -> tuple[Path, Path]:
    return _raw_dir(), _trimmed_dir()


def _remove_temp_wav(path: Path) -> bool:
    if path.is_file():
        path.unlink()
        return True
    return False


def _cleanup_temp_dir(path: Path) -> int:
    """删除目录内全部 wav，目录空则移除。返回删除文件数。"""
    if not path.is_dir():
        return 0
    n = 0
    for wav in path.glob("*.wav"):
        wav.unlink()
        n += 1
    try:
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    except OSError:
        pass
    return n


def _cleanup_temp_wavs_for_names(names: list[str]) -> int:
    """按文件名清理 regen_raw / regen_trimmed 中的临时 wav。"""
    removed = 0
    for name in names:
        for d in _temp_wav_dirs():
            if _remove_temp_wav(d / name):
                removed += 1
    for d in _temp_wav_dirs():
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass
    return removed


def _cleanup_all_temp_wavs() -> int:
    """清空全部临时 wav 目录。"""
    return _cleanup_temp_dir(_raw_dir()) + _cleanup_temp_dir(_trimmed_dir())


def windows_path_for_reaper(path: Path) -> str:
    """WSL/Linux 绝对路径 → Windows Reaper 可写入的原生路径（如 E:\\…）。"""
    p = path.resolve()
    if sys.platform == "win32":
        return str(p)
    return wsl_to_windows_path(p)


def lua_path_literal(win_path: str) -> str:
    """Lua 字符串字面量中的 Windows 路径（反斜杠加倍）。"""
    return win_path.replace("\\", "\\\\")


def _batch_lua_lines(rpp_paths: list[Path]) -> list[str]:
    win_paths = [lua_path_literal(windows_path_for_reaper(p)) for p in rpp_paths]
    lines = ["local projects = {"]
    for win_path in win_paths:
        lines.append(f'  "{win_path}",')
    lines.extend([
        "}",
        "",
        "for i, path in ipairs(projects) do",
        "  reaper.Main_openProject(path)",
        "  reaper.Main_OnCommand(42230, 0) -- Render",
        "end",
        "reaper.Main_OnCommand(40004, 0) -- Quit REAPER",
        "",
    ])
    return lines


def _write_batch_lua(rpp_paths: list[Path], lua_path: Path) -> Path:
    lua_path.parent.mkdir(parents=True, exist_ok=True)
    lua_path.write_text("\n".join(_batch_lua_lines(rpp_paths)), encoding="utf-8")
    return lua_path


def _load_reaper_exe() -> str | None:
    cfg = REPO / "gui" / "user_config.json"
    if not cfg.is_file():
        return None
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    exe = (data.get("reaper_exe") or "").strip()
    return exe or None


def patch_rpp_for_32s(text: str, *, render_file_unc: str, render_end: float = 32.0) -> str:
    if RENDER_RANGE_RE.search(text):
        text = RENDER_RANGE_RE.sub(rf"\g<1>0.0 {render_end:.1f}\2", text)
    else:
        text = re.sub(
            r"^(\s*RENDER_RANGE\s+0\s+)0\.0\s+[\d.]+\s+0\s+1000\s*$",
            rf"\g<1>0.0 {render_end:.1f} 0 1000",
            text,
            count=1,
            flags=re.MULTILINE,
        )

    def _repl_render_file(m: re.Match) -> str:
        return f'{m.group(1)}{render_file_unc}{m.group(2)}'

    text = RENDER_FILE_RE.sub(_repl_render_file, text, count=1)
    return text


def cmd_prepare(args: argparse.Namespace) -> int:
    if not RPPS_SRC.is_dir():
        raise SystemExit(f"缺少 RPP 目录: {RPPS_SRC}")

    _ensure_regen_dirs()
    jobs = _jobs_dir()
    raw = _raw_dir()

    rpps = sorted(RPPS_SRC.glob("*.rpp"))
    if args.offset:
        rpps = rpps[args.offset :]
    if args.limit:
        rpps = rpps[: args.limit]

    job_paths_win: list[str] = []
    for src in rpps:
        stem = src.stem
        out_wav = raw / f"{stem}.wav"
        job = jobs / f"{stem}.rpp"
        text = src.read_text(encoding="utf-8", errors="surrogateescape")
        win_out = windows_path_for_reaper(out_wav)
        patched = patch_rpp_for_32s(text, render_file_unc=win_out, render_end=args.render_s)
        job.write_text(patched, encoding="utf-8", errors="surrogateescape")
        job_paths_win.append(windows_path_for_reaper(job))

    job_stems = [src.stem for src in rpps]
    job_rpp_paths = [jobs / f"{s}.rpp" for s in job_stems]
    _write_batch_lua(job_rpp_paths, BATCH_LUA)

    manifest = {
        "render_s": args.render_s,
        "trim_head_s": args.trim_head,
        "trim_tail_s": args.trim_tail,
        "output_s": args.output_s,
        "search_margin_head": args.search_margin_head,
        "search_margin_tail": args.search_margin_tail,
        "optimize_metric": args.optimize_metric,
        "trim_mode": "optimize",
        "job_count": len(rpps),
        "job_stems": job_stems,
        "jobs_dir": str(jobs),
        "raw_dir": str(raw),
        "trimmed_dir": str(_trimmed_dir()),
        "sounds_dir": str(_sounds_dir()),
        "lua": str(BATCH_LUA),
    }
    _manifest_path().write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"已生成 {len(rpps)} 个 render job → {jobs}")
    print(f"Reaper 渲染输出 → {raw}")
    print(f"批量渲染脚本 → {BATCH_LUA}")
    print(f"最终安装目标 → {_sounds_dir()}")
    print()
    print("下一步：")
    print("  python3 -m scripts.video_analysis.regenerate_rain_sounds render --batch-size 50")
    print("  python3 -m scripts.video_analysis.regenerate_rain_sounds trim --mode optimize")
    print("  python3 -m scripts.video_analysis.regenerate_rain_sounds install")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    jobs = _jobs_dir()
    raw = _raw_dir()
    if not jobs.is_dir():
        raise SystemExit(f"render_jobs 不存在，请先 prepare: {jobs}")
    raw.mkdir(parents=True, exist_ok=True)

    rpps = sorted(jobs.glob("*.rpp"))
    manifest_path = _manifest_path()
    if manifest_path.is_file() and not args.offset:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            stems = manifest.get("job_stems") or []
            if stems:
                by_stem = {p.stem: p for p in rpps}
                rpps = [by_stem[s] for s in stems if s in by_stem]
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
    if args.offset:
        rpps = rpps[args.offset :]
    if args.limit:
        rpps = rpps[: args.limit]
    batch_stems = getattr(args, "batch_stems", None)
    if batch_stems:
        by_stem = {p.stem: p for p in rpps}
        rpps = [by_stem[s] for s in batch_stems if s in by_stem]
    if not rpps:
        raise SystemExit("无待渲染 rpp")

    manifest_path = _manifest_path()
    render_s = DEFAULT_RENDER_S
    if manifest_path.is_file():
        try:
            render_s = float(json.loads(manifest_path.read_text(encoding="utf-8")).get("render_s", render_s))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    reaper_exe = args.reaper_exe or _load_reaper_exe()
    use_lua = getattr(args, "use_lua", True)
    pending: list[Path] = []
    skip = 0
    for rpp in rpps:
        out_wav = raw / f"{rpp.stem}.wav"
        if args.skip_existing and out_wav.is_file() and out_wav.stat().st_size > 0:
            skip += 1
            continue
        pending.append(rpp)

    if not pending:
        print(f"渲染: 0 成功, {skip} 跳过, 0 失败（均已存在）")
        return 0

    t0 = time.time()
    ok, fail = 0, 0

    if use_lua and len(pending) >= 1:
        lua_path = _write_batch_lua(pending, SESSION_LUA)
        print(f"Reaper 单进程批量渲染 {len(pending)} 条（script.lua）→ {lua_path.name}")
        try:
            run_reaper_lua(lua_path, reaper_exe=reaper_exe)
        except Exception as e:
            print(f"  批量渲染失败: {e}")
            return 1
        for rpp in pending:
            out_wav = raw / f"{rpp.stem}.wav"
            if out_wav.is_file() and out_wav.stat().st_size > 0:
                ok += 1
            else:
                fail += 1
                print(f"  失败: 输出未生成 {out_wav.name}")
    else:
        for i, rpp in enumerate(pending, 1):
            out_wav = raw / f"{rpp.stem}.wav"
            print(f"[{i}/{len(pending)}] {rpp.name} → {out_wav.name}")
            try:
                render_reaper_project(
                    rpp,
                    reaper_exe=reaper_exe,
                    output_wav=out_wav,
                    duration_minutes=render_s / 60.0,
                )
                if out_wav.is_file() and out_wav.stat().st_size > 0:
                    ok += 1
                    print(f"  OK ({out_wav.stat().st_size // 1024} KB)")
                else:
                    fail += 1
                    print(f"  失败: 输出未生成 {out_wav}")
            except Exception as e:
                fail += 1
                print(f"  失败: {e}")

            if args.batch_size and i % args.batch_size == 0 and i < len(pending):
                print(f"--- 批次 {i // args.batch_size} 完成 ({i}/{len(pending)}) ---")

    print(f"渲染: {ok} 成功, {skip} 跳过, {fail} 失败, 耗时 {time.time() - t0:.1f}s")
    return 0 if fail == 0 else 1


def _iter_raw_wavs(limit: int | None = None, manifest: dict | None = None) -> list[Path]:
    wavs = sorted(_raw_dir().glob("*.wav"))
    if manifest:
        wavs = _wavs_for_manifest(wavs, manifest)
    if limit:
        wavs = wavs[:limit]
    return wavs


def _load_manifest() -> dict:
    manifest_path = _manifest_path()
    if not manifest_path.is_file():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def cmd_trim(args: argparse.Namespace) -> int:
    raw = _raw_dir()
    out = _trimmed_dir()
    if not raw.is_dir():
        raise SystemExit(f"raw 目录不存在，请先 prepare + Reaper 渲染: {raw}")

    manifest = _load_manifest()
    if args.mode == "optimize":
        if args.output_s == DEFAULT_OUTPUT_S and manifest.get("output_s"):
            args.output_s = float(manifest["output_s"])
        if args.search_margin_head == DEFAULT_SEARCH_MARGIN and manifest.get("search_margin_head") is not None:
            args.search_margin_head = float(manifest["search_margin_head"])
        if args.search_margin_tail == DEFAULT_SEARCH_MARGIN and manifest.get("search_margin_tail") is not None:
            args.search_margin_tail = float(manifest["search_margin_tail"])
        if args.optimize_metric == "combined" and manifest.get("optimize_metric"):
            args.optimize_metric = str(manifest["optimize_metric"])

    wavs = _iter_raw_wavs(args.limit if args.limit else None, manifest)
    batch_stems = getattr(args, "batch_stems", None)
    if batch_stems:
        raw = _raw_dir()
        wavs = [raw / f"{s}.wav" for s in batch_stems]
        wavs = [p for p in wavs if p.is_file()]
    if not wavs:
        raise SystemExit(f"raw 目录无 wav: {raw}")

    report: list[dict] = []
    t0 = time.time()
    for i, src in enumerate(wavs, 1):
        dst = out / src.name
        try:
            if args.mode == "auto":
                meta = trim_wav_auto(src, dst, threshold_db=args.threshold_db)
                score = loop_seam_score(dst)
                report.append({"file": src.name, "ok": True, **meta, "seam_db": score})
            elif args.mode == "optimize":
                meta = trim_wav_best_window(
                    src,
                    dst,
                    output_s=args.output_s,
                    margin_head=args.search_margin_head,
                    margin_tail=args.search_margin_tail,
                    step_ms=args.step_ms,
                    metric=args.optimize_metric,
                )
                score = loop_seam_score(dst)
                report.append({"file": src.name, "ok": True, **meta, "seam_db": score, "mode": "optimize"})
                print(
                    f"  {src.name}: start={meta['start_s']}s seam={score:.2f}dB "
                    f"(搜索 {meta['candidates']} 点, mel={meta['mel_diff']})"
                )
            else:
                dur = trim_wav_fixed(src, dst, head_s=args.trim_head, tail_s=args.trim_tail)
                score = loop_seam_score(dst)
                report.append({
                    "file": src.name,
                    "ok": True,
                    "duration_s": dur,
                    "seam_db": score,
                    "mode": "fixed",
                })
        except Exception as e:
            report.append({"file": src.name, "ok": False, "error": str(e)})
        else:
            if not getattr(args, "keep_raw", False) and _remove_temp_wav(src):
                print(f"  已删临时 raw: {src.name}")
        if i % 50 == 0 or i == len(wavs):
            print(f"  trim {i}/{len(wavs)} …")

    rep_path = _trim_report_path()
    rep_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in report if r.get("ok"))
    bad = [r for r in report if not r.get("ok")]
    print(f"裁切完成: {ok}/{len(report)} 成功，耗时 {time.time() - t0:.1f}s → {out}")
    if bad[:5]:
        print("失败样例:", bad[:5])
    return 0 if not bad else 1


def cmd_install(args: argparse.Namespace) -> int:
    trimmed = _trimmed_dir()
    sounds = _sounds_dir()
    manifest = _load_manifest()
    batch_stems = getattr(args, "batch_stems", None)
    if batch_stems:
        args.clear_sounds = False
    wavs = _installable_trimmed_wavs(manifest, args.limit, batch_stems=batch_stems)
    if not wavs:
        raise SystemExit(f"trimmed 目录无可用 wav，请先 trim: {trimmed}")

    ts = time.strftime("%Y%m%d_%H%M%S")
    backup = sounds.parent / f"sounds_bak_{ts}"
    if sounds.is_dir() and not args.skip_backup and any(sounds.glob("*.wav")):
        print(f"备份 {sounds} → {backup}")
        shutil.copytree(sounds, backup)

    if args.clear_sounds and sounds.is_dir():
        for old in sounds.glob("*.wav"):
            old.unlink()

    sounds.mkdir(parents=True, exist_ok=True)
    for src in wavs:
        shutil.copy2(src, sounds / src.name)

    print(f"已安装 {len(wavs)} 个 wav → {sounds}")
    if args.limit:
        print(f"（--limit {args.limit}，未全量覆盖）")

    if not getattr(args, "keep_temp", False):
        if args.limit or batch_stems:
            n = _cleanup_temp_wavs_for_names([w.name for w in wavs])
        else:
            n = _cleanup_all_temp_wavs()
        if n:
            print(f"已清理 {n} 个临时 wav（regen_raw / regen_trimmed）")
    return 0


def _run_batch_once(args: argparse.Namespace, batch_stems: list[str], batch_no: int, total_batches: int) -> int:
    print(f"\n{'=' * 60}")
    print(f"批次 {batch_no}/{total_batches}：{len(batch_stems)} 条")
    print(f"  首: {batch_stems[0]}")
    print(f"  尾: {batch_stems[-1]}")
    print(f"{'=' * 60}")

    batch_args = argparse.Namespace(**vars(args))
    batch_args.batch_stems = batch_stems
    batch_args.mode = "optimize"
    batch_args.threshold_db = getattr(args, "threshold_db", -42.0)
    batch_args.clear_sounds = False
    batch_args.skip_backup = True
    batch_args.offset = 0
    batch_args.limit = 0
    batch_args.batch_size = 0
    batch_args.skip_existing = getattr(args, "skip_existing", True)
    batch_args.reaper_exe = getattr(args, "reaper_exe", "")
    batch_args.keep_raw = getattr(args, "keep_raw", False)
    batch_args.keep_temp = getattr(args, "keep_temp", False)
    batch_args.optimize_metric = getattr(args, "optimize_metric", "combined")
    batch_args.output_s = getattr(args, "output_s", DEFAULT_OUTPUT_S)
    batch_args.search_margin_head = getattr(args, "search_margin_head", DEFAULT_SEARCH_MARGIN)
    batch_args.search_margin_tail = getattr(args, "search_margin_tail", DEFAULT_SEARCH_MARGIN)
    batch_args.step_ms = getattr(args, "step_ms", 50.0)
    batch_args.trim_head = getattr(args, "trim_head", 1.0)
    batch_args.trim_tail = getattr(args, "trim_tail", 1.0)
    batch_args.use_lua = getattr(args, "use_lua", True)

    for step_name, handler in (
        ("render", cmd_render),
        ("trim", cmd_trim),
        ("install", cmd_install),
    ):
        print(f"\n--- 批次 {batch_no} · {step_name} ---")
        rc = handler(batch_args)
        if rc != 0:
            print(f"批次 {batch_no} 在 {step_name} 失败 (exit {rc})")
            return rc

    done = len(_all_job_stems()) - len(_pending_stems())
    print(f"\n批次 {batch_no} 完成 · sounds 累计 {done}/{len(_all_job_stems())}")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    """分批 render → trim → install（每批默认 50 条，增量写入 sounds）。"""
    pending = _pending_stems()
    if not pending:
        print("全部已完成，sounds 无待处理条目")
        return 0

    total = len(_all_job_stems())
    batch_size = args.batch_size
    batches = [pending[i : i + batch_size] for i in range(0, len(pending), batch_size)]
    print(f"待处理 {len(pending)}/{total}，共 {len(batches)} 批（每批 {batch_size}）")

    run_batches = batches if args.all else batches[:1]
    for i, stems in enumerate(run_batches, 1):
        batch_no = (total - len(pending)) // batch_size + i
        rc = _run_batch_once(args, stems, batch_no, (total + batch_size - 1) // batch_size)
        if rc != 0:
            return rc
        if not args.all:
            remaining = len(_pending_stems())
            print(f"\n本批结束，剩余 {remaining} 条。继续: python3 -m scripts.video_analysis.regenerate_rain_sounds batch --size {batch_size}")
            break

    if args.all and not _pending_stems():
        print(f"\n全部分批完成 → {_sounds_dir()}")
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    """手动清理临时 regen wav（工程 tmp 及 baseURL 旧目录）。"""
    n = _cleanup_all_temp_wavs()
    layer = audio_dir() / LAYER_ID
    for name in ("regen_raw", "regen_trimmed"):
        n += _cleanup_temp_dir(layer / name)
    legacy = layer / "_regen_staging"
    if legacy.is_dir():
        n += _cleanup_temp_dir(legacy / "raw")
        n += _cleanup_temp_dir(legacy / "trimmed")
        try:
            if not any(legacy.iterdir()):
                legacy.rmdir()
                print(f"已移除旧目录 {legacy}")
        except OSError:
            pass
    print(f"cleanup 完成，删除 {n} 个临时 wav")
    return 0


def cmd_repair_trim(args: argparse.Namespace) -> int:
    """对现有 10s sounds 做静音裁切（不重新渲染 VST）。"""
    sounds = _sounds_dir()
    wavs = sorted(sounds.glob("*.wav"))
    if args.limit:
        wavs = wavs[: args.limit]
    if not wavs:
        raise SystemExit(f"无 wav: {sounds}")

    staging = _repair_dir()
    staging.mkdir(parents=True, exist_ok=True)
    report = []
    for src in wavs:
        dst = staging / src.name
        if args.dry_run:
            start_s, end_s = detect_silence_bounds(src, threshold_db=args.threshold_db)
            report.append({"file": src.name, "start_s": start_s, "end_s": end_s, "dry_run": True})
            continue
        meta = trim_wav_auto(src, dst, threshold_db=args.threshold_db)
        score = loop_seam_score(dst)
        report.append({**meta, "file": src.name, "seam_db": score})

    if not args.dry_run:
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup = sounds.parent / f"sounds_bak_repair_{ts}"
        print(f"备份 → {backup}")
        shutil.copytree(sounds, backup)
        for src in staging.glob("*.wav"):
            shutil.copy2(src, sounds / src.name)
        print(f"已就地替换 {len(list(staging.glob('*.wav')))} 个 wav")

    rep = _repair_report_path()
    rep.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告 → {rep}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    sounds = _sounds_dir()
    wavs = sorted(sounds.glob("*.wav"))
    if args.limit:
        wavs = wavs[: args.limit]
    scores = [(w.name, loop_seam_score(w)) for w in wavs]
    scores.sort(key=lambda x: x[1])
    bad = [s for s in scores if s[1] > args.max_seam_db]
    print(f"检测 {len(scores)} 个 wav，接缝差 > {args.max_seam_db} dB 的有 {len(bad)} 个")
    for name, sc in scores[:5]:
        print(f"  最无缝: {name} Δ{sc:.2f} dB")
    for name, sc in scores[-5:]:
        print(f"  最差: {name} Δ{sc:.2f} dB")
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    """prepare → render → trim → install（全量默认参数）。"""
    args.mode = "optimize"
    args.threshold_db = getattr(args, "threshold_db", -42.0)
    steps = (
        ("prepare", cmd_prepare),
        ("render", cmd_render),
        ("trim", cmd_trim),
        ("install", cmd_install),
    )
    for name, handler in steps:
        print(f"\n========== {name} ==========")
        rc = handler(args)
        if rc != 0:
            print(f"pipeline 在 {name} 步骤失败 (exit {rc})")
            return rc
    print("\n========== pipeline 完成 ==========")
    print(f"最终产物 → {_sounds_dir()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="重新生成 1_rain/sounds 无缝循环素材")
    sub = p.add_subparsers(dest="cmd", required=True)

    prep = sub.add_parser("prepare", help="生成 render_jobs + batch_render_regen.lua")
    prep.add_argument("--render-s", type=float, default=DEFAULT_RENDER_S, help="VST 渲染时长（秒）")
    prep.add_argument("--trim-head", type=float, default=1.0)
    prep.add_argument("--trim-tail", type=float, default=1.0)
    prep.add_argument("--output-s", type=float, default=DEFAULT_OUTPUT_S, help="optimize 目标成片时长")
    prep.add_argument("--search-margin-head", type=float, default=DEFAULT_SEARCH_MARGIN)
    prep.add_argument("--search-margin-tail", type=float, default=DEFAULT_SEARCH_MARGIN)
    prep.add_argument("--optimize-metric", choices=("combined", "seam", "mel"), default="combined")
    prep.add_argument("--limit", type=int, default=0, help="仅处理前 N 个 preset（测试）")
    prep.add_argument("--offset", type=int, default=0, help="跳过前 N 个 preset")

    ren = sub.add_parser("render", help="命令行调用 Reaper 渲染 render_jobs/*.rpp")
    ren.add_argument("--limit", type=int, default=0, help="仅渲染前 N 个")
    ren.add_argument("--offset", type=int, default=0, help="跳过前 N 个 job")
    ren.add_argument("--batch-size", type=int, default=0, help="每批 N 条后打印进度（如 50）")
    ren.add_argument("--skip-existing", action="store_true", default=True)
    ren.add_argument("--no-skip-existing", action="store_false", dest="skip_existing")
    ren.add_argument("--reaper-exe", default="", help="覆盖 gui/user_config.json 中的 reaper_exe")
    ren.add_argument("--use-lua", action="store_true", default=True, help="单 Reaper 进程 + batch_session.lua（默认）")
    ren.add_argument("--no-use-lua", action="store_false", dest="use_lua", help="逐条 -renderproject（慢）")

    tr = sub.add_parser("trim", help="regen_raw → regen_trimmed")
    tr.add_argument("--mode", choices=("fixed", "auto", "optimize"), default="optimize")
    tr.add_argument("--trim-head", type=float, default=1.0)
    tr.add_argument("--trim-tail", type=float, default=1.0)
    tr.add_argument("--output-s", type=float, default=DEFAULT_OUTPUT_S, help="optimize 目标成片时长")
    tr.add_argument("--search-margin-head", type=float, default=DEFAULT_SEARCH_MARGIN)
    tr.add_argument("--search-margin-tail", type=float, default=DEFAULT_SEARCH_MARGIN)
    tr.add_argument("--optimize-metric", choices=("combined", "seam", "mel"), default="combined")
    tr.add_argument("--step-ms", type=float, default=50.0, help="optimize 搜索步长（毫秒）")
    tr.add_argument("--threshold-db", type=float, default=-42.0)
    tr.add_argument("--limit", type=int, default=0)
    tr.add_argument("--keep-raw", action="store_true", help="裁切后保留 regen_raw")

    ins = sub.add_parser("install", help="regen_trimmed → sounds/（默认不备份）")
    ins.add_argument("--limit", type=int, default=0)
    ins.add_argument("--skip-backup", action="store_true", default=True)
    ins.add_argument("--backup", action="store_false", dest="skip_backup")
    ins.add_argument("--clear-sounds", action="store_true", default=True)
    ins.add_argument("--no-clear-sounds", action="store_false", dest="clear_sounds")
    ins.add_argument("--keep-temp", action="store_true", help="安装后保留 regen_trimmed/regen_raw")

    sub.add_parser("cleanup", help="清理工程 tmp 临时 regen wav")

    bat = sub.add_parser("batch", help="分批 render → trim → install（默认每批 50 条）")
    bat.add_argument("--size", type=int, default=50, dest="batch_size")
    bat.add_argument("--all", action="store_true", help="连续跑完所有剩余批次")
    bat.add_argument("--skip-existing", action="store_true", default=True)
    bat.add_argument("--no-skip-existing", action="store_false", dest="skip_existing")
    bat.add_argument("--reaper-exe", default="")
    bat.add_argument("--step-ms", type=float, default=50.0)
    bat.add_argument("--keep-raw", action="store_true")
    bat.add_argument("--keep-temp", action="store_true")
    bat.add_argument("--use-lua", action="store_true", default=True)
    bat.add_argument("--no-use-lua", action="store_false", dest="use_lua")

    rep = sub.add_parser("repair-trim", help="仅裁切现有 10s sounds（不重新渲染）")
    rep.add_argument("--threshold-db", type=float, default=-42.0)
    rep.add_argument("--limit", type=int, default=0)
    rep.add_argument("--dry-run", action="store_true")

    ver = sub.add_parser("verify", help="检测 sounds 首尾接缝 RMS 差")
    ver.add_argument("--limit", type=int, default=20)
    ver.add_argument("--max-seam-db", type=float, default=6.0)

    pipe = sub.add_parser("pipeline", help="prepare → render → trim → install")
    pipe.add_argument("--render-s", type=float, default=DEFAULT_RENDER_S)
    pipe.add_argument("--output-s", type=float, default=DEFAULT_OUTPUT_S)
    pipe.add_argument("--search-margin-head", type=float, default=DEFAULT_SEARCH_MARGIN)
    pipe.add_argument("--search-margin-tail", type=float, default=DEFAULT_SEARCH_MARGIN)
    pipe.add_argument("--optimize-metric", choices=("combined", "seam", "mel"), default="combined")
    pipe.add_argument("--limit", type=int, default=0)
    pipe.add_argument("--offset", type=int, default=0)
    pipe.add_argument("--batch-size", type=int, default=50)
    pipe.add_argument("--skip-existing", action="store_true", default=True)
    pipe.add_argument("--no-skip-existing", action="store_false", dest="skip_existing")
    pipe.add_argument("--reaper-exe", default="")
    pipe.add_argument("--step-ms", type=float, default=50.0)
    pipe.add_argument("--skip-backup", action="store_true", default=True)
    pipe.add_argument("--backup", action="store_false", dest="skip_backup")
    pipe.add_argument("--clear-sounds", action="store_true", default=True)
    pipe.add_argument("--no-clear-sounds", action="store_false", dest="clear_sounds")
    pipe.add_argument("--trim-head", type=float, default=1.0)
    pipe.add_argument("--trim-tail", type=float, default=1.0)
    pipe.add_argument("--keep-raw", action="store_true")
    pipe.add_argument("--keep-temp", action="store_true")

    return p


def main() -> int:
    args = build_parser().parse_args()
    handlers = {
        "prepare": cmd_prepare,
        "render": cmd_render,
        "trim": cmd_trim,
        "install": cmd_install,
        "repair-trim": cmd_repair_trim,
        "verify": cmd_verify,
        "pipeline": cmd_pipeline,
        "cleanup": cmd_cleanup,
        "batch": cmd_batch,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
