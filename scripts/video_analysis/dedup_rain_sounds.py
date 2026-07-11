#!/usr/bin/env python3
"""对 baseURL/audio/1_rain/sounds 做感知特征聚类去重（方案 B）。

1. 备份 audio/1_rain → audio/1_rain_bak
2. MFCC + 谱特征 → 标准化 → 凝聚聚类（cosine）
3. 每簇保留距簇中心最近的 WAV，其余移入 dedup_removed/

用法（仓库根目录）:
  python3 -m scripts.video_analysis.dedup_rain_sounds
  python3 -m scripts.video_analysis.dedup_rain_sounds --distance 0.15 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.config.paths import audio_dir, audio_layer_dir, material_dir  # noqa: E402

LAYER_ID = "1_rain"
BACKUP_NAME = "1_rain_bak"
REMOVED_DIRNAME = "dedup_removed"
REPORT_NAME = "1_rain_dedup_report.json"
FEATURES_CACHE_NAME = "1_rain_dedup_features.npz"
MAX_DURATION_S = 10.0
TARGET_SR = 22000
N_MFCC = 20
DEFAULT_DISTANCE = 0.02


@dataclass
class WavFeature:
    path: str
    name: str
    vector: list[float]


def _layer_root() -> Path:
    return audio_dir() / LAYER_ID


def _backup_root() -> Path:
    return audio_dir() / BACKUP_NAME


def _sounds_dir() -> Path:
    return audio_layer_dir(LAYER_ID)


def _extract_feature(path: Path) -> WavFeature | None:
    import librosa

    try:
        y, sr = librosa.load(
            path,
            sr=TARGET_SR,
            mono=True,
            duration=MAX_DURATION_S,
            res_type="kaiser_fast",
        )
        if y.size < TARGET_SR // 2:
            return None

        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=N_MFCC)
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)
        rms = librosa.feature.rms(y=y)

        parts = []
        for block in (mfcc, centroid, bandwidth, rolloff, rms):
            parts.append(block.mean(axis=1))
            parts.append(block.std(axis=1))
        vec = np.concatenate(parts).astype(np.float64)
        vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
        return WavFeature(path=str(path), name=path.name, vector=vec.tolist())
    except Exception:
        return None


def _backup_layer(*, force: bool) -> Path:
    src = _layer_root()
    dst = _backup_root()
    sounds = src / "sounds"
    if not sounds.is_dir():
        raise SystemExit(f"源目录不存在: {sounds}")

    wav_count = len(list(sounds.glob("*.wav")))
    if dst.exists():
        bak_sounds = dst / "sounds"
        bak_count = len(list(bak_sounds.glob("*.wav"))) if bak_sounds.is_dir() else 0
        if not force and bak_count >= wav_count and wav_count > 0:
            print(f"备份已存在且不少于源库 ({bak_count} ≥ {wav_count})，跳过: {dst}")
            return dst
        if force:
            print(f"删除旧备份: {dst}")
            shutil.rmtree(dst)

    print(f"备份 {src} → {dst}（{wav_count} 个 wav，请稍候）…")
    t0 = time.time()
    shutil.copytree(src, dst)
    print(f"备份完成，耗时 {time.time() - t0:.1f}s")
    return dst


def _build_matrix(items: list[WavFeature]) -> np.ndarray:
    from sklearn.preprocessing import StandardScaler

    X = np.array([it.vector for it in items], dtype=np.float64)
    return StandardScaler().fit_transform(X)


def _load_or_extract_features(
    wavs: list[Path],
    *,
    workers: int,
    cache_path: Path,
) -> tuple[list[WavFeature], list[str]]:
    if cache_path.is_file():
        data = np.load(cache_path, allow_pickle=True)
        names = data["names"].tolist()
        vectors = data["vectors"]
        print(f"加载特征缓存: {cache_path} ({len(names)} 条)")
        items = [
            WavFeature(path="", name=n, vector=v.tolist())
            for n, v in zip(names, vectors)
        ]
        return items, []

    print(f"提取特征（workers={workers}，每文件前 {MAX_DURATION_S}s）…")
    t0 = time.time()
    items: list[WavFeature] = []
    failed: list[str] = []

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_extract_feature, p): p for p in wavs}
        done = 0
        for fut in as_completed(futures):
            done += 1
            if done % 200 == 0 or done == len(wavs):
                print(f"  特征进度 {done}/{len(wavs)}")
            path = futures[fut]
            feat = fut.result()
            if feat is None:
                failed.append(path.name)
            else:
                items.append(feat)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        cache_path,
        names=[it.name for it in items],
        vectors=np.array([it.vector for it in items], dtype=np.float64),
    )
    print(f"特征缓存已写入: {cache_path}")
    print(f"特征完成，耗时 {time.time() - t0:.1f}s，有效 {len(items)}，失败 {len(failed)}")
    return items, failed


def _cluster(
    items: list[WavFeature],
    *,
    distance: float,
) -> tuple[list[int], int]:
    from sklearn.cluster import AgglomerativeClustering

    X = _build_matrix(items)
    model = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance,
        metric="cosine",
        linkage="average",
    )
    labels = model.fit_predict(X)
    return labels.tolist(), int(labels.max()) + 1


def _pick_keepers(
    items: list[WavFeature],
    labels: list[int],
) -> tuple[list[str], dict[str, list[str]]]:
    X = _build_matrix(items)
    keepers: list[str] = []
    clusters: dict[str, list[str]] = {}

    by_label: dict[int, list[int]] = {}
    for i, lb in enumerate(labels):
        by_label.setdefault(lb, []).append(i)

    for lb, idxs in sorted(by_label.items()):
        sub = X[idxs]
        center = sub.mean(axis=0)
        dists = 1.0 - (sub @ center) / (
            np.linalg.norm(sub, axis=1) * (np.linalg.norm(center) + 1e-9) + 1e-9
        )
        best_local = idxs[int(np.argmin(dists))]
        keeper_name = items[best_local].name
        keepers.append(keeper_name)
        member_names = [items[i].name for i in idxs]
        clusters[str(lb)] = member_names

    return keepers, clusters


def _apply_dedup(
    sounds: Path,
    layer_root: Path,
    keepers: set[str],
    *,
    dry_run: bool,
) -> tuple[int, int]:
    removed_dir = layer_root / REMOVED_DIRNAME
    if not dry_run:
        removed_dir.mkdir(parents=True, exist_ok=True)

    kept = removed = 0
    for wav in sorted(sounds.glob("*.wav")):
        if wav.name in keepers:
            kept += 1
            continue
        removed += 1
        dest = removed_dir / wav.name
        if dry_run:
            continue
        if dest.exists():
            dest.unlink()
        shutil.move(str(wav), str(dest))
    return kept, removed


def main() -> None:
    parser = argparse.ArgumentParser(description="1_rain/sounds 感知聚类去重")
    parser.add_argument(
        "--distance",
        type=float,
        default=DEFAULT_DISTANCE,
        help=f"凝聚聚类 cosine 距离阈值（越大合并越激进，默认 {DEFAULT_DISTANCE}）",
    )
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 4))
    parser.add_argument("--dry-run", action="store_true", help="只分析不移动文件")
    parser.add_argument("--force-backup", action="store_true", help="强制重建备份目录")
    parser.add_argument("--skip-backup", action="store_true", help="跳过备份（不推荐）")
    args = parser.parse_args()

    sounds = _sounds_dir()
    layer_root = _layer_root()
    wavs = sorted(sounds.glob("*.wav"))
    if not wavs:
        raise SystemExit(f"未找到 wav: {sounds}")

    print(f"源目录: {sounds}")
    print(f"共 {len(wavs)} 个 wav")

    if not args.skip_backup:
        _backup_layer(force=args.force_backup)

    cache_path = material_dir() / FEATURES_CACHE_NAME
    items, failed = _load_or_extract_features(
        wavs, workers=args.workers, cache_path=cache_path
    )
    if failed:
        print(f"警告: {len(failed)} 个文件特征提取失败，将保留不删")

    print(f"聚类 cosine distance_threshold={args.distance} …")
    labels, n_clusters = _cluster(items, distance=args.distance)
    keepers_list, clusters = _pick_keepers(items, labels)
    keeper_set = set(keepers_list)
    # 特征失败的文件一律保留
    keeper_set.update(failed)

    kept, removed = _apply_dedup(sounds, layer_root, keeper_set, dry_run=args.dry_run)

    report = {
        "layer": LAYER_ID,
        "sounds_dir": str(sounds),
        "backup_dir": str(_backup_root()),
        "total_wavs": len(wavs),
        "features_cache": str(cache_path),
        "feature_ok": len(items),
        "feature_failed": failed,
        "distance_threshold": args.distance,
        "n_clusters": n_clusters,
        "keepers_count": len(keeper_set),
        "kept_in_sounds": kept,
        "removed_count": removed,
        "dry_run": args.dry_run,
        "clusters": clusters,
        "keepers": sorted(keeper_set),
    }
    report_path = material_dir() / REPORT_NAME
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("—— 结果 ——")
    print(f"簇数: {n_clusters}")
    print(f"保留: {len(keeper_set)}（sounds 中 {kept}）")
    print(f"移出: {removed} → {layer_root / REMOVED_DIRNAME}")
    print(f"报告: {report_path}")
    if args.dry_run:
        print("（dry-run：未移动文件）")


if __name__ == "__main__":
    main()
