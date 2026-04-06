# TODO: compute cheap technical metrics
# aesthetic/agents/metrics.py
#
# Metrics engine — computes all per-frame measurements defined in
# AESTHETIC_Metric.md for a single candidate frame.
#
# Entry point: compute_frame_metrics(frame_path, scene_id, timestamp, config)
# Returns a fully populated FrameMetrics model.
# Writes a JSON sidecar to jobs/<job_id>/metrics/<frame_id>.json.
#
# All metrics are CPU-only in this implementation.
# GPU / model inference paths (CLIP, MiDaS, YOLO) are handled separately
# in Phase 6 and stored in FrameMetrics.inference.
#
# Design principles:
#   - Every metric degrades gracefully — a failure in one bundle does not
#     abort the others. Failed metrics are left as None.
#   - All scores are normalised to 0.0 - 100.0 where applicable.
#   - Raw measurement values are stored alongside scores where useful.

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from scipy import ndimage, signal
# skimage imported lazily inside functions to avoid lazy_loader version conflicts

from ..models.scores import (
    ExposureMetrics,
    LightingMetrics,
    CompositionMetrics,
    MovementMetrics,
    ColorMetrics,
    QualityMetrics,
    NarrativeMetrics,
    InferenceOutputs,
    FrameMetrics,
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_frame_metrics(
    frame_path: str,
    scene_id:   int,
    timestamp:  float,
    job_dir:    Path,
    config:     Dict[str, Any],
    prev_frame_path: Optional[str] = None,
) -> FrameMetrics:
    """
    Compute the full metrics bundle for a single candidate frame.

    Args:
        frame_path:      Path to the extracted JPEG frame on disk.
        scene_id:        Scene this frame belongs to.
        timestamp:       Timestamp in seconds from start of video.
        job_dir:         Job directory — sidecar is written to job_dir/metrics/.
        config:          Full config dict from config.yaml.
        prev_frame_path: Path to the previous frame in the scene (for motion metrics).
                         If None, motion metrics will be None.

    Returns:
        Populated FrameMetrics model.
    """
    path = Path(frame_path)
    frame_id = path.stem

    # load the frame — return empty FrameMetrics rather than raising
    # so the pipeline can continue even if individual frames are unreadable
    try:
        bgr = cv2.imread(str(path))
    except Exception:
        bgr = None
    if bgr is None:
        return FrameMetrics(
            frame_id=Path(frame_path).stem,
            scene_id=scene_id,
            timestamp=timestamp,
            frame_path=frame_path,
        )

    # load previous frame for motion metrics if available
    prev_bgr: Optional[np.ndarray] = None
    if prev_frame_path:
        prev_bgr = cv2.imread(str(prev_frame_path))

    # compute all bundles with graceful degradation
    exposure    = _safe(lambda: _compute_exposure(bgr),    ExposureMetrics())
    lighting    = _safe(lambda: _compute_lighting(bgr),    LightingMetrics())
    composition = _safe(lambda: _compute_composition(bgr), CompositionMetrics())
    movement    = _safe(lambda: _compute_movement(bgr, prev_bgr), MovementMetrics())
    color       = _safe(lambda: _compute_color(bgr),       ColorMetrics())
    quality     = _safe(lambda: _compute_quality(bgr),     QualityMetrics())
    narrative   = _safe(lambda: _compute_narrative(bgr),   NarrativeMetrics())

    metrics = FrameMetrics(
        frame_id=frame_id,
        scene_id=scene_id,
        timestamp=timestamp,
        frame_path=frame_path,
        exposure=exposure,
        lighting=lighting,
        composition=composition,
        movement=movement,
        color=color,
        quality=quality,
        narrative=narrative,
        inference=InferenceOutputs(),
    )

    _write_sidecar(metrics, job_dir)
    return metrics


def compute_scene_metrics(
    candidates: List[FrameMetrics],
) -> Dict[str, Optional[float]]:
    """
    Compute cross-frame temporal consistency metrics for a scene.
    Called after all per-frame metrics in a scene are computed.
    Returns a dict of metric_name -> value to merge into aggregation.
    """
    if not candidates:
        return {}

    results: Dict[str, Optional[float]] = {}

    # exposure temporal consistency — low std = consistent exposure
    means = [c.exposure.histogram_mean for c in candidates if c.exposure.histogram_mean is not None]
    if means:
        std = float(np.std(means))
        # invert and normalise: std of 0 = score 100, std of 128 = score 0
        results["exposure_temporal_consistency"] = round(max(0.0, 100.0 - (std / 128.0) * 100.0), 2)

    # color grading uniformity — low variance in white balance = consistent grade
    wb_devs = [c.color.wb_deviation for c in candidates if c.color.wb_deviation is not None]
    if wb_devs:
        variance = float(np.std(wb_devs))
        results["grading_uniformity"] = round(max(0.0, 100.0 - (variance / 50.0) * 100.0), 2)

    return results


# ---------------------------------------------------------------------------
# Exposure bundle
# ---------------------------------------------------------------------------

def _compute_exposure(bgr: np.ndarray) -> ExposureMetrics:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    flat = gray.flatten()

    mean   = float(np.mean(flat))
    median = float(np.median(flat))
    std    = float(np.std(flat))

    # skew and kurtosis
    if std > 0:
        skew     = float(np.mean(((flat - mean) / std) ** 3))
        kurtosis = float(np.mean(((flat - mean) / std) ** 4)) - 3.0
    else:
        skew, kurtosis = 0.0, 0.0

    # clipping: % of pixels at or near 0 (shadow clip) or 255 (highlight clip)
    shadow_clip_pct    = float(np.sum(flat <= 5)   / len(flat) * 100.0)
    highlight_clip_pct = float(np.sum(flat >= 250) / len(flat) * 100.0)

    # third moment about 18% gray (zone V = 118 in 0-255)
    zone_v = 118.0
    third_moment = float(np.mean(((flat - zone_v) / 255.0) ** 3))

    # SNR — signal = mean luminance, noise = std of local patches
    snr_luma = _compute_luma_snr(gray)

    # chroma SNR via Lab a* b* channels
    lab   = cv2.cvtColor(bgr, cv2.COLOR_BGR2Lab).astype(np.float32)
    snr_a = _channel_snr(lab[:, :, 1])
    snr_b = _channel_snr(lab[:, :, 2])
    snr_chroma = round((snr_a + snr_b) / 2.0, 2)

    # PSNR proxy (vs a smoothed reference of itself — no true reference available)
    blurred   = cv2.GaussianBlur(gray, (5, 5), 0)
    mse       = float(np.mean((gray - blurred) ** 2))
    psnr      = round(10.0 * np.log10((255.0 ** 2) / mse), 2) if mse > 0 else 60.0

    # SSIM proxy (vs smoothed self — structural integrity indicator)
    # skimage imported locally to avoid lazy_loader version conflicts at module load time
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from skimage.metrics import structural_similarity as _ssim_func
        ssim_val = float(_ssim_func(
            gray.astype(np.uint8),
            blurred.astype(np.uint8),
            data_range=255,
        ))

    # exposure intent — score based on how well the histogram fills the tonal range
    # without clipping. Penalise heavy clipping and narrow histograms.
    intent_penalty = (shadow_clip_pct * 1.5) + (highlight_clip_pct * 2.0)
    # reward a well-spread histogram (std close to 50-70 is ideal for most content)
    spread_score = min(100.0, (std / 64.0) * 100.0)
    exposure_intent = round(max(0.0, spread_score - intent_penalty), 2)

    return ExposureMetrics(
        histogram_mean=round(mean, 2),
        histogram_median=round(median, 2),
        histogram_std=round(std, 2),
        histogram_skew=round(skew, 4),
        histogram_kurtosis=round(kurtosis, 4),
        highlight_clip_pct=round(highlight_clip_pct, 3),
        shadow_clip_pct=round(shadow_clip_pct, 3),
        psnr=psnr,
        ssim=round(ssim_val * 100.0, 2),
        third_moment_18gray=round(third_moment, 6),
        snr_luma=snr_luma,
        snr_chroma=snr_chroma,
        exposure_intent=exposure_intent,
    )


def _compute_luma_snr(gray: np.ndarray) -> float:
    """Estimate luminance SNR using local patch variance."""
    # divide into 8x8 patches and compute signal/noise ratio
    h, w = gray.shape
    ph, pw = h // 8, w // 8
    if ph < 2 or pw < 2:
        return 0.0
    patches = gray[:ph*8, :pw*8].reshape(8, ph, 8, pw)
    patch_means = patches.mean(axis=(1, 3))
    patch_stds  = patches.std(axis=(1, 3))
    signal_val  = float(np.mean(patch_means))
    noise_val   = float(np.mean(patch_stds)) + 1e-6
    snr_db      = 20.0 * np.log10(signal_val / noise_val) if signal_val > 0 else 0.0
    return round(float(snr_db), 2)


def _channel_snr(channel: np.ndarray) -> float:
    """SNR for a single channel."""
    mean = float(np.mean(np.abs(channel)))
    std  = float(np.std(channel)) + 1e-6
    snr  = 20.0 * np.log10(mean / std) if mean > 0 else 0.0
    return round(float(snr), 2)


# ---------------------------------------------------------------------------
# Lighting bundle
# ---------------------------------------------------------------------------

def _compute_lighting(bgr: np.ndarray) -> LightingMetrics:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    lab  = cv2.cvtColor(bgr, cv2.COLOR_BGR2Lab).astype(np.float32)
    L    = lab[:, :, 0]  # 0-100

    # dynamic range in stops
    p2, p98    = np.percentile(L, 2), np.percentile(L, 98)
    dr_range   = float(p98 - p2)
    dr_stops   = round(np.log2(dr_range / 100.0 * 255.0 + 1.0), 2) if dr_range > 0 else 0.0

    # key to fill ratio estimate
    # use >= and <= so the masks are never empty even when pixels cluster at extremes
    p75         = float(np.percentile(L, 75))
    p25         = float(np.percentile(L, 25))
    bright_mask = L >= p75
    shadow_mask = L <= p25
    key_mean    = float(np.mean(L[bright_mask])) if bright_mask.any() else 0.0
    fill_mean   = float(np.mean(L[shadow_mask])) + 1.0 if shadow_mask.any() else 1.0
    key_fill    = round(key_mean / fill_mean, 2) if fill_mean > 1.0 else 0.0

    # color temperature estimate via blue/red channel ratio
    b_mean = float(np.mean(bgr[:, :, 0].astype(np.float32)))
    r_mean = float(np.mean(bgr[:, :, 2].astype(np.float32)))
    # rough CCT proxy: higher b/r = cooler
    br_ratio = (b_mean / (r_mean + 1e-6))
    # map to approximate Kelvin range 2000-10000
    color_temp = round(2000.0 + (br_ratio * 4000.0), 0)
    color_temp_deviation = round(abs(color_temp - 5600.0) / 5600.0 * 100.0, 2)

    # shadow detail — mean luminance and texture in shadow zones
    if shadow_mask.any():
        shadow_L     = L[shadow_mask]
        shadow_gray  = gray[shadow_mask]
        shadow_detail = round(float(np.mean(shadow_L)) / 100.0 * 100.0, 2)
        shadow_noise  = round(float(np.std(shadow_gray)), 2)
    else:
        shadow_detail = 0.0
        shadow_noise  = 0.0

    # hard vs soft transition — high gradient variance = hard light
    grad_x = cv2.Sobel(gray.astype(np.uint8), cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray.astype(np.uint8), cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.sqrt(grad_x**2 + grad_y**2)
    transition_hardness = round(min(100.0, float(np.std(grad_mag)) / 50.0 * 100.0), 2)

    # light motivation heuristic
    # motivated light has a clear directional source — look for strong gradients
    # in one quadrant vs the others
    h, w = gray.shape
    quadrants = [
        gray[:h//2, :w//2],
        gray[:h//2, w//2:],
        gray[h//2:, :w//2],
        gray[h//2:, w//2:],
    ]
    q_means = [float(np.mean(q)) for q in quadrants]
    q_std   = float(np.std(q_means))
    # high std across quadrants = directional, motivated light
    light_motivation = round(min(100.0, q_std / 30.0 * 100.0), 2)

    return LightingMetrics(
        dynamic_range_stops=dr_stops,
        key_fill_ratio=key_fill,
        color_temp_kelvin=color_temp,
        color_temp_deviation=color_temp_deviation,
        shadow_detail=shadow_detail,
        shadow_noise=shadow_noise,
        transition_hardness=transition_hardness,
        light_motivation=light_motivation,
    )


# ---------------------------------------------------------------------------
# Composition bundle
# ---------------------------------------------------------------------------

def _compute_composition(bgr: np.ndarray) -> CompositionMetrics:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = bgr.shape[:2]

    # rule of thirds — check if strong edges cluster near the thirds lines
    thirds_x = [w // 3, 2 * w // 3]
    thirds_y = [h // 3, 2 * h // 3]
    edges = cv2.Canny(gray.astype(np.uint8), 50, 150)

    # sample edge density within a band around each thirds line
    band = max(1, w // 20)
    thirds_density = 0.0
    for tx in thirds_x:
        col_slice = edges[:, max(0, tx-band):min(w, tx+band)]
        thirds_density += float(np.mean(col_slice))
    band_h = max(1, h // 20)
    for ty in thirds_y:
        row_slice = edges[max(0, ty-band_h):min(h, ty+band_h), :]
        thirds_density += float(np.mean(row_slice))
    thirds_density /= 4.0
    rule_of_thirds = round(min(100.0, thirds_density / 128.0 * 100.0), 2)

    # center of mass of luminance
    total_lum = float(np.sum(gray)) + 1e-6
    y_coords, x_coords = np.mgrid[0:h, 0:w]
    com_x = round(float(np.sum(x_coords * gray) / total_lum) / w, 4)
    com_y = round(float(np.sum(y_coords * gray) / total_lum) / h, 4)

    # negative space ratio — proportion of frame with below-median luminance
    median_lum = float(np.median(gray))
    negative_space = round(float(np.sum(gray < median_lum)) / gray.size * 100.0, 2)

    # occupancy map score — how well the frame is filled with content
    # (content = pixels with luminance significantly above background)
    background_thresh = float(np.percentile(gray, 20))
    content_mask = gray > (background_thresh * 1.5)
    occupancy_score = round(float(np.mean(content_mask)) * 100.0, 2)

    # symmetry score — compare left half to flipped right half
    mid = w // 2
    left  = gray[:, :mid]
    right = np.fliplr(gray[:, w-mid:])
    min_w = min(left.shape[1], right.shape[1])
    sym_diff = float(np.mean(np.abs(left[:, :min_w].astype(np.float32) -
                                    right[:, :min_w].astype(np.float32))))
    symmetry_score = round(max(0.0, 100.0 - (sym_diff / 128.0 * 100.0)), 2)

    # headroom — proportion of frame above the center of mass
    headroom = round((1.0 - com_y) * 100.0, 2)

    # lead room — distance of COM from center (horizontal)
    lead_room = round(abs(com_x - 0.5) * 200.0, 2)

    # frame balance — how close the center of luminance mass is to the
    # rule-of-thirds intersection points (score is higher when COM
    # is near a power point rather than dead center or at the very edge)
    thirds_points = [
        (1/3, 1/3), (2/3, 1/3),
        (1/3, 2/3), (2/3, 2/3),
    ]
    min_dist = min(
        ((com_x - px)**2 + (com_y - py)**2)**0.5
        for px, py in thirds_points
    )
    frame_balance = round(max(0.0, 100.0 - (min_dist / 0.5) * 100.0), 2)

    # face detection
    face_count, face_placement = _detect_faces(bgr, gray, h, w)

    # depth separation proxy — variance of a Laplacian pyramid
    # high variance in low-frequency bands suggests depth separation
    depth_separation = _estimate_depth_separation(gray)

    return CompositionMetrics(
        rule_of_thirds=rule_of_thirds,
        face_placement=face_placement,
        face_count=face_count,
        center_of_mass_x=com_x,
        center_of_mass_y=com_y,
        negative_space_ratio=negative_space,
        depth_separation=depth_separation,
        occupancy_map_score=occupancy_score,
        symmetry_score=symmetry_score,
        headroom=headroom,
        lead_room=lead_room,
        frame_balance=frame_balance,
    )


def _detect_faces(
    bgr: np.ndarray,
    gray: np.ndarray,
    h: int,
    w: int,
) -> Tuple[int, Optional[float]]:
    """
    Detect faces using OpenCV's Haar cascade.
    Returns (face_count, placement_score).
    placement_score is None if no faces are found.
    """
    try:
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces = cascade.detectMultiScale(
            gray.astype(np.uint8),
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
        )
        face_count = len(faces) if len(faces) > 0 else 0

        if face_count == 0:
            return 0, None

        # score face placement — reward faces near thirds intersection points
        thirds_points = [(w/3, h/3), (2*w/3, h/3), (w/3, 2*h/3), (2*w/3, 2*h/3)]
        best_score = 0.0
        for (fx, fy, fw, fh) in faces:
            face_cx = fx + fw / 2
            face_cy = fy + fh / 2
            for (tx, ty) in thirds_points:
                dist = ((face_cx - tx)**2 + (face_cy - ty)**2)**0.5
                max_dist = (w**2 + h**2)**0.5
                score = max(0.0, 100.0 - (dist / max_dist) * 100.0)
                best_score = max(best_score, score)

        return face_count, round(best_score, 2)

    except Exception:
        return 0, None


def _estimate_depth_separation(gray: np.ndarray) -> float:
    """
    Proxy for depth separation using Laplacian variance at multiple scales.
    High variance in a blurred version suggests foreground/background separation.
    """
    try:
        lap_sharp  = cv2.Laplacian(gray.astype(np.uint8), cv2.CV_32F)
        blurred    = cv2.GaussianBlur(gray.astype(np.uint8), (15, 15), 0)
        lap_blurred= cv2.Laplacian(blurred, cv2.CV_32F)
        ratio = float(np.var(lap_sharp)) / (float(np.var(lap_blurred)) + 1e-6)
        return round(min(100.0, ratio / 10.0 * 100.0), 2)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Camera movement bundle
# ---------------------------------------------------------------------------

def _compute_movement(
    bgr:      np.ndarray,
    prev_bgr: Optional[np.ndarray],
) -> MovementMetrics:
    if prev_bgr is None:
        return MovementMetrics()

    gray      = cv2.cvtColor(bgr,      cv2.COLOR_BGR2GRAY)
    prev_gray = cv2.cvtColor(prev_bgr, cv2.COLOR_BGR2GRAY)

    # optical flow — Farneback dense flow
    flow = cv2.calcOpticalFlowFarneback(
        prev_gray, gray,
        None,
        pyr_scale=0.5, levels=3, winsize=15,
        iterations=3, poly_n=5, poly_sigma=1.2,
        flags=0,
    )

    mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    flow_mean = round(float(np.mean(mag)), 4)
    flow_std  = round(float(np.std(mag)),  4)

    # smoothness — inverse of temporal jerkiness
    # jerkiness is high when flow magnitude varies a lot spatially
    jerkiness   = round(min(100.0, flow_std / (flow_mean + 1e-6) * 50.0), 2)
    smoothness  = round(max(0.0, 100.0 - jerkiness), 2)

    # stabilization proxy — look for residual high-frequency motion
    # after removing the dominant global motion
    global_flow = np.median(flow.reshape(-1, 2), axis=0)
    residual    = flow - global_flow
    res_mag     = np.sqrt(residual[..., 0]**2 + residual[..., 1]**2)
    stabilization = round(max(0.0, 100.0 - float(np.mean(res_mag)) * 10.0), 2)

    # motion blur amount via gradient frequency spectrum
    blur_amount = _estimate_motion_blur(gray)

    # motion blur direction via Radon transform proxy
    blur_direction = _estimate_blur_direction(gray)

    # movement type classification (rule-based)
    movement_type = _classify_movement(flow, flow_mean)

    # focus during movement — sharpness relative to motion magnitude
    sharpness = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    focus_during = round(min(100.0, sharpness / (1.0 + flow_mean * 10.0)), 2)

    # trajectory smoothness — how straight/curved the dominant flow vector is
    # (single frame comparison: always 100 unless we have a sequence)
    trajectory_smoothness = 100.0

    return MovementMetrics(
        optical_flow_mean=flow_mean,
        optical_flow_std=flow_std,
        smoothness=smoothness,
        jerkiness=jerkiness,
        stabilization=stabilization,
        motion_blur_amount=blur_amount,
        motion_blur_direction=blur_direction,
        movement_type=movement_type,
        focus_during_movement=focus_during,
        trajectory_smoothness=trajectory_smoothness,
    )


def _estimate_motion_blur(gray: np.ndarray) -> float:
    """
    Estimate motion blur amount via gradient spectrum analysis.
    A blurred image has less high-frequency energy.
    """
    try:
        f     = np.fft.fft2(gray.astype(np.float32))
        fshift= np.fft.fftshift(f)
        mag   = np.abs(fshift)
        h, w  = gray.shape
        # ratio of energy in high-frequency vs total
        cy, cx = h // 2, w // 2
        r = min(h, w) // 4
        mask = np.zeros_like(mag)
        cv2.circle(mask, (cx, cy), r, 1, -1)
        low_freq  = float(np.sum(mag *      mask))
        high_freq = float(np.sum(mag * (1 - mask)))
        total     = low_freq + high_freq + 1e-6
        blur_amount = round((low_freq / total) * 100.0, 2)
        return blur_amount
    except Exception:
        return 0.0


def _estimate_blur_direction(gray: np.ndarray) -> Optional[float]:
    """
    Estimate dominant blur direction using gradient orientation histogram.
    Returns angle in degrees (0-180), or None if no clear direction.
    """
    try:
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag_g, ang_g = cv2.cartToPolar(gx, gy, angleInDegrees=True)
        # weight angles by gradient magnitude
        hist, edges = np.histogram(ang_g.flatten(), bins=36, range=(0, 360),
                                   weights=mag_g.flatten())
        dominant_bin = int(np.argmax(hist))
        return round(float((edges[dominant_bin] + edges[dominant_bin+1]) / 2.0), 1)
    except Exception:
        return None


def _classify_movement(flow: np.ndarray, flow_mean: float) -> str:
    """
    Rule-based movement type classifier from optical flow.
    Returns a MovementType enum value string.
    """
    if flow_mean < 0.5:
        return "static"

    # dominant flow direction
    mean_dx = float(np.median(flow[..., 0]))
    mean_dy = float(np.median(flow[..., 1]))

    abs_dx = abs(mean_dx)
    abs_dy = abs(mean_dy)

    # flow variance (handheld has high local variance)
    flow_var = float(np.std(flow.reshape(-1, 2), axis=0).mean())

    if flow_var > 2.0:
        return "handheld"
    if abs_dx > abs_dy * 2:
        return "pan"
    if abs_dy > abs_dx * 2:
        return "tilt"
    if flow_mean > 1.5:
        return "dolly"
    return "unknown"


# ---------------------------------------------------------------------------
# Color bundle
# ---------------------------------------------------------------------------

def _compute_color(bgr: np.ndarray) -> ColorMetrics:
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2Lab).astype(np.float32)
    L, a, b = lab[:, :, 0], lab[:, :, 1], lab[:, :, 2]

    # white balance deviation — ideal WB has a* and b* near zero.
    # OpenCV encodes 8-bit Lab with a* and b* shifted by 128 so neutral = 128.
    # We subtract 128 to centre on zero before computing deviation.
    a_centered = a - 128.0
    b_centered = b - 128.0
    a_mean     = float(np.mean(a_centered))
    b_mean     = float(np.mean(b_centered))
    wb_deviation = round(float(np.sqrt(a_mean**2 + b_mean**2)), 3)

    # saturation in Lab (chroma = sqrt(a_centered^2 + b_centered^2))
    chroma = np.sqrt(a_centered**2 + b_centered**2)
    sat_mean        = round(float(np.mean(chroma)), 2)
    sat_uniformity  = round(max(0.0, 100.0 - float(np.std(chroma))), 2)

    # palette entropy — entropy of the hue histogram
    hsv     = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hue     = hsv[:, :, 0].flatten().astype(np.float32)
    hist, _ = np.histogram(hue, bins=36, range=(0, 180))
    hist    = hist.astype(np.float32) + 1e-6
    hist   /= hist.sum()
    entropy = float(-np.sum(hist * np.log2(hist)))
    palette_entropy = round(entropy, 4)

    # palette family classification
    palette_family = _classify_palette(bgr, hsv, sat_mean)

    # chroma noise — std of a* and b* channels
    chroma_noise = round(float((np.std(a) + np.std(b)) / 2.0), 2)

    # banding detection proxy — look for sudden luminance steps in L channel
    L_u8   = np.clip(L / 100.0 * 255.0, 0, 255).astype(np.uint8)
    banding = _detect_banding(L_u8)

    # ΔE2000 vs D65 neutral (a*=0, b*=0 in centred Lab = neutral grey)
    L_mean  = float(np.mean(L))
    delta_e = _compute_delta_e2000(L_mean, a_mean, b_mean, L_mean, 0.0, 0.0)

    return ColorMetrics(
        wb_deviation=wb_deviation,
        saturation_mean=sat_mean,
        saturation_uniformity=sat_uniformity,
        palette_entropy=palette_entropy,
        palette_family=palette_family,
        chroma_noise=chroma_noise,
        banding_score=banding,
        color_accuracy_de2000=delta_e,
    )


def _compute_delta_e2000(
    L1: float, a1: float, b1: float,
    L2: float, a2: float, b2: float,
) -> float:
    """
    ΔE2000 perceptual colour difference. a*/b* in centred form (neutral=0).
    <1 imperceptible · 1-2 just noticeable · 2-10 clearly different · >10 strong
    """
    import math
    kL = kC = kH = 1.0
    C1ab = math.sqrt(a1**2 + b1**2)
    C2ab = math.sqrt(a2**2 + b2**2)
    Cab7 = ((C1ab + C2ab) / 2.0) ** 7
    G    = 0.5 * (1.0 - math.sqrt(Cab7 / (Cab7 + 25.0**7)))
    a1p, a2p = a1 * (1.0 + G), a2 * (1.0 + G)
    C1p  = math.sqrt(a1p**2 + b1**2)
    C2p  = math.sqrt(a2p**2 + b2**2)
    h1p  = math.degrees(math.atan2(b1, a1p)) % 360.0
    h2p  = math.degrees(math.atan2(b2, a2p)) % 360.0
    dLp  = L2 - L1
    dCp  = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360.0
    else:
        dhp = h2p - h1p + 360.0
    dHp  = 2.0 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2.0))
    Lpm  = (L1 + L2) / 2.0
    Cpm  = (C1p + C2p) / 2.0
    if C1p * C2p == 0:
        hpm = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hpm = (h1p + h2p) / 2.0
    elif h1p + h2p < 360:
        hpm = (h1p + h2p + 360.0) / 2.0
    else:
        hpm = (h1p + h2p - 360.0) / 2.0
    T    = (1.0 - 0.17 * math.cos(math.radians(hpm - 30))
            + 0.24 * math.cos(math.radians(2 * hpm))
            + 0.32 * math.cos(math.radians(3 * hpm + 6))
            - 0.20 * math.cos(math.radians(4 * hpm - 63)))
    SL   = 1.0 + 0.015 * (Lpm - 50)**2 / math.sqrt(20 + (Lpm - 50)**2)
    SC   = 1.0 + 0.045 * Cpm
    SH   = 1.0 + 0.015 * Cpm * T
    Cpm7 = Cpm ** 7
    RC   = 2.0 * math.sqrt(Cpm7 / (Cpm7 + 25.0**7))
    dth  = 30.0 * math.exp(-((hpm - 275) / 25.0)**2)
    RT   = -math.sin(math.radians(2 * dth)) * RC
    dE   = math.sqrt((dLp/(kL*SL))**2 + (dCp/(kC*SC))**2 +
                     (dHp/(kH*SH))**2 + RT*(dCp/(kC*SC))*(dHp/(kH*SH)))
    return round(dE, 3)


def _classify_palette(
    bgr: np.ndarray,
    hsv: np.ndarray,
    sat_mean: float,
) -> str:
    """
    Classify the dominant color palette into a descriptive family.
    """
    hue    = hsv[:, :, 0].flatten().astype(np.float32)
    value  = hsv[:, :, 2].flatten().astype(np.float32)

    mean_hue   = float(np.mean(hue))
    mean_value = float(np.mean(value))

    if sat_mean < 15.0:
        return "desaturated"
    if mean_value < 60.0:
        return "dark"
    if mean_value > 200.0:
        return "bright"
    # warm: reds/oranges/yellows (hue 0-30 and 150-180 in OpenCV 0-180 range)
    warm_pct = float(np.sum((hue < 30) | (hue > 150)) / len(hue))
    cool_pct = float(np.sum((hue > 60) & (hue < 130)) / len(hue))
    if warm_pct > 0.5:
        return "warm"
    if cool_pct > 0.5:
        return "cool"
    return "neutral"


def _detect_banding(L_u8: np.ndarray) -> float:
    """
    Gradient-based banding proxy.
    Banding appears as repeated sharp horizontal or vertical steps
    in an otherwise smooth gradient.
    """
    try:
        grad_x = cv2.Sobel(L_u8, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(L_u8, cv2.CV_32F, 0, 1, ksize=3)
        # banding creates periodic spikes in one direction
        row_means = np.mean(np.abs(grad_y), axis=1)
        col_means = np.mean(np.abs(grad_x), axis=0)
        # look for periodicity via autocorrelation variance
        row_var = float(np.std(row_means))
        col_var = float(np.std(col_means))
        banding = round(min(100.0, (row_var + col_var) / 2.0), 2)
        return banding
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Image quality bundle
# ---------------------------------------------------------------------------

def _compute_quality(bgr: np.ndarray) -> QualityMetrics:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # sharpness — Laplacian variance (higher = sharper)
    lap      = cv2.Laplacian(gray, cv2.CV_32F)
    lap_var  = round(float(lap.var()), 2)

    # edge density
    edges       = cv2.Canny(gray, 50, 150)
    edge_density= round(float(np.mean(edges > 0)) * 100.0, 2)

    # MTF proxy — high-frequency energy ratio
    mtf_proxy = _compute_mtf_proxy(gray)

    # lens distortion proxy — straight line detection via Hough
    lens_distortion = _estimate_lens_distortion(gray)

    # vignetting — compare corner vs center brightness
    vignetting = _measure_vignetting(gray)

    # chromatic aberration — detect colour fringing at edges
    ca_width = _measure_ca(bgr, edges)

    # flare — detect bright overexposed regions near edges
    flare = _detect_flare(gray)

    # compression artifacts
    blocking, banding_q, mosquito, ringing = _detect_compression_artifacts(gray)

    # texture retention — local SSIM on high-texture regions
    texture_retention = _measure_texture_retention(gray)

    return QualityMetrics(
        sharpness_laplacian=lap_var,
        sharpness_edge_density=edge_density,
        mtf_proxy=mtf_proxy,
        lens_distortion=lens_distortion,
        vignetting_stops=vignetting,
        ca_width_px=ca_width,
        flare_contrast_loss=flare,
        compression_blocking=blocking,
        compression_banding=banding_q,
        compression_mosquito=mosquito,
        compression_ringing=ringing,
        texture_retention=texture_retention,
    )


def _compute_mtf_proxy(gray: np.ndarray) -> float:
    """High-frequency energy ratio as MTF proxy."""
    try:
        f     = np.fft.fft2(gray.astype(np.float32))
        fshift= np.fft.fftshift(f)
        mag   = np.abs(fshift)
        h, w  = gray.shape
        cy, cx= h // 2, w // 2
        r     = min(h, w) // 8
        mask  = np.zeros_like(mag)
        cv2.circle(mask, (cx, cy), r, 1, -1)
        low  = float(np.sum(mag * mask))
        high = float(np.sum(mag * (1 - mask)))
        return round(high / (low + high + 1e-6) * 100.0, 2)
    except Exception:
        return 0.0


def _estimate_lens_distortion(gray: np.ndarray) -> float:
    """
    Straight line detection proxy for lens distortion.
    Fewer/shorter straight lines detected = more distortion.
    """
    try:
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80,
                                minLineLength=gray.shape[1]//8, maxLineGap=10)
        if lines is None:
            return 50.0  # unknown — neutral score
        # score: more long straight lines = less distortion
        total_len = sum(
            ((x2-x1)**2 + (y2-y1)**2)**0.5
            for line in lines for x1, y1, x2, y2 in line
        )
        distortion = round(max(0.0, 100.0 - total_len / gray.shape[1]), 2)
        return distortion
    except Exception:
        return 50.0


def _measure_vignetting(gray: np.ndarray) -> float:
    """
    Measure vignetting as ratio of corner brightness to center brightness.
    Returns estimated stops of light loss from center to corner.
    """
    try:
        h, w   = gray.shape
        margin = min(h, w) // 8
        center = float(np.mean(gray[h//2-margin:h//2+margin, w//2-margin:w//2+margin]))
        corners= [
            gray[:margin, :margin],
            gray[:margin, -margin:],
            gray[-margin:, :margin],
            gray[-margin:, -margin:],
        ]
        corner_mean = float(np.mean([np.mean(c) for c in corners]))
        if center <= 0:
            return 0.0
        ratio = corner_mean / center
        stops = round(-np.log2(ratio + 1e-6), 2) if ratio > 0 else 0.0
        return max(0.0, float(stops))
    except Exception:
        return 0.0


def _measure_ca(bgr: np.ndarray, edges: np.ndarray) -> float:
    """
    Chromatic aberration proxy — measure colour channel misalignment at edges.
    """
    try:
        b, g, r = bgr[:, :, 0], bgr[:, :, 1], bgr[:, :, 2]
        # at edge pixels, compute RMS colour channel difference
        edge_mask = edges > 0
        if not edge_mask.any():
            return 0.0
        b_e = b[edge_mask].astype(np.float32)
        g_e = g[edge_mask].astype(np.float32)
        r_e = r[edge_mask].astype(np.float32)
        rg_diff = float(np.mean(np.abs(r_e - g_e)))
        bg_diff = float(np.mean(np.abs(b_e - g_e)))
        return round((rg_diff + bg_diff) / 2.0, 2)
    except Exception:
        return 0.0


def _detect_flare(gray: np.ndarray) -> float:
    """
    Detect veiling glare and flare as proportion of overexposed regions
    near the frame edges (where flare typically enters).
    """
    try:
        h, w   = gray.shape
        margin = min(h, w) // 6
        edge_region = np.concatenate([
            gray[:margin, :].flatten(),
            gray[-margin:, :].flatten(),
            gray[:, :margin].flatten(),
            gray[:, -margin:].flatten(),
        ])
        flare_pct = float(np.sum(edge_region > 240) / len(edge_region) * 100.0)
        return round(flare_pct, 3)
    except Exception:
        return 0.0


def _detect_compression_artifacts(gray: np.ndarray) -> Tuple[float, float, float, float]:
    """
    Detect four types of compression artifact.
    Returns (blocking, banding, mosquito, ringing) scores 0-100.
    Higher = more artifact present.
    """
    try:
        # blocking — DCT block boundary artifacts (8x8 pixel grid)
        blocking = _detect_blocking(gray)

        # banding — smooth gradients with visible steps
        banding = _detect_banding(gray)

        # mosquito — high-frequency noise around edges
        edges   = cv2.Canny(gray, 30, 100)
        dilated = cv2.dilate(edges, np.ones((5, 5), np.uint8))
        near_edge = dilated > 0
        if near_edge.any():
            lap   = np.abs(cv2.Laplacian(gray, cv2.CV_32F))
            mosquito = round(float(np.mean(lap[near_edge])) / 255.0 * 100.0, 2)
        else:
            mosquito = 0.0

        # ringing — oscillations near sharp edges (Gibbs phenomenon)
        kernel  = np.array([[-1, -1, -1], [-1, 8, -1], [-1, -1, -1]], dtype=np.float32)
        highpass= cv2.filter2D(gray.astype(np.float32), -1, kernel)
        ringing = round(min(100.0, float(np.std(highpass)) / 20.0 * 100.0), 2)

        return blocking, banding, mosquito, ringing
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


def _detect_blocking(gray: np.ndarray) -> float:
    """Detect DCT blocking artifacts by looking for 8-pixel boundary patterns."""
    try:
        h, w = gray.shape
        g    = gray.astype(np.float32)
        # vertical block boundaries
        v_diffs = []
        for x in range(8, w - 8, 8):
            diff = float(np.mean(np.abs(g[:, x] - g[:, x-1])))
            v_diffs.append(diff)
        # horizontal block boundaries
        h_diffs = []
        for y in range(8, h - 8, 8):
            diff = float(np.mean(np.abs(g[y, :] - g[y-1, :])))
            h_diffs.append(diff)
        if not v_diffs and not h_diffs:
            return 0.0
        all_diffs = v_diffs + h_diffs
        return round(min(100.0, float(np.mean(all_diffs)) / 20.0 * 100.0), 2)
    except Exception:
        return 0.0


def _measure_texture_retention(gray: np.ndarray) -> float:
    """
    Texture retention via local Laplacian variance on high-frequency mask.
    High-texture regions should have high local variance if detail is preserved.
    """
    try:
        blur   = cv2.GaussianBlur(gray, (5, 5), 0)
        diff   = cv2.absdiff(gray, blur)
        # high-texture mask: pixels with significant high-frequency content
        mask   = diff > 10
        if not mask.any():
            return 50.0
        lap    = cv2.Laplacian(gray, cv2.CV_32F)
        texture_var = float(np.var(lap[mask]))
        return round(min(100.0, texture_var / 500.0 * 100.0), 2)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Narrative and aesthetic bundle
# ---------------------------------------------------------------------------

def _compute_narrative(bgr: np.ndarray) -> NarrativeMetrics:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # saliency consistency proxy
    # Use OpenCV's static saliency to find salient regions
    # Score = how concentrated the saliency is (consistent attention point)
    saliency_consistency = _compute_saliency(gray)

    # compelling degree MOS — rule-based seed
    # Reward: high contrast, clear subject, good exposure
    lap_var  = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    exposure = float(np.mean(gray))
    contrast = float(np.std(gray))
    # normalise components
    sharpness_score  = min(100.0, lap_var / 500.0 * 100.0)
    exposure_score   = max(0.0, 100.0 - abs(exposure - 128.0) / 128.0 * 100.0)
    contrast_score   = min(100.0, contrast / 80.0 * 100.0)
    compelling_mos   = round((sharpness_score * 0.4 + exposure_score * 0.3 + contrast_score * 0.3), 2)

    return NarrativeMetrics(
        saliency_consistency=saliency_consistency,
        compelling_mos=compelling_mos,
    )


def _compute_saliency(gray: np.ndarray) -> float:
    """
    Compute saliency consistency using OpenCV's spectral residual method.
    Returns a score 0-100 where higher = more concentrated/consistent saliency.
    """
    try:
        saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
        success, saliency_map = saliency.computeSaliency(gray)
        if not success:
            return 50.0
        sal = saliency_map.astype(np.float32)
        # concentration: high max vs mean ratio = focused attention point
        sal_max  = float(np.max(sal))
        sal_mean = float(np.mean(sal)) + 1e-6
        concentration = min(100.0, (sal_max / sal_mean) * 10.0)
        return round(concentration, 2)
    except Exception:
        return 50.0


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe(fn, fallback):
    """
    Call fn() and return its result.
    On any exception, log the error and return fallback.
    """
    try:
        return fn()
    except Exception as exc:
        # in production this would go to the job logger
        # for now silently degrade — the field stays None
        return fallback


def _write_sidecar(metrics: FrameMetrics, job_dir: Path) -> None:
    """Write FrameMetrics to jobs/<job_id>/metrics/<frame_id>.json."""
    metrics_dir = job_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    out_path = metrics_dir / f"{metrics.frame_id}.json"
    out_path.write_text(
        json.dumps(metrics.to_sidecar_dict(), indent=2),
        encoding="utf-8",
    )