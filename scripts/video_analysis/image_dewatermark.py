"""图片去水印：默认去掉右上角平台水印；底部中英字幕先检测再去除。

面向素材库 raw 参考图（常见 bilibili「独播」角标 + 底部双语字幕）。

半透明 logo 必须罩住字心（凸包），不能只修笔画边缘，否则字还在。
字幕用不透明笔画遮罩。都用 LaMa 在带周围纹理的裁剪块上修，
遮罩内部 100% 用修复结果，只在外侧与原图过渡。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

LogFn = Callable[[str], None]

_LAMA = None
_LAMA_FAILED: str | None = None


@dataclass
class DewatermarkResult:
    output_path: Path
    removed_top_right: bool
    removed_subtitle: bool
    top_right_pixels: int = 0
    subtitle_pixels: int = 0


def _log(log_fn: LogFn | None, msg: str) -> None:
    if log_fn:
        log_fn(msg)


def detect_top_right_watermark_mask(bgr: np.ndarray) -> tuple[np.ndarray, bool, int]:
    """检测右上角半透明白色 logo/文字水印（如 bilibili 独播）。"""
    hh, ww = bgr.shape[:2]
    x0, y0 = int(ww * 0.62), 0
    x1, y1 = ww, int(hh * 0.22)
    roi = bgr[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    whiteish = ((hsv[:, :, 2] > 120) & (hsv[:, :, 1] < 100)).astype(np.uint8) * 255
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 28, 90)
    m = cv2.bitwise_and(
        cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), 1),
        whiteish,
    )
    m = cv2.morphologyEx(
        m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 9)), 1
    )
    num, labels, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    clean = np.zeros_like(m)
    roi_area = int(m.shape[0] * m.shape[1])
    for i in range(1, num):
        area = int(stats[i, cv2.CC_STAT_AREA])
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        if area < 80 or area > roi_area * 0.55:
            continue
        if bw < 36 or bh < 10:
            continue
        clean[labels == i] = 255
    px = int(clean.sum() // 255)
    if px < 280:
        return np.zeros((hh, ww), np.uint8), False, px
    # 只扩一圈光晕，避免盖住整片树叶
    clean = cv2.dilate(clean, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 5)), 1)
    mask = np.zeros((hh, ww), np.uint8)
    mask[y0:y1, x0:x1] = clean
    return mask, True, px


def detect_bottom_subtitle_mask(bgr: np.ndarray) -> tuple[np.ndarray, bool, int]:
    """检测底部中英字幕（白字黑描边）；无字幕返回空 mask。"""
    hh, ww = bgr.shape[:2]
    y0 = int(hh * 0.70)
    roi = bgr[y0:hh]
    rh, rw = roi.shape[:2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    white = ((hsv[:, :, 2] > 175) & (hsv[:, :, 1] < 90)).astype(np.uint8) * 255
    white = cv2.morphologyEx(
        white, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 2)), 1
    )
    dil = cv2.dilate(white, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), 1)
    ring = cv2.subtract(dil, white)
    dark = (gray < 110).astype(np.uint8) * 255
    outlined = cv2.bitwise_and(ring, dark)
    near = cv2.dilate(outlined, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)), 1)
    cand = cv2.bitwise_and(white, near)

    mid = cand[:, int(rw * 0.12) : int(rw * 0.88)]
    proj = (mid > 0).sum(axis=1).astype(np.float64)
    if float(proj.max()) < 60:
        return np.zeros((hh, ww), np.uint8), False, 0

    proj_s = np.convolve(proj, np.ones(7) / 7, mode="same")
    peaks: list[int] = []
    for i in range(3, rh - 3):
        if (
            proj_s[i] >= proj_s[i - 1]
            and proj_s[i] >= proj_s[i + 1]
            and proj_s[i] > max(50.0, float(proj_s.max()) * 0.35)
            and proj_s[i] >= proj_s[i - 2]
            and proj_s[i] >= proj_s[i + 2]
        ):
            peaks.append(i)

    merged: list[int] = []
    for i in peaks:
        if merged and i - merged[-1] <= 12:
            if proj_s[i] > proj_s[merged[-1]]:
                merged[-1] = i
        else:
            merged.append(i)

    lower = [p for p in merged if p >= int(rh * 0.22)]
    lower = sorted(lower, key=lambda i: -proj_s[i])[:3]
    lower = sorted(lower)
    if not lower:
        return np.zeros((hh, ww), np.uint8), False, 0

    # 笔画 + 描边；只扩 1 圈，保留字与字之间的真实纹理
    stroke = cv2.bitwise_or(cand, outlined)
    stroke = cv2.dilate(stroke, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), 1)
    a = max(0, min(lower) - 16)
    b = min(rh - 1, max(lower) + 18)
    band = stroke[a : b + 1]
    cols = (band > 0).sum(axis=0)
    xs = np.where(cols > 4)[0]
    if len(xs) == 0:
        return np.zeros((hh, ww), np.uint8), False, 0
    xa = max(0, int(xs.min()) - 10)
    xb = min(rw - 1, int(xs.max()) + 10)
    gate = np.zeros((rh, rw), np.uint8)
    gate[a : b + 1, xa : xb + 1] = 255
    stroke = cv2.bitwise_and(stroke, gate)
    stroke[:, : int(rw * 0.05)] = 0
    stroke[:, int(rw * 0.95) :] = 0

    full = np.zeros((hh, ww), np.uint8)
    full[y0:hh] = stroke
    px = int(full.sum() // 255)
    if px < 400:
        return np.zeros((hh, ww), np.uint8), False, px
    return full, True, px


def _prepare_inpaint_mask(mask: np.ndarray, *, dilate: int, close: tuple[int, int] | None) -> np.ndarray:
    """略扩并闭合笔画空洞，让 LaMa 按色块修而不是按字形修。"""
    k = max(int(dilate), 1)
    if k % 2 == 0:
        k += 1
    out = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)), 1)
    if close is not None:
        cw, ch = close
        out = cv2.morphologyEx(
            out, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (cw, ch)), 1
        )
    return out


def _solid_logo_mask(edge_mask: np.ndarray) -> np.ndarray:
    """把半透明 logo 的字心也罩住：笔画凸包 + 光晕，避免只修边缘留下整段字。"""
    ys, xs = np.where(edge_mask > 0)
    if len(xs) == 0:
        return edge_mask
    # 限制在检测框附近，避免凸包把远处亮斑连进来
    x, y, bw, bh = cv2.boundingRect(edge_mask)
    pad_x, pad_y = 18, 14
    h, w = edge_mask.shape
    gate = np.zeros_like(edge_mask)
    gate[
        max(0, y - pad_y) : min(h, y + bh + pad_y),
        max(0, x - pad_x) : min(w, x + bw + pad_x),
    ] = 255
    pts = np.stack([xs, ys], axis=1).astype(np.int32)
    filled = np.zeros_like(edge_mask)
    cv2.fillConvexPoly(filled, cv2.convexHull(pts), 255)
    filled = cv2.bitwise_and(filled, gate)
    filled = cv2.dilate(filled, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 13)), 1)
    filled = cv2.GaussianBlur(filled, (11, 11), 0)
    _, filled = cv2.threshold(filled, 50, 255, cv2.THRESH_BINARY)
    return filled


def _get_lama(log_fn: LogFn | None = None):
    global _LAMA, _LAMA_FAILED
    if _LAMA is not None:
        return _LAMA
    if _LAMA_FAILED is not None:
        return None
    try:
        import torch
        from simple_lama_inpainting import SimpleLama

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        _log(log_fn, f"加载 LaMa 修复模型（{device}）…")
        _LAMA = SimpleLama(device)
        return _LAMA
    except Exception as exc:  # noqa: BLE001
        _LAMA_FAILED = str(exc)
        _log(log_fn, f"LaMa 不可用，将回退 OpenCV inpaint：{exc}")
        return None


def _blend_inside_mask(
    original: np.ndarray, filled: np.ndarray, mask: np.ndarray, fade: int = 6
) -> np.ndarray:
    """遮罩内部 100% 用 filled；仅在外侧 fade 像素与原图过渡。"""
    inner = (mask > 0).astype(np.uint8)
    if not inner.any():
        return original
    dist_out = cv2.distanceTransform((inner == 0).astype(np.uint8), cv2.DIST_L2, 3)
    alpha = np.clip(1.0 - dist_out / max(float(fade), 1.0), 0.0, 1.0)
    alpha[inner > 0] = 1.0
    k = fade if fade % 2 == 1 else fade + 1
    if k >= 3:
        alpha = cv2.GaussianBlur(alpha, (k, k), 0)
        alpha[inner > 0] = 1.0
    a = np.clip(alpha, 0.0, 1.0)[:, :, None]
    return np.clip(
        original.astype(np.float32) * (1.0 - a) + filled.astype(np.float32) * a,
        0,
        255,
    ).astype(np.uint8)


def _lama_inpaint_region(
    bgr: np.ndarray,
    mask: np.ndarray,
    lama,
    *,
    pad: int = 180,
    fade: int = 6,
) -> np.ndarray:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return bgr
    h, w = bgr.shape[:2]
    x0 = max(0, int(xs.min()) - pad)
    x1 = min(w, int(xs.max()) + pad + 1)
    y0 = max(0, int(ys.min()) - pad)
    y1 = min(h, int(ys.max()) + pad + 1)
    crop = bgr[y0:y1, x0:x1]
    crop_mask = mask[y0:y1, x0:x1]
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).copy()
    rgb[crop_mask > 0] = 0
    arr = np.array(lama(rgb, crop_mask))
    arr = arr[: crop.shape[0], : crop.shape[1]]
    filled = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    blended = _blend_inside_mask(crop, filled, crop_mask, fade=fade)
    out = bgr.copy()
    out[y0:y1, x0:x1] = blended
    return out


def _opencv_inpaint_region(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """LaMa 不可用时的窄笔画回退，半径保持很小以免抹糊。"""
    if not mask.any():
        return bgr
    radius = 3
    filled = cv2.inpaint(bgr, mask, radius, cv2.INPAINT_NS)
    return _blend_inside_mask(bgr, filled, mask, fade=4)


def _inpaint(bgr: np.ndarray, mask: np.ndarray, lama, *, pad: int, fade: int) -> np.ndarray:
    if not mask.any():
        return bgr
    if lama is not None:
        return _lama_inpaint_region(bgr, mask, lama, pad=pad, fade=fade)
    return _opencv_inpaint_region(bgr, mask)


def resolve_clean_output_path(src: Path) -> Path:
    """同目录输出 ``*_clean.ext``；若输入已是 clean，则覆盖自身。"""
    stem = src.stem
    if stem.endswith("_clean"):
        return src
    return src.with_name(f"{stem}_clean{src.suffix.lower()}")


def remove_image_watermarks(
    image_path: Path | str,
    *,
    output_path: Path | str | None = None,
    remove_top_right: bool = True,
    remove_subtitles: bool = True,
    log_fn: LogFn | None = None,
) -> DewatermarkResult:
    """对单张图片去水印，写到 ``*_clean`` 文件并返回结果摘要。"""
    src = Path(image_path)
    if not src.is_file():
        raise FileNotFoundError(f"图片不存在：{src}")

    data = np.fromfile(str(src), dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError(f"无法读取图片：{src}")

    out = bgr
    removed_tr = False
    removed_sub = False
    tr_px = 0
    sub_px = 0
    lama = None

    if remove_top_right:
        tr_mask, hit, tr_px = detect_top_right_watermark_mask(bgr)
        if hit:
            if lama is None:
                lama = _get_lama(log_fn)
            work = _solid_logo_mask(tr_mask)
            _log(log_fn, f"检测到右上角水印（约 {tr_px} px），正在去除")
            out = _inpaint(out, work, lama, pad=240, fade=6)
            tr2, still, _ = detect_top_right_watermark_mask(out)
            if still:
                _log(log_fn, "右上角仍有残留，再去一次")
                out = _inpaint(out, _solid_logo_mask(tr2), lama, pad=200, fade=5)
            removed_tr = True
        else:
            _log(log_fn, "未检测到右上角水印，跳过")

    if remove_subtitles:
        sub_mask, hit, sub_px = detect_bottom_subtitle_mask(bgr)
        if hit:
            if lama is None:
                lama = _get_lama(log_fn)
            work = _prepare_inpaint_mask(sub_mask, dilate=7, close=(15, 9))
            _log(log_fn, f"检测到底部字幕（约 {sub_px} px），正在去除")
            out = _inpaint(out, work, lama, pad=220, fade=6)
            sub2, still, _ = detect_bottom_subtitle_mask(out)
            if still:
                _log(log_fn, "字幕仍有残留，再去一次")
                out = _inpaint(
                    out, _prepare_inpaint_mask(sub2, dilate=7, close=(15, 9)), lama, pad=200, fade=5
                )
            removed_sub = True
        else:
            _log(log_fn, "未检测到底部字幕，跳过")

    out_path = Path(output_path) if output_path else resolve_clean_output_path(src)
    if not removed_tr and not removed_sub:
        _log(log_fn, "无需处理：未发现可去除的水印/字幕")
        if out_path.resolve() != src.resolve():
            out_path.write_bytes(src.read_bytes())
        return DewatermarkResult(
            output_path=out_path,
            removed_top_right=False,
            removed_subtitle=False,
            top_right_pixels=tr_px,
            subtitle_pixels=sub_px,
        )

    suffix = out_path.suffix.lower()
    ext = ".png" if suffix == ".png" else ".jpg"
    ok, buf = cv2.imencode(
        ext, out, [int(cv2.IMWRITE_JPEG_QUALITY), 95] if ext == ".jpg" else []
    )
    if not ok:
        raise RuntimeError(f"编码输出失败：{out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    buf.tofile(str(out_path))
    _log(log_fn, f"已保存：{out_path.name}")
    return DewatermarkResult(
        output_path=out_path,
        removed_top_right=removed_tr,
        removed_subtitle=removed_sub,
        top_right_pixels=tr_px,
        subtitle_pixels=sub_px,
    )


__all__ = [
    "DewatermarkResult",
    "detect_top_right_watermark_mask",
    "detect_bottom_subtitle_mask",
    "resolve_clean_output_path",
    "remove_image_watermarks",
]
