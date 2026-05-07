# aesthetic/agents/corpus_scoring.py
#
# Corpus-relative metric scoring.
#
# Every metric is scored by comparing the query value against the
# distribution of that metric across the Golden Baseline corpus.
# Score = 0-100 representing position in the corpus distribution.
#
# For "higher is better" metrics: score rises as query exceeds corpus mean.
# For "lower is better" metrics: score rises as query falls below corpus mean.
# For "optimal range" metrics: score is highest near corpus mean, falls off
#   in either direction (the corpus defines what "normal" looks like).
#
# A score of 50 means the query matches the corpus mean exactly.
# A score of 85 means the query is better than ~85% of the corpus.
# A score of 15 means the query is worse than ~85% of the corpus.

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Metric directionality table
# ---------------------------------------------------------------------------
# "high"    = higher query value is better (sharpness, SNR, etc.)
# "low"     = lower query value is better (noise, jitter, clipping, etc.)
# "range"   = corpus mean is optimal; deviations in either direction score lower
#             used for metrics where the corpus distribution defines normal
# ---------------------------------------------------------------------------

METRIC_DIRECTION: Dict[str, str] = {
    # Exposure
    "histogram_mean":         "range",   # corpus defines normal exposure
    "histogram_median":       "range",
    "histogram_std":          "range",   # corpus defines normal contrast range
    "histogram_skew":         "range",
    "histogram_kurtosis":     "range",
    "highlight_clip_pct":     "low",     # less clipping is better
    "shadow_clip_pct":        "low",
    "psnr":                   "high",
    "ssim":                   "high",
    "third_moment_18gray":    "range",
    "snr_luma":               "high",
    "snr_chroma":             "high",
    "temporal_consistency":   "high",
    "exposure_intent":        "high",

    # Lighting
    "dynamic_range_stops":    "high",
    "key_fill_ratio":         "range",   # corpus defines normal lighting ratio
    "color_temp_kelvin":      "range",   # corpus defines normal colour temp
    "color_temp_deviation":   "low",     # less deviation from intent is better
    "shadow_detail":          "high",
    "shadow_noise":           "low",
    "transition_hardness":    "range",
    "light_motivation":       "high",

    # Composition
    "rule_of_thirds":         "high",
    "face_placement":         "high",
    "center_of_mass_x":       "range",   # corpus defines normal balance
    "center_of_mass_y":       "range",
    "negative_space_ratio":   "range",
    "depth_separation":       "high",
    "occupancy_map_score":    "range",
    "symmetry_score":         "range",
    "headroom":               "range",
    "lead_room":              "range",
    "frame_balance":          "high",

    # Movement
    "optical_flow_mean":      "range",
    "optical_flow_std":       "low",     # erratic motion is worse
    "smoothness":             "high",
    "jerkiness":              "low",
    "stabilization":          "high",
    "motion_blur_amount":     "range",   # corpus defines intentional motion blur
    "motion_blur_direction":  "range",
    "focus_during_movement":  "high",
    "trajectory_smoothness":  "high",

    # Color
    "wb_deviation":           "low",
    "saturation_mean":        "range",   # corpus defines normal saturation
    "saturation_uniformity":  "high",
    "palette_entropy":        "range",
    "chroma_noise":           "low",
    "banding_score":          "low",

    # Quality
    "sharpness_laplacian":    "high",
    "sharpness_edge_density": "high",
    "mtf_proxy":              "high",
    "vignetting_stops":       "low",
    "ca_width_px":            "low",
    "flare_contrast_loss":    "low",
    "compression_blocking":   "low",
    "compression_banding":    "low",
    "compression_mosquito":   "low",
    "compression_ringing":    "low",
    "texture_retention":      "high",

    # Narrative
    "saliency_consistency":   "high",
    "compelling_mos":         "high",
}


# ---------------------------------------------------------------------------
# Normal CDF approximation (no scipy dependency)
# ---------------------------------------------------------------------------

def _norm_cdf(z: float) -> float:
    """Approximation of the normal CDF. Returns probability 0-1."""
    # Abramowitz & Stegun approximation
    t = 1.0 / (1.0 + 0.2316419 * abs(z))
    poly = t * (0.319381530
              + t * (-0.356563782
              + t * (1.781477937
              + t * (-1.821255978
              + t * 1.330274429))))
    p = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * z * z) * poly
    return p if z >= 0 else 1.0 - p


# ---------------------------------------------------------------------------
# Per-metric corpus-relative score
# ---------------------------------------------------------------------------

def score_metric_vs_corpus(
    metric:     str,
    value:      float,
    corpus_stats: Dict[str, Any],
) -> Optional[float]:
    """
    Score a single metric value against the corpus distribution.

    Returns 0-100:
      50 = exactly at corpus mean
      85 = better than ~85% of corpus frames
      15 = worse than ~85% of corpus frames

    Returns None if:
      - metric not in corpus (no reference distribution)
      - corpus has fewer than 10 samples (unreliable)
      - corpus std is 0 (degenerate distribution)
    """
    stat = corpus_stats.get(metric)
    if stat is None:
        return None

    n    = int(stat.get("n", 0))
    mean = float(stat.get("mean", 0.0))
    m2   = float(stat.get("M2", 0.0))

    if n < 10:
        return None

    variance = m2 / (n - 1) if n > 1 else 0.0
    std = math.sqrt(variance) if variance > 0 else 0.0

    if std < 1e-8:
        # Degenerate distribution — all corpus frames identical for this metric
        # Score 50 if query matches, 0 if below, 100 if above (for high metrics)
        direction = METRIC_DIRECTION.get(metric, "range")
        if abs(value - mean) < 1e-6:
            return 50.0
        if direction == "high":
            return 100.0 if value > mean else 0.0
        if direction == "low":
            return 100.0 if value < mean else 0.0
        return 50.0

    z = (value - mean) / std
    direction = METRIC_DIRECTION.get(metric, "range")

    if direction == "high":
        # Higher is better — percentile of query in distribution
        pct = _norm_cdf(z) * 100.0

    elif direction == "low":
        # Lower is better — invert: low query = high score
        pct = (1.0 - _norm_cdf(z)) * 100.0

    else:  # "range"
        # Optimal near corpus mean. Score = 100 at z=0, falls toward 0 at |z|=3
        # Use a bell curve: score = 100 * exp(-0.5 * z^2 / sigma^2)
        # sigma=1.5 means z=1.5 → score ~71, z=2 → score ~51, z=3 → score ~22
        pct = 100.0 * math.exp(-0.5 * (z / 1.5) ** 2)

    return round(min(100.0, max(0.0, pct)), 1)


def score_all_metrics_vs_corpus(
    metrics:      Dict[str, Optional[float]],
    corpus_stats: Dict[str, Any],
) -> Dict[str, Optional[float]]:
    """
    Score all metrics in a dict against the corpus.
    Returns dict of metric_name -> score (0-100) or None if no corpus data.
    """
    return {
        k: score_metric_vs_corpus(k, v, corpus_stats)
        for k, v in metrics.items()
        if v is not None and isinstance(v, (int, float))
    }