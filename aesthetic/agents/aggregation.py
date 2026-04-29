# aesthetic/agents/aggregation.py
#
# Shot score aggregation.
# Takes a list of FrameMetrics for a single scene and collapses them
# into a single ShotScore model.
#
# Key design decisions:
#   - Stable metrics (exposure, composition, color) use weighted mean
#     with outlier down-weighting via IQR trimming
#   - Motion metrics are scored as a sequence across frames, not per-frame
#   - Temporal variance is computed and stored as an explicit signal —
#     high variance within a shot is itself a negative indicator
#   - Missing metrics (None) are excluded from aggregation rather than
#     treated as zero — partial data produces honest partial scores
#   - Category totals are computed from pillar subtotals using config weights

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import numpy as np
from pathlib import Path
import cv2

from ..models.scores import (
    CategoryScore,
    FrameMetrics,
    ShotScore,
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def is_non_cinematic_scene(frames: List[FrameMetrics], threshold: float = 0.6) -> bool:
    """
    Return True if the majority of frames in a scene look like title cards,
    credits, logos, or static graphics rather than cinematic content.

    Checks raw per-frame metrics before any aggregation so technically sharp
    text cards don't sneak through the scoring pipeline.

    A scene is flagged if more than `threshold` fraction of its frames
    fail at least 3 of 5 cinematic content signals.
    """
    if not frames:
        return False

    flagged = 0
    for f in frames:
        signals_failed = 0

        # low color entropy — title cards have very few distinct hues
        entropy = f.color.palette_entropy
        if entropy is not None and entropy < 2.8:
            signals_failed += 1

        # low saturation — black/white/grey dominates
        sat = f.color.saturation_mean
        if sat is not None and sat < 10.0:
            signals_failed += 1

        # flat image — no depth at all
        depth = f.composition.depth_separation
        if depth is not None and depth < 4.0:
            signals_failed += 1

        # sparse content — little meaningful content in frame
        occ = f.composition.occupancy_map_score
        if occ is not None and occ < 12.0:
            signals_failed += 1

        # low histogram std — near-uniform tone (black bg or white bg)
        hist_std = f.exposure.histogram_std
        if hist_std is not None and hist_std < 18.0:
            signals_failed += 1

        if signals_failed >= 3:
            flagged += 1

    return (flagged / len(frames)) >= threshold


def aggregate_shot(
    shot_id:  str,
    scene_id: int,
    frames:   List[FrameMetrics],
    config:   Dict[str, Any],
) -> ShotScore:
    """
    Aggregate a list of FrameMetrics for one scene into a ShotScore.

    Args:
        shot_id:  Unique shot identifier.
        scene_id: Scene this shot belongs to.
        frames:   All FrameMetrics for candidate frames in this scene.
        config:   Full config dict — used for pillar and category weights.

    Returns:
        Populated ShotScore with Technical pillar subtotal and category breakdowns.
        Creative and Subjective pillars are populated in Phase 7 after baseline scoring.
        Returns a near-zero score if the scene is detected as non-cinematic content.
    """
    if not frames:
        return ShotScore(shot_id=shot_id, scene_id=scene_id)

    # filter title cards, credits, logos before scoring
    if is_non_cinematic_scene(frames):
        return ShotScore(
            shot_id=shot_id,
            scene_id=scene_id,
            total_score=0.0,
            technical_total=0.0,
            frame_count=len(frames),
        )

    weights = config.get("weights", {})
    w_tech  = float(weights.get("technical",  0.50))
    w_creat = float(weights.get("creative",   0.30))
    w_subj  = float(weights.get("subjective", 0.20))

    cat_weights = config.get("category_weights", {
        "exposure":    0.18,
        "lighting":    0.18,
        "composition": 0.18,
        "movement":    0.14,
        "color":       0.14,
        "quality":     0.10,
        "narrative":   0.08,
    })

    exposure    = _aggregate_exposure(frames)
    lighting    = _aggregate_lighting(frames)
    composition = _aggregate_composition(frames)
    movement    = _aggregate_movement(frames)
    color       = _aggregate_color(frames)
    quality     = _aggregate_quality(frames)
    narrative   = _aggregate_narrative(frames)

    for cat in [exposure, lighting, composition, movement, color, quality, narrative]:
        cat.total = cat.compute_total(w_tech, w_creat, w_subj)

    # technical pillar subtotal — weighted average across categories
    tech_scores, tech_weights = [], []
    for cat, key in [
        (exposure,    "exposure"),
        (lighting,    "lighting"),
        (composition, "composition"),
        (movement,    "movement"),
        (color,       "color"),
        (quality,     "quality"),
        (narrative,   "narrative"),
    ]:
        if cat.technical is not None:
            cw = float(cat_weights.get(key, 1.0 / 7.0))
            tech_scores.append(cat.technical * cw)
            tech_weights.append(cw)

    technical_total: Optional[float] = None
    if tech_weights:
        technical_total = round(sum(tech_scores) / sum(tech_weights), 2)

    # temporal variance — std of per-frame technical proxy scores
    frame_scores = _collect(frames, _frame_technical_proxy)
    temporal_variance: Optional[float] = None
    if len(frame_scores) > 1:
        temporal_variance = round(float(np.std(frame_scores)), 2)

    # subjective proxy — seeded from narrative + temporal consistency only.
    # Uses no technical category scores to avoid circular dependency.
    # Neutral midpoint is 50 — missing data neither rewards nor penalises.
    # Real calibration comes from the baseline corpus over time.
    subjective_total = _compute_subjective_proxy(frames, narrative, temporal_variance)
    metric_detail    = _collect_metric_detail(frames)
    gamut_data       = _collect_gamut_data(frames)

    return ShotScore(
        shot_id=shot_id,
        scene_id=scene_id,
        exposure=exposure,
        lighting=lighting,
        composition=composition,
        movement=movement,
        color=color,
        quality=quality,
        narrative=narrative,
        technical_total=technical_total,
        subjective_total=subjective_total,
        total_score=technical_total,
        temporal_variance=temporal_variance,
        frame_count=len(frames),
        metric_detail=metric_detail,
        gamut_coverage=gamut_data.get("gamut_coverage"),
        dominant_colours=gamut_data.get("dominant_colours"),
    )


# ---------------------------------------------------------------------------
# Per-metric detail collector
# ---------------------------------------------------------------------------

def _collect_metric_detail(frames: List[FrameMetrics]) -> Dict[str, Dict[str, float]]:
    """Average every raw metric across frames for the matrix drill-down panel."""
    if not frames:
        return {}

    def _avg(vals):
        v = [x for x in vals if x is not None]
        return round(float(np.mean(v)), 3) if v else None

    detail: Dict[str, Dict[str, float]] = {}

    exp = {
        "histogram_mean":       _avg([f.exposure.histogram_mean       for f in frames]),
        "histogram_std":        _avg([f.exposure.histogram_std        for f in frames]),
        "histogram_skew":       _avg([f.exposure.histogram_skew       for f in frames]),
        "highlight_clip_%":     _avg([f.exposure.highlight_clip_pct   for f in frames]),
        "shadow_clip_%":        _avg([f.exposure.shadow_clip_pct      for f in frames]),
        "snr_luma":             _avg([f.exposure.snr_luma             for f in frames]),
        "snr_chroma":           _avg([f.exposure.snr_chroma           for f in frames]),
        "psnr":                 _avg([f.exposure.psnr                 for f in frames]),
        "ssim":                 _avg([f.exposure.ssim                 for f in frames]),
        "exposure_intent":      _avg([f.exposure.exposure_intent      for f in frames]),
        "temporal_consistency": _avg([f.exposure.temporal_consistency for f in frames]),
        # new exposure refinement
        "highlight_rolloff":    _avg([f.exposure.highlight_rolloff    for f in frames]),
        "midtone_separation":   _avg([f.exposure.midtone_separation   for f in frames]),
        "toe_character":        _avg([f.exposure.toe_character        for f in frames]),
        "shoulder_character":   _avg([f.exposure.shoulder_character   for f in frames]),
    }
    # Flicker: variance of mean luma across frames (temporal metric)
    luma_means = [f.exposure.histogram_mean for f in frames if f.exposure.histogram_mean is not None]
    if len(luma_means) >= 2:
        import numpy as _np
        flicker = float(_np.clip(float(_np.std(luma_means)) / 20 * 100, 0, 100))
        for f in frames:
            if f.exposure is not None:
                f.exposure.flicker_score = round(flicker, 1)
        exp["flicker_score"] = round(flicker, 1)
    # Skin IRE: face luma as % of full range (from inference skin tone data)
    skin_ires = []
    for f in frames:
        if f.color and f.color.skin_tone_de is not None:
            # Proxy: use face region luma from YOLo detections if available
            if f.inference and f.inference.detections:
                face_dets = [d for d in f.inference.detections
                             if d.get("class_name","").lower() == "person"]
                if face_dets:
                    # Already have skin_tone_de; IRE proxy from histogram mean
                    skin_ires.append(f.exposure.histogram_mean or 128)
    if skin_ires:
        import numpy as _np2
        mean_ire = float(_np2.mean(skin_ires)) / 255 * 100  # % of full range
        exp["skin_ire_placement"] = round(mean_ire, 1)
    detail["exposure"] = {k: v for k, v in exp.items() if v is not None}

    lit = {
        "dynamic_range_stops":  _avg([f.lighting.dynamic_range_stops  for f in frames]),
        "key_fill_ratio":       _avg([f.lighting.key_fill_ratio        for f in frames]),
        "color_temp_K":         _avg([f.lighting.color_temp_kelvin     for f in frames]),
        "color_temp_deviation": _avg([f.lighting.color_temp_deviation  for f in frames]),
        "shadow_detail":        _avg([f.lighting.shadow_detail         for f in frames]),
        "shadow_noise":         _avg([f.lighting.shadow_noise          for f in frames]),
        "transition_hardness":  _avg([f.lighting.transition_hardness   for f in frames]),
        "light_motivation":     _avg([f.lighting.light_motivation      for f in frames]),
        "lighting_complexity":  _avg([f.lighting.lighting_complexity   for f in frames]),
        "atmosphere_density":   _avg([f.lighting.atmosphere_density    for f in frames]),
    }
    detail["lighting"] = {k: v for k, v in lit.items() if v is not None}

    comp = {
        "rule_of_thirds":       _avg([f.composition.rule_of_thirds       for f in frames]),
        "center_of_mass_x":     _avg([f.composition.center_of_mass_x     for f in frames]),
        "center_of_mass_y":     _avg([f.composition.center_of_mass_y     for f in frames]),
        "symmetry_score":       _avg([f.composition.symmetry_score       for f in frames]),
        # depth_separation: MiDaS when available, Laplacian proxy otherwise
        "depth_separation":     _avg([
            f.inference.midas_depth_separation
            if (f.inference and f.inference.midas_depth_separation is not None)
            else f.composition.depth_separation
            for f in frames
        ]),
        "negative_space_%":     _avg([f.composition.negative_space_ratio for f in frames]),
        "occupancy_%":          _avg([f.composition.occupancy_map_score  for f in frames]),
        "headroom":             _avg([f.composition.headroom             for f in frames]),
        "lead_room":            _avg([f.composition.lead_room            for f in frames]),
        "frame_balance":        _avg([f.composition.frame_balance        for f in frames]),
        "face_placement":       _avg([f.composition.face_placement       for f in frames]),
    }
    detail["composition"] = {k: v for k, v in comp.items() if v is not None}

    mov = {
        "optical_flow_mean":     _avg([f.movement.optical_flow_mean     for f in frames]),
        "optical_flow_std":      _avg([f.movement.optical_flow_std      for f in frames]),
        "smoothness":            _avg([f.movement.smoothness            for f in frames]),
        "jerkiness":             _avg([f.movement.jerkiness             for f in frames]),
        "stabilization":         _avg([f.movement.stabilization         for f in frames]),
        "motion_blur_amount":    _avg([f.movement.motion_blur_amount    for f in frames]),
        "focus_during_movement": _avg([f.movement.focus_during_movement for f in frames]),
        "trajectory_smoothness": _avg([f.movement.trajectory_smoothness for f in frames]),
    }
    detail["movement"] = {k: v for k, v in mov.items() if v is not None}

    col = {
        "wb_deviation":          _avg([f.color.wb_deviation          for f in frames]),
        "saturation_mean":       _avg([f.color.saturation_mean       for f in frames]),
        "saturation_uniformity": _avg([f.color.saturation_uniformity for f in frames]),
        "palette_entropy":       _avg([f.color.palette_entropy       for f in frames]),
        "chroma_noise":          _avg([f.color.chroma_noise          for f in frames]),
        "banding_score":         _avg([f.color.banding_score         for f in frames]),
        "delta_e_d65":           _avg([f.color.color_accuracy_de2000 for f in frames]),
        "skin_tone_de":          _avg([f.color.skin_tone_de           for f in frames]),
    }
    detail["color"] = {k: v for k, v in col.items() if v is not None}

    qual = {
        "sharpness_laplacian":   _avg([f.quality.sharpness_laplacian    for f in frames]),
        "sharpness_edge_density":_avg([f.quality.sharpness_edge_density for f in frames]),
        "mtf_proxy":             _avg([f.quality.mtf_proxy              for f in frames]),
        "vignetting_stops":      _avg([f.quality.vignetting_stops       for f in frames]),
        "ca_width_px":           _avg([f.quality.ca_width_px            for f in frames]),
        "flare_contrast_loss":   _avg([f.quality.flare_contrast_loss    for f in frames]),
        "compression_blocking":  _avg([f.quality.compression_blocking   for f in frames]),
        "compression_ringing":   _avg([f.quality.compression_ringing    for f in frames]),
        "texture_retention":     _avg([f.quality.texture_retention      for f in frames]),
    }
    detail["quality"] = {k: v for k, v in qual.items() if v is not None}

    nar = {
        "saliency_consistency":  _avg([f.narrative.saliency_consistency for f in frames]),
        "compelling_mos":        _avg([f.narrative.compelling_mos       for f in frames]),
    }
    detail["narrative"] = {k: v for k, v in nar.items() if v is not None}

    return detail


# ---------------------------------------------------------------------------
# Subjective proxy
# ---------------------------------------------------------------------------

def _compute_subjective_proxy(
    frames:            list,
    narrative_score:   Any,
    temporal_variance: Optional[float],
) -> float:
    """
    Compute a subjective pillar proxy score from narrative metrics and
    temporal consistency only — deliberately avoiding technical category
    scores to prevent circular dependency with the Technical pillar.

    Components:
      - Saliency consistency (40%) — how well the frame draws attention
      - Compelling MOS (40%)      — aesthetic appeal proxy
      - Temporal stability (20%)  — consistent shots feel more intentional

    Neutral midpoint is 50. Missing data returns 50 (unknown, not penalised).
    Real calibration improves as the baseline corpus grows.
    """
    NEUTRAL = 50.0
    parts:   list = []
    weights: list = []

    # pull raw narrative signals directly from FrameMetrics — NOT from
    # narrative_score which is a CategoryScore (collapsed scalar) and has
    # no saliency_consistency or compelling_mos attributes
    sal_vals = _collect(frames, lambda f: f.narrative.saliency_consistency
                        if f.narrative is not None else None)
    mos_vals = _collect(frames, lambda f: f.narrative.compelling_mos
                        if f.narrative is not None else None)

    sal = float(np.mean(sal_vals)) if sal_vals else None
    mos = float(np.mean(mos_vals)) if mos_vals else None

    parts.append(float(sal) if sal is not None else NEUTRAL)
    weights.append(0.40)

    parts.append(float(mos) if mos is not None else NEUTRAL)
    weights.append(0.40)

    # temporal stability — low variance = intentional, consistent shot
    if temporal_variance is not None:
        stability = max(0.0, 100.0 - min(temporal_variance * 2.0, 50.0))
        parts.append(stability)
    else:
        parts.append(NEUTRAL)
    weights.append(0.20)

    proxy = sum(p * w for p, w in zip(parts, weights)) / sum(weights)
    return round(min(100.0, max(0.0, proxy)), 2)


# ---------------------------------------------------------------------------
# Gamut data collection
# ---------------------------------------------------------------------------

# sRGB to XYZ D65 matrix (IEC 61966-2-1)
_SRGB_TO_XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
], dtype=np.float32)

# Gamut primary xy chromaticities (CIE 1931)
_GAMUT_PRIMARIES = {
    "srgb":    {"r": (0.6400, 0.3300), "g": (0.3000, 0.6000), "b": (0.1500, 0.0600), "w": (0.3127, 0.3290)},
    "p3":      {"r": (0.6800, 0.3200), "g": (0.2650, 0.6900), "b": (0.1500, 0.0600), "w": (0.3127, 0.3290)},
    "rec2020": {"r": (0.7080, 0.2920), "g": (0.1700, 0.7970), "b": (0.1310, 0.0460), "w": (0.3127, 0.3290)},
}


def _point_in_triangle(px, py, ax, ay, bx, by, cx, cy) -> bool:
    """Test if point (px,py) is inside triangle (ax,ay)-(bx,by)-(cx,cy)."""
    def sign(p1x, p1y, p2x, p2y, p3x, p3y):
        return (p1x - p3x) * (p2y - p3y) - (p2x - p3x) * (p1y - p3y)
    d1 = sign(px, py, ax, ay, bx, by)
    d2 = sign(px, py, bx, by, cx, cy)
    d3 = sign(px, py, cx, cy, ax, ay)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def _xy_from_bgr(img: np.ndarray) -> "Optional[np.ndarray]":
    """Convert a BGR image to xy chromaticity array, filtering dark pixels."""
    small  = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA)
    pixels = small.reshape(-1, 3).astype(np.float32) / 255.0
    linear = np.where(pixels <= 0.04045, pixels / 12.92,
                      ((pixels + 0.055) / 1.055) ** 2.4)
    linear = linear[:, ::-1]  # BGR → RGB
    xyz    = linear @ _SRGB_TO_XYZ.T
    xyz_sum = xyz.sum(axis=1, keepdims=True) + 1e-8
    xy     = xyz[:, :2] / xyz_sum
    Y      = xyz[:, 1]
    mask   = Y > 0.005
    return xy[mask] if mask.any() else None


def _kmeans_xy(xy_pts: np.ndarray, k: int = 4, seed: int = 42) -> tuple:
    """Mini k-means in xy space. Returns (centres, weights)."""
    k   = min(k, len(xy_pts))
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(xy_pts), k, replace=False)
    centres = xy_pts[idx].copy()
    labels  = np.zeros(len(xy_pts), dtype=int)
    for _ in range(15):
        diffs  = xy_pts[:, None, :] - centres[None, :, :]
        labels = np.argmin(np.sum(diffs ** 2, axis=2), axis=1)
        new_c  = np.array([
            xy_pts[labels == i].mean(axis=0) if np.any(labels == i) else centres[i]
            for i in range(k)
        ])
        if np.allclose(centres, new_c, atol=0.001):
            break
        centres = new_c
    sizes   = [int(np.sum(labels == i)) for i in range(k)]
    total   = max(1, sum(sizes))
    weights = [round(s / total, 3) for s in sizes]
    return centres, weights


def _collect_gamut_data(frames: List[FrameMetrics]) -> Dict[str, Any]:
    """
    Collect xy chromaticity data from frame image files for the gamut chart.
    Returns:
      - dominant_colours: 8 aggregate clusters across all frames (for backward compat)
      - per_frame_colours: list of per-frame cluster arrays — one entry per valid frame
      - gamut_coverage: % of pixels inside each gamut triangle
      - waveform: per-column percentile bands for luma and R/G/B channels
    """
    all_xy:        List[np.ndarray] = []
    per_frame_xy:  List[list]       = []   # per-frame 4-cluster sets
    waveform_cols: List[np.ndarray] = []   # per-frame column luma arrays
    parade_cols_r: List[np.ndarray] = []
    parade_cols_g: List[np.ndarray] = []
    parade_cols_b: List[np.ndarray] = []

    N_COLS = 64  # waveform resolution

    for f in frames:
        if not f.frame_path or not Path(f.frame_path).exists():
            continue
        try:
            img = cv2.imread(f.frame_path)
            if img is None:
                continue

            # --- chromaticity ---
            xy = _xy_from_bgr(img)
            if xy is not None:
                all_xy.append(xy)
                centres, weights = _kmeans_xy(xy, k=4)
                per_frame_xy.append([
                    [round(float(c[0]), 4), round(float(c[1]), 4), w]
                    for c, w in zip(centres, weights)
                ])

            # --- waveform data ---
            # resize to N_COLS wide, keep height for column sampling
            wf_h = min(img.shape[0], 128)
            wf   = cv2.resize(img, (N_COLS, wf_h), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(wf, cv2.COLOR_BGR2GRAY).astype(np.float32)
            # luma as IRE (0-100)
            waveform_cols.append(gray / 255.0 * 100.0)
            # R/G/B channels (BGR order from OpenCV)
            parade_cols_b.append(wf[:, :, 0].astype(np.float32) / 255.0 * 100.0)
            parade_cols_g.append(wf[:, :, 1].astype(np.float32) / 255.0 * 100.0)
            parade_cols_r.append(wf[:, :, 2].astype(np.float32) / 255.0 * 100.0)

        except Exception:
            continue

    if not all_xy:
        return {}

    xy_all = np.vstack(all_xy)

    # aggregate 8-cluster for dominant_colours (backward compat)
    centres8, weights8 = _kmeans_xy(xy_all, k=8, seed=42)

    # gamut coverage
    gamut_coverage = {}
    for gamut_name, primaries in _GAMUT_PRIMARIES.items():
        rx, ry = primaries["r"]
        gx, gy = primaries["g"]
        bx, by = primaries["b"]
        inside = sum(1 for x, y in xy_all
                     if _point_in_triangle(x, y, rx, ry, gx, gy, bx, by))
        gamut_coverage[gamut_name] = round(inside / len(xy_all) * 100.0, 1)

    # waveform: average percentile bands across frames for each column
    def _col_bands(stacked: List[np.ndarray]) -> list:
        """For each of N_COLS columns, compute [p5,p25,p50,p75,p95] across all frame rows."""
        if not stacked:
            return []
        arr = np.concatenate(stacked, axis=0)  # all rows from all frames, N_COLS wide
        bands = []
        for c in range(N_COLS):
            col = arr[:, c]
            bands.append([
                round(float(np.percentile(col, 5)),  1),
                round(float(np.percentile(col, 25)), 1),
                round(float(np.percentile(col, 50)), 1),
                round(float(np.percentile(col, 75)), 1),
                round(float(np.percentile(col, 95)), 1),
            ])
        return bands

    return {
        "dominant_colours":  [[round(float(c[0]),4), round(float(c[1]),4), w]
                               for c, w in zip(centres8, weights8)],
        "per_frame_colours": per_frame_xy,
        "gamut_coverage":    gamut_coverage,
        "waveform":          _col_bands(waveform_cols),
        "parade_r":          _col_bands(parade_cols_r),
        "parade_g":          _col_bands(parade_cols_g),
        "parade_b":          _col_bands(parade_cols_b),
    }


# ---------------------------------------------------------------------------
# Per-category aggregation
# ---------------------------------------------------------------------------

def _aggregate_exposure(frames: List[FrameMetrics]) -> CategoryScore:
    scores = []
    for f in frames:
        e = f.exposure
        parts = []
        # tonal spread — good exposure uses the full range
        if e.histogram_std is not None:
            parts.append(min(100.0, (e.histogram_std / 64.0) * 100.0))
        # tonal balance — avoid extreme skew (very dark or very bright)
        if e.histogram_skew is not None:
            skew_penalty = min(50.0, abs(e.histogram_skew) * 10.0)
            parts.append(max(0.0, 100.0 - skew_penalty))
        # midtone placement — histogram_mean near 128 = balanced exposure
        if e.histogram_mean is not None:
            mean_score = 100.0 - min(100.0, abs(e.histogram_mean - 118.0) / 1.18)
            parts.append(max(0.0, mean_score))
        # clipping penalty
        if e.highlight_clip_pct is not None and e.shadow_clip_pct is not None:
            clip_penalty = (e.highlight_clip_pct * 2.0) + (e.shadow_clip_pct * 1.5)
            parts.append(max(0.0, 100.0 - clip_penalty))
        # luma signal quality
        if e.snr_luma is not None:
            parts.append(min(100.0, max(0.0, (e.snr_luma + 10.0) / 60.0 * 100.0)))
        # chroma signal quality
        if e.snr_chroma is not None:
            parts.append(min(100.0, max(0.0, (e.snr_chroma + 10.0) / 60.0 * 100.0)))
        # structural integrity
        if e.psnr is not None:
            parts.append(min(100.0, max(0.0, (e.psnr - 20.0) / 40.0 * 100.0)))
        if e.ssim is not None:
            parts.append(e.ssim)
        # temporal exposure consistency
        if e.temporal_consistency is not None:
            parts.append(e.temporal_consistency)
        # deliberate exposure intent
        if e.exposure_intent is not None:
            parts.append(e.exposure_intent)
        if parts:
            scores.append(float(np.mean(parts)))
    return CategoryScore(technical=_trimmed_mean(scores))


def _aggregate_lighting(frames: List[FrameMetrics]) -> CategoryScore:
    scores = []
    for f in frames:
        li = f.lighting
        parts = []
        if li.dynamic_range_stops is not None:
            parts.append(min(100.0, li.dynamic_range_stops / 12.0 * 100.0))
        if li.key_fill_ratio is not None:
            kf = li.key_fill_ratio
            if 2.0 <= kf <= 8.0:
                parts.append(100.0)
            elif kf < 2.0:
                parts.append(max(0.0, kf / 2.0 * 100.0))
            else:
                parts.append(max(0.0, 100.0 - (kf - 8.0) * 10.0))
        if li.shadow_detail is not None:
            parts.append(li.shadow_detail)
        if li.light_motivation is not None:
            parts.append(li.light_motivation)
        if parts:
            scores.append(float(np.mean(parts)))
    return CategoryScore(technical=_trimmed_mean(scores))


def _aggregate_composition(frames: List[FrameMetrics]) -> CategoryScore:
    scores = []
    for f in frames:
        co = f.composition
        parts = []

        # compositional placement
        if co.rule_of_thirds    is not None: parts.append(co.rule_of_thirds)
        if co.frame_balance     is not None: parts.append(co.frame_balance)

        # visual balance — penalise extreme centre-of-mass offset
        if co.center_of_mass_x is not None:
            # ideal: near 0.33 or 0.67 (thirds), penalise dead-centre or edge
            x = co.center_of_mass_x
            thirds_dist = min(abs(x - 0.33), abs(x - 0.5), abs(x - 0.67))
            parts.append(max(0.0, 100.0 - thirds_dist * 200.0))
        if co.center_of_mass_y is not None:
            y = co.center_of_mass_y
            # upper third (0.33) generally preferred for subjects
            thirds_dist = min(abs(y - 0.33), abs(y - 0.67))
            parts.append(max(0.0, 100.0 - thirds_dist * 200.0))

        # negative space — enough breathing room is intentional
        if co.negative_space_ratio is not None:
            # 20-60% negative space = good range
            ns = co.negative_space_ratio
            ns_score = 100.0 if 20.0 <= ns <= 60.0 else max(0.0, 100.0 - abs(ns - 40.0) * 2.0)
            parts.append(ns_score)

        # symmetry — high symmetry is intentional (faces, architecture)
        if co.symmetry_score    is not None: parts.append(co.symmetry_score)

        # headroom and lead room — compositional breathing space
        if co.headroom  is not None:
            # 15-35% headroom is ideal
            hr = co.headroom
            hr_score = 100.0 if 15.0 <= hr <= 35.0 else max(0.0, 100.0 - abs(hr - 25.0) * 3.0)
            parts.append(hr_score)
        if co.lead_room is not None: parts.append(co.lead_room)

        # frame occupancy
        if co.occupancy_map_score is not None: parts.append(co.occupancy_map_score)

        # depth
        if co.depth_separation  is not None: parts.append(co.depth_separation)

        # face placement — weighted more heavily when faces are present
        if co.face_placement is not None and co.face_placement > 0:
            face_weight = 1 + min(2, getattr(co, 'face_count', 0) or 0)  # 1-3x weight
            for _ in range(face_weight):
                parts.append(co.face_placement)
        elif co.face_placement is not None:
            parts.append(co.face_placement)

        if parts:
            scores.append(float(np.mean(parts)))
    return CategoryScore(technical=_trimmed_mean(scores))


def _aggregate_movement(frames: List[FrameMetrics]) -> CategoryScore:
    parts = []
    # core smoothness signals
    smooth = _collect(frames, lambda f: f.movement.smoothness)
    stab   = _collect(frames, lambda f: f.movement.stabilization)
    focus  = _collect(frames, lambda f: f.movement.focus_during_movement)
    traj   = _collect(frames, lambda f: f.movement.trajectory_smoothness)
    if smooth: parts.append(_trimmed_mean(smooth))
    if stab:   parts.append(_trimmed_mean(stab))
    if focus:  parts.append(_trimmed_mean(focus))
    if traj:   parts.append(_trimmed_mean(traj))

    # jerkiness — inverted: high jerkiness = low score
    jerk = _collect(frames, lambda f: f.movement.jerkiness)
    if jerk: parts.append(max(0.0, 100.0 - _trimmed_mean(jerk)))

    # motion blur — some is intentional (cinematic 180° shutter)
    # penalise extremes: too little (stroboscopic) or too much (uncontrolled)
    blur = _collect(frames, lambda f: f.movement.motion_blur_amount)
    if blur:
        mean_blur = _trimmed_mean(blur)
        # optimal range: 10-40 blur amount
        blur_score = 100.0 if 10.0 <= mean_blur <= 40.0 else max(0.0, 100.0 - abs(mean_blur - 25.0) * 2.5)
        parts.append(blur_score)

    # optical flow consistency — high std = erratic movement
    flow_std = _collect(frames, lambda f: f.movement.optical_flow_std)
    if flow_std:
        parts.append(max(0.0, 100.0 - min(100.0, _trimmed_mean(flow_std) * 2.0)))

    technical = round(float(np.mean(parts)), 2) if parts else None
    return CategoryScore(technical=technical)


def _aggregate_color(frames: List[FrameMetrics]) -> CategoryScore:
    scores = []
    for f in frames:
        cl = f.color
        parts = []
        # white balance accuracy — lower deviation = better
        if cl.wb_deviation        is not None: parts.append(max(0.0, 100.0 - cl.wb_deviation * 3.0))
        # saturation — mean and uniformity both matter
        if cl.saturation_mean     is not None:
            # moderate saturation is ideal (not flat, not oversaturated)
            # optimal range ~20-60 Lab chroma
            sat = cl.saturation_mean
            sat_score = 100.0 if 20.0 <= sat <= 60.0 else max(0.0, 100.0 - abs(sat - 40.0) * 1.5)
            parts.append(sat_score)
        if cl.saturation_uniformity is not None: parts.append(cl.saturation_uniformity)
        # colour complexity — palette entropy (higher = more intentional use of colour)
        if cl.palette_entropy     is not None:
            parts.append(min(100.0, cl.palette_entropy / 4.0 * 100.0))
        # noise and artifact penalties
        if cl.chroma_noise        is not None: parts.append(max(0.0, 100.0 - cl.chroma_noise))
        if cl.banding_score       is not None: parts.append(max(0.0, 100.0 - cl.banding_score))
        # colour accuracy vs D65 neutral — lower ΔE = more neutral/accurate WB
        if cl.color_accuracy_de2000 is not None:
            de_score = max(0.0, 100.0 - cl.color_accuracy_de2000 * 5.0)
            parts.append(de_score)
        # skin tone accuracy — lower ΔE = skin renders close to reference
        if cl.skin_tone_de is not None:
            skin_score = max(0.0, 100.0 - cl.skin_tone_de * 4.0)
            parts.append(skin_score)
        if parts:
            scores.append(float(np.mean(parts)))
    return CategoryScore(technical=_trimmed_mean(scores))


def _aggregate_quality(frames: List[FrameMetrics]) -> CategoryScore:
    scores = []
    for f in frames:
        qu = f.quality
        parts = []
        # sharpness
        if qu.sharpness_laplacian   is not None: parts.append(min(100.0, qu.sharpness_laplacian / 500.0 * 100.0))
        if qu.sharpness_edge_density is not None: parts.append(qu.sharpness_edge_density)
        if qu.mtf_proxy             is not None: parts.append(qu.mtf_proxy)
        if qu.texture_retention     is not None: parts.append(qu.texture_retention)
        # all compression artifacts — all inverted (higher artifact = lower score)
        if qu.compression_blocking  is not None: parts.append(max(0.0, 100.0 - qu.compression_blocking))
        if qu.compression_banding   is not None: parts.append(max(0.0, 100.0 - qu.compression_banding))
        if qu.compression_mosquito  is not None: parts.append(max(0.0, 100.0 - qu.compression_mosquito))
        if qu.compression_ringing   is not None: parts.append(max(0.0, 100.0 - qu.compression_ringing))
        # optical imperfections — inverted
        if qu.vignetting_stops      is not None: parts.append(max(0.0, 100.0 - qu.vignetting_stops * 25.0))
        if qu.ca_width_px           is not None: parts.append(max(0.0, 100.0 - qu.ca_width_px * 10.0))
        if qu.flare_contrast_loss   is not None: parts.append(max(0.0, 100.0 - qu.flare_contrast_loss * 5.0))
        # lens distortion — higher score = more distortion = worse
        if qu.lens_distortion       is not None: parts.append(max(0.0, 100.0 - qu.lens_distortion))
        if parts:
            scores.append(float(np.mean(parts)))
    return CategoryScore(technical=_trimmed_mean(scores))


def _aggregate_narrative(frames: List[FrameMetrics]) -> CategoryScore:
    parts = []
    sal  = _collect(frames, lambda f: f.narrative.saliency_consistency)
    comp = _collect(frames, lambda f: f.narrative.compelling_mos)
    if sal:  parts.append(_trimmed_mean(sal))
    if comp: parts.append(_trimmed_mean(comp))
    technical = round(float(np.mean(parts)), 2) if parts else None
    return CategoryScore(technical=technical)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _frame_technical_proxy(f: FrameMetrics) -> Optional[float]:
    """Single-number proxy for a frame's technical quality — used for variance."""
    parts = []
    if f.exposure.histogram_std      is not None: parts.append(min(100.0, f.exposure.histogram_std / 64.0 * 100.0))
    if f.quality.sharpness_laplacian is not None: parts.append(min(100.0, f.quality.sharpness_laplacian / 500.0 * 100.0))
    if f.color.wb_deviation          is not None: parts.append(max(0.0, 100.0 - f.color.wb_deviation * 3.0))
    return round(float(np.mean(parts)), 2) if parts else None


def _collect(
    frames: List[FrameMetrics],
    getter: Callable[[FrameMetrics], Optional[float]],
) -> List[float]:
    """Collect non-None values from frames using a getter function."""
    results = []
    for f in frames:
        v = getter(f)
        if v is not None:
            results.append(v)
    return results


def _trimmed_mean(values: List[float], trim_pct: float = 0.1) -> Optional[float]:
    """
    Trimmed mean — removes top and bottom trim_pct before averaging.
    More robust to outlier frames than a plain mean.
    """
    if not values:
        return None
    if len(values) < 4:
        return round(float(np.mean(values)), 2)
    arr     = np.array(sorted(values))
    n       = len(arr)
    trim_n  = max(1, int(n * trim_pct))
    trimmed = arr[trim_n:-trim_n]
    return round(float(np.mean(trimmed)), 2)