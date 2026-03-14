# aesthetic/agents/selection.py
#
# Global selection agent.
# Takes all scored shots across all scenes and selects the final set
# that maximises both quality and diversity.
#
# Pipeline:
#   1. Per-scene ranking — rank shots within each scene, keep top pct
#   2. Global pool — combine all per-scene winners
#   3. Deduplication — remove near-identical shots via perceptual hash
#   4. Diversity constraint — cosine similarity on metric vectors
#   5. Facility location objective — final selection maximising quality + coverage
#   6. Guarantee top_k — always return at least top_k even when degraded
#
# Output: shots.json written to job directory

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..models.job import Shot
from ..models.scores import ShotScore


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def select_shots(
    shots:       List[Shot],
    scores:      List[ShotScore],
    job_dir:     Path,
    config:      Dict[str, Any],
    seed:        int = 42,
) -> List[Dict[str, Any]]:
    """
    Select the best shots from the global pool across all scenes.

    Args:
        shots:   List of Shot models from the pipeline.
        scores:  List of ShotScore models — one per shot, same order as shots.
        job_dir: Job directory — shots.json written here.
        config:  Full config dict.
        seed:    Random seed for deterministic tiebreaking.

    Returns:
        List of selected shot dicts with scores and timecodes.
        Also writes shots.json to job_dir.
    """
    if not shots or not scores:
        return []

    extract  = config.get("extract", {})
    keep_pct = float(extract.get("per_scene_keep_pct", 0.40))
    top_k    = int(config.get("selection", {}).get("top_k", 10))

    rng = np.random.default_rng(seed)

    # pair shots with their scores
    paired = _pair_shots_scores(shots, scores)
    if not paired:
        return []

    # step 1 — per-scene ranking
    per_scene = _per_scene_rank(paired, keep_pct)

    # step 2 — global pool
    pool = [item for scene_items in per_scene.values() for item in scene_items]
    if not pool:
        pool = paired   # fallback — use everything

    # step 3 — deduplication
    pool = _deduplicate(pool)

    # step 4 — filter title cards, logos, and static graphics
    pre_filter_count = len(pool)
    pool = _filter_non_cinematic(pool, config)
    filtered_count = pre_filter_count - len(pool)
    if filtered_count > 0:
        print(f"[selection] filtered {filtered_count} non-cinematic shots (title cards / logos)")

    # step 5 — ensure we have enough for selection
    if len(pool) <= top_k:
        selected = pool
    else:
        # step 5 — facility location selection
        selected = _facility_location(pool, top_k, rng)

    # step 6 — guarantee top_k even if facility location degraded
    if len(selected) < min(top_k, len(pool)):
        selected = _top_k_fallback(pool, top_k)

    # build output records
    result = _build_output(selected)

    _write_shots_json(result, job_dir)
    return result


# ---------------------------------------------------------------------------
# Step 3b — non-cinematic content filter
# ---------------------------------------------------------------------------

def _filter_non_cinematic(
    pool:   List[Tuple[Shot, ShotScore]],
    config: Dict[str, Any],
) -> List[Tuple[Shot, ShotScore]]:
    """
    Filter out shots that are likely title cards, logos, credits,
    or static graphics rather than cinematic content.

    Detection signals (all computed from existing metrics):
      - palette_entropy very low     -> few distinct colors (title card bg)
      - occupancy_map_score very low -> sparse content in frame
      - depth_separation near zero   -> flat image, no depth
      - histogram_std very low       -> near-uniform tone (black/white bg)
      - sharpness_laplacian very high with low saturation -> text on plain bg

    A shot is flagged as non-cinematic if it meets enough of these criteria.
    Thresholds are configurable via config.yaml under selection.content_filter.
    """
    cfg = config.get("selection", {}).get("content_filter", {})

    entropy_thresh    = float(cfg.get("min_palette_entropy",   2.5))
    occupancy_thresh  = float(cfg.get("min_occupancy_score",  15.0))
    depth_thresh      = float(cfg.get("min_depth_separation",  5.0))
    hist_std_thresh   = float(cfg.get("min_histogram_std",    20.0))
    saturation_thresh = float(cfg.get("min_saturation_mean",   8.0))

    kept = []
    for shot, score in pool:
        if _is_non_cinematic(
            score,
            entropy_thresh,
            occupancy_thresh,
            depth_thresh,
            hist_std_thresh,
            saturation_thresh,
        ):
            continue
        kept.append((shot, score))

    # safety — never filter everything
    if not kept:
        return pool

    return kept


def _is_non_cinematic(
    score:             ShotScore,
    entropy_thresh:    float,
    occupancy_thresh:  float,
    depth_thresh:      float,
    hist_std_thresh:   float,
    saturation_thresh: float,
) -> bool:
    """
    Return True if the shot looks like a title card, logo, or static graphic.
    Uses a points system — needs at least 3 of 5 signals to flag.
    This avoids false positives on intentionally minimal cinematography
    (e.g. a desaturated fog shot should not be filtered).
    """
    flags = 0

    # low color entropy — few distinct hues (title card background)
    entropy = _get_metric(score, "color", "palette_entropy")
    if entropy is not None and entropy < entropy_thresh:
        flags += 1

    # sparse content — little happening in the frame
    occupancy = _get_metric(score, "composition", "occupancy_map_score")
    if occupancy is not None and occupancy < occupancy_thresh:
        flags += 1

    # flat image — no depth separation
    depth = _get_metric(score, "composition", "depth_separation")
    if depth is not None and depth < depth_thresh:
        flags += 1

    # near-uniform tone — black or white background
    # we use exposure technical as a proxy — very high or very low = flat bg
    hist_std = score.exposure.technical
    if hist_std is not None and hist_std < hist_std_thresh:
        flags += 1

    # desaturated — logo or credit roll
    saturation = _get_metric(score, "color", "saturation_mean")
    if saturation is not None and saturation < saturation_thresh:
        flags += 1

    return flags >= 3


def _get_metric(score: ShotScore, category: str, field: str) -> Optional[float]:
    """Safely retrieve a raw metric value from a ShotScore category."""
    try:
        cat = getattr(score, category, None)
        if cat is None:
            return None
        # ShotScore stores CategoryScore objects — check if raw metrics available
        # Fall back to the technical score for the category
        return getattr(cat, field, None)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Step 1 — per-scene ranking
# ---------------------------------------------------------------------------

def _per_scene_rank(
    paired:   List[Tuple[Shot, ShotScore]],
    keep_pct: float,
) -> Dict[int, List[Tuple[Shot, ShotScore]]]:
    """
    Group shots by scene, rank by total_score descending,
    keep the top keep_pct from each scene.
    Always keeps at least 1 shot per scene.
    """
    scenes: Dict[int, List[Tuple[Shot, ShotScore]]] = {}
    for shot, score in paired:
        scenes.setdefault(shot.scene_id, []).append((shot, score))

    result: Dict[int, List[Tuple[Shot, ShotScore]]] = {}
    for scene_id, items in scenes.items():
        ranked = sorted(items, key=lambda x: x[1].total_score or 0.0, reverse=True)
        keep_n = max(1, int(len(ranked) * keep_pct))
        result[scene_id] = ranked[:keep_n]

    return result


# ---------------------------------------------------------------------------
# Step 3 — deduplication
# ---------------------------------------------------------------------------

def _deduplicate(
    pool:          List[Tuple[Shot, ShotScore]],
    hash_threshold: int = 8,
) -> List[Tuple[Shot, ShotScore]]:
    """
    Remove near-duplicate shots using perceptual hash comparison.
    Keeps the higher-scoring shot when duplicates are found.
    hash_threshold: maximum hamming distance to consider as duplicate (0-64).
    """
    if not pool:
        return pool

    # sort by score descending so we always keep the better shot
    sorted_pool = sorted(pool, key=lambda x: x[1].total_score or 0.0, reverse=True)

    kept: List[Tuple[Shot, ShotScore]] = []
    kept_hashes: List[np.ndarray] = []

    for shot, score in sorted_pool:
        # get hero frame path for hashing
        frame_path = shot.hero_frame or (shot.frame_paths[0] if shot.frame_paths else None)
        if not frame_path or not Path(frame_path).exists():
            kept.append((shot, score))
            kept_hashes.append(None)
            continue

        phash = _perceptual_hash(frame_path)
        if phash is None:
            kept.append((shot, score))
            kept_hashes.append(None)
            continue

        # check against all kept hashes
        is_duplicate = False
        for kept_hash in kept_hashes:
            if kept_hash is not None:
                distance = _hamming_distance(phash, kept_hash)
                if distance <= hash_threshold:
                    is_duplicate = True
                    break

        if not is_duplicate:
            kept.append((shot, score))
            kept_hashes.append(phash)

    return kept


def _perceptual_hash(frame_path: str, hash_size: int = 8) -> Optional[np.ndarray]:
    """
    Compute a perceptual hash (pHash) for an image.
    Returns an 8x8 binary array, or None on failure.
    """
    try:
        img  = cv2.imread(frame_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        # resize to hash_size * 4 then DCT
        size = hash_size * 4
        img  = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
        img  = img.astype(np.float32)
        dct  = cv2.dct(img)
        # take top-left hash_size x hash_size block (low frequencies)
        dct_low = dct[:hash_size, :hash_size]
        median  = np.median(dct_low)
        return (dct_low > median).astype(np.uint8)
    except Exception:
        return None


def _hamming_distance(a: np.ndarray, b: np.ndarray) -> int:
    """Hamming distance between two binary hash arrays."""
    return int(np.sum(a != b))


# ---------------------------------------------------------------------------
# Step 5 — facility location selection
# ---------------------------------------------------------------------------

def _facility_location(
    pool:  List[Tuple[Shot, ShotScore]],
    top_k: int,
    rng:   np.random.Generator,
) -> List[Tuple[Shot, ShotScore]]:
    """
    Greedy facility location — iteratively select shots that maximise
    the sum of (quality + coverage gain).

    Coverage gain for a candidate is defined as:
        min distance from candidate to any already-selected shot
        in the metric vector space.

    This rewards shots that are both high-quality AND different from
    what has already been selected.
    """
    if len(pool) <= top_k:
        return pool

    # build metric vectors for all shots
    vectors = np.array([_metric_vector(score) for _, score in pool], dtype=np.float32)

    # normalise vectors
    norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-8
    vectors = vectors / norms

    # quality scores
    quality = np.array([score.total_score or 0.0 for _, score in pool], dtype=np.float32)
    quality = quality / (quality.max() + 1e-8)   # normalise to 0-1

    n = len(pool)
    selected_indices = []
    min_distances = np.full(n, np.inf)

    # seed with the highest quality shot
    first_idx = int(np.argmax(quality))
    selected_indices.append(first_idx)
    _update_distances(min_distances, vectors, first_idx)

    while len(selected_indices) < top_k:
        # facility location objective: quality + coverage (min distance to selected)
        # normalise distances to 0-1
        max_dist = min_distances.max() + 1e-8
        coverage = min_distances / max_dist

        scores_fl = quality + coverage

        # mask already selected
        for idx in selected_indices:
            scores_fl[idx] = -np.inf

        next_idx = int(np.argmax(scores_fl))
        selected_indices.append(next_idx)
        _update_distances(min_distances, vectors, next_idx)

    return [pool[i] for i in selected_indices]


def _update_distances(
    min_distances: np.ndarray,
    vectors:       np.ndarray,
    new_idx:       int,
) -> None:
    """Update minimum distances after adding a new selected point."""
    new_vec   = vectors[new_idx]
    distances = 1.0 - np.dot(vectors, new_vec)   # cosine distance
    np.minimum(min_distances, distances, out=min_distances)


def _metric_vector(score: ShotScore) -> np.ndarray:
    """
    Build a fixed-length feature vector from a ShotScore for distance computation.
    Uses the technical category scores as the basis.
    """
    return np.array([
        score.exposure.technical    or 0.0,
        score.lighting.technical    or 0.0,
        score.composition.technical or 0.0,
        score.movement.technical    or 0.0,
        score.color.technical       or 0.0,
        score.quality.technical     or 0.0,
        score.narrative.technical   or 0.0,
        score.technical_total       or 0.0,
        score.baseline_similarity_score or 0.0,
    ], dtype=np.float32)


# ---------------------------------------------------------------------------
# Step 6 — top-k fallback
# ---------------------------------------------------------------------------

def _top_k_fallback(
    pool:  List[Tuple[Shot, ShotScore]],
    top_k: int,
) -> List[Tuple[Shot, ShotScore]]:
    """Simple top-k by total score — used when facility location degrades."""
    return sorted(pool, key=lambda x: x[1].total_score or 0.0, reverse=True)[:top_k]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pair_shots_scores(
    shots:  List[Shot],
    scores: List[ShotScore],
) -> List[Tuple[Shot, ShotScore]]:
    """
    Pair shots with their scores by shot_id.
    Handles mismatches gracefully.
    """
    score_map = {s.shot_id: s for s in scores}
    paired = []
    for shot in shots:
        score = score_map.get(shot.shot_id)
        if score is not None:
            paired.append((shot, score))
    return paired


def _build_output(
    selected: List[Tuple[Shot, ShotScore]],
) -> List[Dict[str, Any]]:
    """
    Build the final output list of shot dicts for shots.json.
    Sorted by total score descending.
    """
    sorted_selected = sorted(
        selected,
        key=lambda x: x[1].total_score or 0.0,
        reverse=True,
    )

    result = []
    for rank, (shot, score) in enumerate(sorted_selected, start=1):
        result.append({
            "rank":             rank,
            "shot_id":          shot.shot_id,
            "scene_id":         shot.scene_id,
            "start_time":       shot.start_time,
            "end_time":         shot.end_time,
            "duration_sec":     shot.duration_sec,
            "hero_frame":       shot.hero_frame,
            "movement_type":    shot.movement_type.value if shot.movement_type else None,
            "shot_scale":       shot.shot_scale.value   if shot.shot_scale   else None,
            "total_score":      score.total_score,
            "technical_total":  score.technical_total,
            "creative_total":   score.creative_total,
            "subjective_total": score.subjective_total,
            "temporal_variance":score.temporal_variance,
            "baseline_similarity": score.baseline_similarity_score,
            "rationale":        score.rationale,
            "frame_count":      score.frame_count,
            "scores": {
                "exposure":    score.exposure.total,
                "lighting":    score.lighting.total,
                "composition": score.composition.total,
                "movement":    score.movement.total,
                "color":       score.color.total,
                "quality":     score.quality.total,
                "narrative":   score.narrative.total,
            },
            "dedupe_evidence": {
                "kept_over_duplicates": True,
            },
        })

    return result


def _write_shots_json(shots: List[Dict[str, Any]], job_dir: Path) -> None:
    """Write final selected shots to jobs/<job_id>/shots.json."""
    job_dir.mkdir(parents=True, exist_ok=True)
    out_path = job_dir / "shots.json"
    out_path.write_text(json.dumps(shots, indent=2), encoding="utf-8")