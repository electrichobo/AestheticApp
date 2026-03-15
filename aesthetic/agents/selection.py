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
    sel_cfg  = config.get("selection", {})
    min_dur  = float(sel_cfg.get("min_shot_duration_sec",  2.0))
    soft_min = float(sel_cfg.get("soft_min_duration_sec",  1.0))

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

    # step 4b — duration weighting
    # Hard exclude shots below soft_min (unusable by any editor)
    # Apply score penalty to shots between soft_min and min_dur
    pool = _apply_duration_weighting(pool, min_dur, soft_min)

    # step 5 — ensure we have enough for selection
    if len(pool) <= top_k:
        selected = pool
    else:
        # step 6 — facility location selection
        selected = _facility_location(pool, top_k, rng)

    # step 7 — guarantee top_k even if facility location degraded
    if len(selected) < min(top_k, len(pool)):
        selected = _top_k_fallback(pool, top_k)

    # step 8 — narrative diversity enforcement
    # ensure the final picks span shot scales, movement types, and scene types
    # so the selects package is genuinely useful for a showreel
    selected = _enforce_narrative_diversity(selected, pool, sel_cfg)

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

def _enforce_narrative_diversity(
    selected: List[Tuple[Shot, ShotScore]],
    pool:     List[Tuple[Shot, ShotScore]],
    sel_cfg:  Dict[str, Any],
) -> List[Tuple[Shot, ShotScore]]:
    """
    Ensure the final selected set spans the cinematic vocabulary.

    Checks three diversity dimensions:
      - Shot scale: at least one wide/establishing shot if pool has any
      - Movement: at least one static and one moving shot if pool has both
      - Scene type: at least one exterior if pool has any exterior shots

    When a dimension is missing from the selection, the lowest-scoring
    selected shot that duplicates a well-represented category is swapped
    for the highest-scoring unselected shot that fills the gap.

    The swap only happens if the replacement shot scores above the
    diversity_min_score threshold — we never add a bad shot just for variety.

    This is a soft constraint — if the pool genuinely lacks variety
    (e.g. single-location interior film) the selection is unchanged.
    """
    if not selected or not pool:
        return selected

    diversity_min = float(sel_cfg.get("diversity_min_score", 35.0))
    enforce       = sel_cfg.get("enforce_narrative_diversity", True)
    if not enforce:
        return selected

    # build a lookup of unselected pool items sorted by score descending
    selected_ids  = {s.shot_id for s, _ in selected}
    unselected    = [(s, sc) for s, sc in pool if s.shot_id not in selected_ids]
    unselected    = sorted(unselected, key=lambda x: x[1].total_score or 0.0, reverse=True)

    result = list(selected)

    # --- dimension 1: shot scale diversity ---
    # need at least one wide/establishing if pool has any
    wide_scales = {"wide", "extreme_wide", "medium_wide"}
    close_scales= {"close", "extreme_close", "medium_close"}

    selected_scales = {s.shot_scale.value for s, _ in result if s.shot_scale}
    pool_scales     = {s.shot_scale.value for s, _ in pool  if s.shot_scale}

    has_wide_in_selection = bool(selected_scales & wide_scales)
    has_wide_in_pool      = bool(pool_scales     & wide_scales)
    has_close_in_selection= bool(selected_scales & close_scales)
    has_close_in_pool     = bool(pool_scales     & close_scales)

    if not has_wide_in_selection and has_wide_in_pool:
        result = _swap_for_category(
            result, unselected,
            lambda s: s.shot_scale and s.shot_scale.value in wide_scales,
            diversity_min,
            "wide shot",
        )

    if not has_close_in_selection and has_close_in_pool:
        result = _swap_for_category(
            result, unselected,
            lambda s: s.shot_scale and s.shot_scale.value in close_scales,
            diversity_min,
            "close-up",
        )

    # --- dimension 2: movement diversity ---
    # need at least one static and one moving shot if pool has both
    moving_types = {"pan", "tilt", "dolly", "handheld", "drone"}
    static_types = {"static"}

    selected_movements = {s.movement_type.value for s, _ in result if s.movement_type}
    pool_movements     = {s.movement_type.value for s, _ in pool  if s.movement_type}

    has_static_selected = bool(selected_movements & static_types)
    has_moving_selected = bool(selected_movements & moving_types)
    has_static_in_pool  = bool(pool_movements     & static_types)
    has_moving_in_pool  = bool(pool_movements     & moving_types)

    if not has_static_selected and has_static_in_pool:
        result = _swap_for_category(
            result, unselected,
            lambda s: s.movement_type and s.movement_type.value == "static",
            diversity_min,
            "static shot",
        )

    if not has_moving_selected and has_moving_in_pool:
        result = _swap_for_category(
            result, unselected,
            lambda s: s.movement_type and s.movement_type.value in moving_types,
            diversity_min,
            "moving shot",
        )

    # --- dimension 3: scene type diversity ---
    # need at least one exterior if pool has any
    exterior_types = {"exterior_day", "exterior_night"}
    interior_types = {"interior_day", "interior_night"}

    selected_scenes = {s.scene_type.value for s, _ in result if s.scene_type}
    pool_scenes     = {s.scene_type.value for s, _ in pool  if s.scene_type}

    has_exterior_selected = bool(selected_scenes & exterior_types)
    has_exterior_in_pool  = bool(pool_scenes     & exterior_types)

    if not has_exterior_selected and has_exterior_in_pool:
        result = _swap_for_category(
            result, unselected,
            lambda s: s.scene_type and s.scene_type.value in exterior_types,
            diversity_min,
            "exterior shot",
        )

    return result


def _swap_for_category(
    selected:     List[Tuple[Shot, ShotScore]],
    unselected:   List[Tuple[Shot, ShotScore]],
    matches:      Any,   # callable: Shot -> bool
    min_score:    float,
    label:        str,
) -> List[Tuple[Shot, ShotScore]]:
    """
    Try to swap the lowest-scoring over-represented shot in selected
    for the highest-scoring matching unselected shot above min_score.

    If no suitable replacement exists, returns selected unchanged.
    """
    # find best replacement candidate
    replacement = None
    for shot, score in unselected:
        if matches(shot) and (score.total_score or 0.0) >= min_score:
            replacement = (shot, score)
            break

    if replacement is None:
        return selected

    # find the lowest-scoring shot in selected that is not the only
    # representative of its own category (we don't want to remove the
    # only close-up to make room for a wide)
    sorted_selected = sorted(selected, key=lambda x: x[1].total_score or 0.0)
    victim = None
    for shot, score in sorted_selected:
        # skip if this shot is already in the target category — no point swapping it
        if matches(shot):
            continue
        # this shot is our candidate victim — take it
        # (we intentionally don't restrict to "same category must have other members"
        #  because with small top_k pools that always blocks the swap)
        victim = (shot, score)
        break

    if victim is None:
        return selected

    result = [item for item in selected if item[0].shot_id != victim[0].shot_id]
    result.append(replacement)
    print(f"[selection] diversity swap: added {label} (score {replacement[1].total_score:.1f}), "
          f"removed shot {victim[0].shot_id} (score {victim[1].total_score:.1f})")
    return result


def _apply_duration_weighting(
    pool:     List[Tuple[Shot, ShotScore]],
    min_dur:  float = 2.0,
    soft_min: float = 1.0,
) -> List[Tuple[Shot, ShotScore]]:
    """
    Apply duration-based filtering and score penalties.

    Hard exclude: shots shorter than soft_min seconds are removed entirely.
                  They are too short to be usable by any editor.

    Soft penalty: shots between soft_min and min_dur receive a score penalty
                  proportional to how far below min_dur they are.
                  A 1.5s shot with min_dur=2.0 gets a 25% score reduction.
                  This keeps them in the pool but pushes them toward the bottom
                  so the facility location algorithm avoids them unless there
                  are no better options.

    Both thresholds are configurable in config.yaml under selection:
        min_shot_duration_sec: 2.0   # soft penalty kicks in below this
        soft_min_duration_sec: 1.0   # hard exclusion below this
    """
    result = []
    excluded = 0

    for shot, score in pool:
        dur = shot.duration_sec

        # hard exclude — unusable
        if dur < soft_min:
            excluded += 1
            continue

        # soft penalty — usable but not ideal
        if dur < min_dur:
            penalty = (min_dur - dur) / min_dur   # 0.0 to 1.0
            if score.total_score is not None:
                score.total_score = round(
                    score.total_score * (1.0 - penalty * 0.4), 2
                )
            if score.technical_total is not None:
                score.technical_total = round(
                    score.technical_total * (1.0 - penalty * 0.4), 2
                )

        result.append((shot, score))

    if excluded > 0:
        print(f"[selection] excluded {excluded} shots below minimum duration ({soft_min}s)")

    # safety — never return empty pool
    if not result:
        print("[selection] warning: all shots excluded by duration filter — returning full pool")
        return pool

    return result


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
            "scene_type":       shot.scene_type.value   if shot.scene_type   else None,
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