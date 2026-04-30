"""
aesthetic/agents/scene_clusters.py

Scene / shot clustering — Phase 3.

Groups the selected shots from a run into visual families using:
  - SigLIP embedding cosine similarity (primary signal)
  - Palette distance in CIE Lab xy space (secondary)
  - Scene type and shot scale agreement (soft bonus)

Uses agglomerative clustering with a cosine distance threshold —
no need to specify k. Cluster count emerges from the data.

Each cluster gets:
  - A representative shot (highest scoring member)
  - A label derived from the dominant scene_type / shot_scale in the cluster
  - A coherence score (mean intra-cluster similarity)

Public API:
    cluster_shots(shots, config) → ClusterResult
    attach_clusters_to_shots(shots, result) → shots (with cluster_id added)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

DEFAULT_DISTANCE_THRESHOLD = 0.35   # cosine distance; lower = tighter clusters
DEFAULT_MIN_CLUSTER_SIZE   = 1      # single-shot clusters are valid
DEFAULT_PALETTE_WEIGHT     = 0.15   # palette distance contribution
DEFAULT_SEMANTIC_BONUS     = 0.08   # same scene_type / scale reduces distance


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ShotCluster:
    cluster_id:      int
    shot_ids:        List[str]
    representative:  str              # shot_id of best shot in cluster
    label:           str              # human-readable label
    coherence:       float            # mean intra-cluster cosine similarity 0-1
    dominant_scale:  Optional[str]   = None
    dominant_scene:  Optional[str]   = None
    mean_score:      float           = 0.0


@dataclass
class ClusterResult:
    clusters:        List[ShotCluster]
    shot_cluster_map: Dict[str, int]  # shot_id → cluster_id
    n_clusters:      int
    method:          str = "agglomerative_cosine"


# ---------------------------------------------------------------------------
# Distance matrix
# ---------------------------------------------------------------------------

def _cosine_distance_matrix(embeddings: np.ndarray) -> np.ndarray:
    """
    Pairwise cosine distance matrix. Embeddings assumed L2-normalised.
    cosine_distance = 1 - dot_product (for unit vectors).
    """
    # Ensure normalised
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    safe  = np.where(norms > 1e-8, norms, 1.0)
    normed = embeddings / safe

    sim = normed @ normed.T
    sim = np.clip(sim, -1.0, 1.0)
    return 1.0 - sim   # cosine distance


def _palette_distance_matrix(shots: List[Dict]) -> Optional[np.ndarray]:
    """
    Pairwise palette distance in xy chromaticity space.
    Uses the mean of dominant_colours per shot.
    Returns None if palette data isn't available for enough shots.
    """
    n   = len(shots)
    mat = np.zeros((n, n), dtype=np.float32)

    centroids = []
    for s in shots:
        cols = s.get("dominant_colours") or []
        if cols:
            # weighted mean of xy coordinates
            xy = np.array([[c[0], c[1]] for c in cols if len(c) >= 2], dtype=np.float32)
            wt = np.array([c[2] if len(c) >= 3 else 1.0 for c in cols], dtype=np.float32)
            wt = wt / (wt.sum() + 1e-8)
            centroids.append((xy * wt[:, None]).sum(axis=0))
        else:
            centroids.append(None)

    available = sum(1 for c in centroids if c is not None)
    if available < len(shots) * 0.5:
        return None

    for i in range(n):
        for j in range(i + 1, n):
            if centroids[i] is not None and centroids[j] is not None:
                d = float(np.linalg.norm(centroids[i] - centroids[j]))
                # xy distance is small (0-0.8 range) — normalise to 0-1
                d_norm = min(1.0, d / 0.4)
                mat[i, j] = d_norm
                mat[j, i] = d_norm

    return mat


def _semantic_bonus_matrix(shots: List[Dict], bonus: float) -> np.ndarray:
    """
    Reduce distance by `bonus` when two shots share scene_type or shot_scale.
    """
    n   = len(shots)
    mat = np.zeros((n, n), dtype=np.float32)

    for i in range(n):
        for j in range(i + 1, n):
            reduction = 0.0
            si, sj = shots[i], shots[j]
            if (si.get("scene_type") and si["scene_type"] == sj.get("scene_type")
                    and si["scene_type"] != "unknown"):
                reduction += bonus * 0.5
            if (si.get("shot_scale") and si["shot_scale"] == sj.get("shot_scale")
                    and si["shot_scale"] not in ("unknown", None)):
                reduction += bonus * 0.5
            mat[i, j] = reduction
            mat[j, i] = reduction

    return mat


# ---------------------------------------------------------------------------
# Agglomerative clustering (no scipy required)
# ---------------------------------------------------------------------------

def _agglomerative_cluster(
    dist_mat:  np.ndarray,
    threshold: float,
) -> List[int]:
    """
    Simple single-linkage agglomerative clustering.
    Returns a list of cluster labels (0-indexed).
    Merges any two clusters where min inter-cluster distance < threshold.
    """
    n      = len(dist_mat)
    labels = list(range(n))

    changed = True
    while changed:
        changed = False
        # Find the closest pair from different clusters
        best_dist = threshold
        best_i    = -1
        best_j    = -1

        for i in range(n):
            for j in range(i + 1, n):
                if labels[i] != labels[j] and dist_mat[i, j] < best_dist:
                    best_dist = dist_mat[i, j]
                    best_i    = i
                    best_j    = j

        if best_i >= 0:
            # merge cluster of j into cluster of i
            old_label = labels[best_j]
            new_label = labels[best_i]
            labels = [new_label if l == old_label else l for l in labels]
            changed = True

    # Remap to contiguous 0-indexed labels
    unique = sorted(set(labels))
    remap  = {old: new for new, old in enumerate(unique)}
    return [remap[l] for l in labels]


# ---------------------------------------------------------------------------
# Cluster labelling
# ---------------------------------------------------------------------------

def _cluster_label(shots_in_cluster: List[Dict]) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Generate a human-readable label for a cluster from its shots.
    Returns (label, dominant_scale, dominant_scene).
    """
    from collections import Counter

    scales = [s.get("shot_scale")  for s in shots_in_cluster if s.get("shot_scale")  not in (None, "unknown")]
    scenes = [s.get("scene_type")  for s in shots_in_cluster if s.get("scene_type")  not in (None, "unknown")]
    moves  = [s.get("movement_type") for s in shots_in_cluster if s.get("movement_type") not in (None, "unknown")]

    dom_scale = Counter(scales).most_common(1)[0][0] if scales else None
    dom_scene = Counter(scenes).most_common(1)[0][0] if scenes else None
    dom_move  = Counter(moves).most_common(1)[0][0]  if moves  else None

    parts = []
    if dom_scene and dom_scene != "unknown":
        parts.append(dom_scene.replace("_", " ").title())
    if dom_scale and dom_scale != "unknown":
        parts.append(dom_scale.replace("_", " ").title())
    if dom_move and dom_move not in ("unknown", "static") and not parts:
        parts.append(dom_move.replace("_", " ").title())

    label = " · ".join(parts) if parts else "Visual Family"
    return label, dom_scale, dom_scene


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def cluster_shots(
    shots:  List[Dict[str, Any]],
    config: Dict[str, Any] = {},
) -> ClusterResult:
    """
    Cluster selected shots by visual similarity.

    shots:  list of shot dicts from select_shots() — must include
            mean_embedding, dominant_colours, scene_type, shot_scale,
            total_score, shot_id.

    Returns ClusterResult with per-cluster metadata and shot → cluster map.
    """
    if not shots:
        return ClusterResult(clusters=[], shot_cluster_map={}, n_clusters=0)

    cluster_cfg   = config.get("clustering", {})
    threshold     = float(cluster_cfg.get("distance_threshold", DEFAULT_DISTANCE_THRESHOLD))
    palette_w     = float(cluster_cfg.get("palette_weight",     DEFAULT_PALETTE_WEIGHT))
    semantic_b    = float(cluster_cfg.get("semantic_bonus",     DEFAULT_SEMANTIC_BONUS))

    n = len(shots)

    # --- Build distance matrix ---
    # Primary: embedding cosine distance
    embeddings = np.array([
        s.get("mean_embedding") or [0.0] * 1152
        for s in shots
    ], dtype=np.float32)

    # Check all embeddings are same dim; fall back to zeros if mixed
    dims = set(len(s.get("mean_embedding") or []) for s in shots)
    if len(dims) > 1 or 0 in dims:
        # Some shots missing embeddings — use identity clustering
        print("[clusters] mixed/missing embeddings — skipping embedding clustering")
        embeddings = np.eye(n, dtype=np.float32)

    dist = _cosine_distance_matrix(embeddings)

    # Secondary: palette distance
    pal = _palette_distance_matrix(shots)
    if pal is not None:
        dist = dist + pal * palette_w

    # Soft: semantic bonus
    bonus = _semantic_bonus_matrix(shots, semantic_b)
    dist  = np.clip(dist - bonus, 0.0, 2.0)

    # --- Cluster ---
    labels = _agglomerative_cluster(dist, threshold)
    n_clusters = max(labels) + 1 if labels else 0

    print(f"[clusters] {n} shots → {n_clusters} clusters (threshold {threshold:.2f})")

    # --- Build ShotCluster objects ---
    shot_cluster_map: Dict[str, int] = {}
    clusters_raw: Dict[int, List[int]] = {}

    for idx, label in enumerate(labels):
        shot_cluster_map[shots[idx]["shot_id"]] = label
        clusters_raw.setdefault(label, []).append(idx)

    clusters: List[ShotCluster] = []

    for cid in sorted(clusters_raw.keys()):
        indices = clusters_raw[cid]
        members = [shots[i] for i in indices]

        # Representative: highest scoring member
        rep_idx = max(indices, key=lambda i: shots[i].get("total_score") or 0)
        rep_id  = shots[rep_idx]["shot_id"]

        # Coherence: mean intra-cluster similarity
        if len(indices) > 1:
            sub = dist[np.ix_(indices, indices)]
            # upper triangle only, convert distance → similarity
            tri  = sub[np.triu_indices(len(indices), k=1)]
            coherence = round(float(1.0 - tri.mean()), 3)
        else:
            coherence = 1.0

        label_str, dom_scale, dom_scene = _cluster_label(members)
        mean_score = round(
            float(np.mean([s.get("total_score") or 0 for s in members])), 1
        )

        clusters.append(ShotCluster(
            cluster_id=cid,
            shot_ids=[shots[i]["shot_id"] for i in indices],
            representative=rep_id,
            label=label_str,
            coherence=coherence,
            dominant_scale=dom_scale,
            dominant_scene=dom_scene,
            mean_score=mean_score,
        ))

    return ClusterResult(
        clusters=clusters,
        shot_cluster_map=shot_cluster_map,
        n_clusters=n_clusters,
    )


def attach_clusters_to_shots(
    shots:  List[Dict[str, Any]],
    result: ClusterResult,
) -> List[Dict[str, Any]]:
    """
    Add cluster_id and is_representative flags to each shot dict in place.
    """
    reps = {c.representative for c in result.clusters}
    for s in shots:
        sid = s.get("shot_id", "")
        s["cluster_id"]       = result.shot_cluster_map.get(sid)
        s["is_representative"] = sid in reps
    return shots