# aesthetic/agents/feature_export.py
#
# Feature export pipeline for reranker training.
#
# Reads the feedback event store + cached metric sidecars and produces
# a flat feature matrix (CSV or Parquet) that can be fed directly into
# LightGBM or a small MLP for reranker training.
#
# Each row is one feedback event with:
#   - All numerical metric averages (from metric_detail or scores_json)
#   - Pillar scores (technical, creative, subjective)
#   - Classification labels (one-hot encoded)
#   - Shot metadata (duration, rank, scene_id)
#   - Target: rating (1=positive, -1=negative)
#   - Pairwise pairs from pairwise_prefs table
#
# Usage:
#   from aesthetic.agents.feature_export import export_training_features
#   export_training_features(output_path="training_features.csv")

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .feedback_store import get_all_feedback, get_pairwise_prefs

# ---------------------------------------------------------------------------
# Feature schema — ordered list of numeric features extracted per event
# ---------------------------------------------------------------------------

# Metric detail keys we flatten into feature columns
_METRIC_KEYS = {
    "exposure":    ["histogram_mean","histogram_std","histogram_skew",
                    "highlight_clip_%","shadow_clip_%","snr_luma","snr_chroma",
                    "psnr","ssim","exposure_intent","temporal_consistency"],
    "lighting":    ["dynamic_range_stops","key_fill_ratio","color_temp_K",
                    "color_temp_deviation","shadow_detail","shadow_noise",
                    "transition_hardness","light_motivation"],
    "composition": ["rule_of_thirds","center_of_mass_x","center_of_mass_y",
                    "symmetry_score","depth_separation","negative_space_%",
                    "occupancy_%","headroom","lead_room","frame_balance","face_placement"],
    "movement":    ["optical_flow_mean","optical_flow_std","smoothness","jerkiness",
                    "stabilization","motion_blur_amount","focus_during_movement",
                    "trajectory_smoothness"],
    "color":       ["wb_deviation","saturation_mean","saturation_uniformity",
                    "palette_entropy","chroma_noise","banding_score","delta_e_d65",
                    "skin_tone_de"],
    "quality":     ["sharpness_laplacian","sharpness_edge_density","mtf_proxy",
                    "vignetting_stops","ca_width_px","flare_contrast_loss",
                    "compression_blocking","compression_ringing","texture_retention"],
    "narrative":   ["saliency_consistency","compelling_mos"],
}

# Classification labels for one-hot encoding
_MOVEMENT_TYPES = ["static","pan","tilt","dolly","handheld","unknown"]
_SHOT_SCALES    = ["extreme_close","close","medium_close","medium","medium_wide","wide","extreme_wide","unknown"]
_SCENE_TYPES    = ["interior_day","interior_night","exterior_day","exterior_night","unknown"]
_SHOT_INTENTS   = ["intimate","establishing","action","dialogue","transitional","unknown"]


def _one_hot(value: Optional[str], labels: List[str]) -> List[int]:
    v = (value or "unknown").lower().replace(" ", "_")
    return [1 if v == lab else 0 for lab in labels]


def _extract_features(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract a flat feature dict from a feedback event row.
    Returns None if the event has insufficient data.
    """
    row: Dict[str, Any] = {}

    # --- pillar scores ---
    row["score_total"]      = event.get("total_score")      or 0.0
    row["score_technical"]  = event.get("technical_total")  or 0.0
    row["score_creative"]   = event.get("creative_total")   or 0.0
    row["score_subjective"] = event.get("subjective_total") or 0.0

    # --- shot metadata ---
    row["rank"]         = event.get("rank")         or 0
    row["duration_sec"] = event.get("duration_sec") or 0.0

    # --- category scores from scores_json ---
    scores = {}
    if event.get("scores_json"):
        try:
            scores = json.loads(event["scores_json"])
        except Exception:
            pass
    for cat in _METRIC_KEYS:
        sc = scores.get(cat, {})
        if isinstance(sc, dict):
            row[f"cat_{cat}_total"]      = sc.get("total")      or 0.0
            row[f"cat_{cat}_technical"]  = sc.get("technical")  or 0.0
            row[f"cat_{cat}_creative"]   = sc.get("creative")   or 0.0
            row[f"cat_{cat}_subjective"] = sc.get("subjective") or 0.0

    # --- per-metric detail ---
    detail = {}
    if event.get("metric_detail_json"):
        try:
            detail = json.loads(event["metric_detail_json"])
        except Exception:
            pass
    for cat, keys in _METRIC_KEYS.items():
        cat_detail = detail.get(cat, {})
        for key in keys:
            col = f"m_{cat}_{key}".replace("%", "pct").replace("-", "_").replace(" ", "_")
            row[col] = cat_detail.get(key) or 0.0

    # --- classification one-hot ---
    for val, labels, prefix in [
        (event.get("movement_type"), _MOVEMENT_TYPES, "mv_"),
        (event.get("shot_scale"),    _SHOT_SCALES,    "sc_"),
        (event.get("scene_type"),    _SCENE_TYPES,    "st_"),
        (event.get("shot_intent"),   _SHOT_INTENTS,   "si_"),
    ]:
        for lab, enc in zip(labels, _one_hot(val, labels)):
            row[f"{prefix}{lab}"] = enc

    # --- target ---
    row["rating"] = int(event.get("rating") or 0)
    row["job_id"] = event.get("job_id", "")
    row["shot_id"]= event.get("shot_id", "")

    return row


def export_training_features(
    output_path: Optional[str] = None,
    format: str = "csv",
) -> Dict[str, Any]:
    """
    Export all feedback events as a flat feature matrix for reranker training.

    Returns a summary dict. If output_path is provided, writes to disk.
    Format: 'csv' (default) or 'parquet' (requires pyarrow).

    Only includes explicit signals (rating +1 or -1, not retracted 0).
    """
    events = get_all_feedback()
    if not events:
        return {"ok": False, "error": "no feedback events found", "rows": 0}

    rows = []
    skipped = 0
    for event in events:
        feat = _extract_features(event)
        if feat is not None:
            rows.append(feat)
        else:
            skipped += 1

    if not rows:
        return {"ok": False, "error": "no extractable features", "rows": 0}

    if output_path:
        out = Path(output_path)
        if format == "parquet":
            try:
                import pandas as pd
                pd.DataFrame(rows).to_parquet(str(out), index=False)
            except ImportError:
                # fall back to CSV
                _write_csv(rows, out.with_suffix(".csv"))
                output_path = str(out.with_suffix(".csv"))
        else:
            _write_csv(rows, Path(output_path))

    return {
        "ok":           True,
        "rows":         len(rows),
        "skipped":      skipped,
        "feature_cols": len(rows[0]) - 3 if rows else 0,  # minus rating, job_id, shot_id
        "output_path":  output_path,
    }


def export_pairwise_features(
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Export pairwise preference pairs as a feature matrix for ranking model training.
    Each row has winner features, loser features, confidence, and pair type.
    """
    pairs = get_pairwise_prefs()
    if not pairs:
        return {"ok": False, "error": "no pairwise preferences found", "rows": 0}

    # fetch all events indexed by shot_id for fast lookup
    events = get_all_feedback()
    event_by_shot: Dict[str, Dict] = {}
    for e in events:
        sid = e.get("shot_id", "")
        if sid and sid not in event_by_shot:
            event_by_shot[sid] = e

    rows = []
    for pair in pairs:
        w_event = event_by_shot.get(pair["winner_shot_id"])
        l_event = event_by_shot.get(pair["loser_shot_id"])
        if not w_event or not l_event:
            continue

        w_feat = _extract_features(w_event) or {}
        l_feat = _extract_features(l_event) or {}

        row: Dict[str, Any] = {
            "job_id":          pair["job_id"],
            "winner_shot_id":  pair["winner_shot_id"],
            "loser_shot_id":   pair["loser_shot_id"],
            "confidence":      pair["confidence"],
            "pair_type":       pair["pair_type"],
        }
        # prefix winner/loser features
        for k, v in w_feat.items():
            if k not in ("rating", "job_id", "shot_id"):
                row[f"w_{k}"] = v
        for k, v in l_feat.items():
            if k not in ("rating", "job_id", "shot_id"):
                row[f"l_{k}"] = v
        # feature deltas (winner - loser) — often most informative for rankers
        for k in w_feat:
            if k not in ("rating", "job_id", "shot_id") and isinstance(w_feat.get(k), (int, float)):
                row[f"delta_{k}"] = (w_feat.get(k) or 0.0) - (l_feat.get(k) or 0.0)
        rows.append(row)

    if not rows:
        return {"ok": False, "error": "no extractable pairwise features", "rows": 0}

    if output_path:
        _write_csv(rows, Path(output_path))

    return {
        "ok":        True,
        "rows":      len(rows),
        "output_path": output_path,
    }


def _write_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(str(path), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
