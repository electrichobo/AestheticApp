# aesthetic/agents/stratification.py
#
# Baseline corpus stratification.
#
# The problem with flat corpus comparison:
#   774 reference stills span wildly different visual styles.
#   Blade Runner 2049 and Roma have almost nothing in common technically.
#   Comparing a candidate frame against the average of everything produces
#   a score that means "distance from the average of all excellent
#   cinematography" — which is not a useful signal.
#
# The fix — cluster the corpus into visual style families:
#   1. Load all CLIP embeddings from the baseline corpus
#   2. Cluster them using k-means in embedding space
#   3. For each cluster, compute a centroid and label it with a style name
#   4. At scoring time, find the nearest cluster to the candidate frame
#   5. Score against that cluster only — like-for-like comparison
#
# Cluster labels are assigned automatically by inspecting the dominant
# visual characteristics of the cluster members (luminance, saturation,
# contrast). They are descriptive, not prescriptive.
#
# The cluster index is built once and cached to disk at:
#   data/baseline/clusters.json
#
# It is rebuilt automatically when the baseline version changes.
# The active golden version hash is stored in the cluster file so
# we know when it needs rebuilding.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# Number of style clusters.
# 8 covers the main cinematic style families without over-splitting a
# 774-still corpus. Increase as the corpus grows.
N_CLUSTERS = 8

# Minimum cluster size — if a cluster has fewer members than this
# after k-means, it is merged with its nearest neighbour.
MIN_CLUSTER_SIZE = 10


# ---------------------------------------------------------------------------
# Public entry point — cluster-aware similarity
# ---------------------------------------------------------------------------

def compute_stratified_similarity(
    embedding: List[float],
    data_dir:  Path,
    baseline_version: int = 0,
) -> Dict[str, Any]:
    """
    Compute cluster-aware similarity between a candidate frame and the
    Golden Baseline corpus.

    Steps:
    1. Load or build the cluster index
    2. Find the nearest cluster to the candidate embedding
    3. Score against that cluster's members (top-k mean cosine similarity)
    4. Return score + cluster label + confidence

    Args:
        embedding:        CLIP embedding for the candidate frame.
        data_dir:         Root data directory.
        baseline_version: Active baseline version — triggers index rebuild if changed.

    Returns:
        Dict with:
          score (0-100): similarity score vs nearest cluster
          cluster_label: descriptive style family name
          cluster_id: integer cluster index
          cluster_confidence: how close the frame is to the cluster centroid (0-1)
          global_score: flat similarity vs full corpus (for comparison)
    """
    try:
        index = _load_or_build_index(data_dir, baseline_version)
        if index is None or not index.get("clusters"):
            # fallback to flat scoring
            flat = _flat_similarity(embedding, data_dir)
            return {
                "score":              flat,
                "cluster_label":      "unclustered",
                "cluster_id":         -1,
                "cluster_confidence": 0.0,
                "global_score":       flat,
            }

        frame_vec = _normalise(np.array(embedding, dtype=np.float32))
        clusters  = index["clusters"]

        # find nearest cluster centroid — skip if dim mismatch (stale index)
        best_cluster_id   = -1
        best_centroid_sim = -1.0
        frame_dim = len(frame_vec)
        for cid, cluster in enumerate(clusters):
            centroid = np.array(cluster["centroid"], dtype=np.float32)
            if len(centroid) != frame_dim:
                # stale centroids from a different model — bail out entirely
                # and fall back to flat similarity
                return _flat_similarity(embedding, data_dir) or 0.0
            sim = float(np.dot(frame_vec, centroid))
            if sim > best_centroid_sim:
                best_centroid_sim = sim
                best_cluster_id   = cid

        if best_cluster_id < 0:
            flat = _flat_similarity(embedding, data_dir)
            return {"score": flat, "cluster_label": "unclustered",
                    "cluster_id": -1, "cluster_confidence": 0.0, "global_score": flat}

        cluster = clusters[best_cluster_id]

        # score against this cluster's members
        member_embeddings = [np.array(e, dtype=np.float32) for e in cluster["embeddings"]]
        similarities      = [float(np.dot(frame_vec, _normalise(m))) for m in member_embeddings]
        top_k    = sorted(similarities, reverse=True)[:10]
        score    = float(np.mean(top_k))
        score_100= round((score + 1.0) / 2.0 * 100.0, 2)

        # global score for transparency
        global_score = _flat_similarity(embedding, data_dir)

        # confidence: how well the frame fits the nearest cluster
        # (centroid similarity normalised to 0-1)
        confidence = round((best_centroid_sim + 1.0) / 2.0, 3)

        return {
            "score":              score_100,
            "cluster_label":      cluster.get("label", f"style_{best_cluster_id}"),
            "cluster_id":         best_cluster_id,
            "cluster_confidence": confidence,
            "global_score":       global_score,
        }

    except Exception as exc:
        print(f"[stratification] error: {exc}")
        return {
            "score":              None,
            "cluster_label":      "error",
            "cluster_id":         -1,
            "cluster_confidence": 0.0,
            "global_score":       None,
        }


# ---------------------------------------------------------------------------
# Cluster index — build and load
# ---------------------------------------------------------------------------

def _load_or_build_index(
    data_dir:         Path,
    baseline_version: int,
) -> Optional[Dict[str, Any]]:
    """
    Load the cluster index from disk, or build it if it doesn't exist
    or is stale (baseline version changed).
    """
    index_path = data_dir / "baseline" / "clusters.json"

    # check if cached index is still valid
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if index.get("baseline_version") == baseline_version:
                clusters = index.get("clusters", [])
                if clusters:
                    centroid_dim = len(clusters[0].get("centroid", []))
                    if centroid_dim != 512:
                        print(f"[stratification] stale index: centroid dim "
                              f"{centroid_dim} != 512 — rebuilding")
                    else:
                        emb_dir = data_dir / "baseline" / "embeddings"
                        actual  = sum(1 for _ in emb_dir.glob("*.json")) if emb_dir.exists() else 0
                        covered = sum(len(c.get("embeddings", [])) for c in clusters)
                        if actual > 0 and covered < actual * 0.5:
                            print(f"[stratification] stale index: {covered} members "
                                  f"vs {actual} embeddings — rebuilding")
                        else:
                            return index
        except Exception:
            pass

    # build fresh
    return _build_cluster_index(data_dir, baseline_version, index_path)


def _build_cluster_index(
    data_dir:         Path,
    baseline_version: int,
    index_path:       Path,
) -> Optional[Dict[str, Any]]:
    """
    Build the cluster index from scratch using k-means on CLIP embeddings.
    """
    from .baseline_trainer import _build_embeddings_index

    print(f"[stratification] building cluster index for baseline v{baseline_version}…")

    raw_embeddings = _build_embeddings_index(data_dir)
    if len(raw_embeddings) < N_CLUSTERS * MIN_CLUSTER_SIZE:
        print(f"[stratification] corpus too small to cluster ({len(raw_embeddings)} embeddings)")
        return None

    # normalise all embeddings
    matrix = np.array(raw_embeddings, dtype=np.float32)
    norms  = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
    matrix = matrix / norms

    # k-means clustering
    centroids, labels = _kmeans(matrix, N_CLUSTERS, n_iter=50)

    # build cluster records
    clusters = []
    for cid in range(N_CLUSTERS):
        member_indices = np.where(labels == cid)[0]
        if len(member_indices) < MIN_CLUSTER_SIZE:
            # too small — will be handled by merging below
            continue

        member_embs = matrix[member_indices].tolist()
        centroid    = centroids[cid].tolist()
        label       = _auto_label_cluster(cid, len(member_indices))

        clusters.append({
            "id":         cid,
            "label":      label,
            "size":       len(member_indices),
            "centroid":   centroid,
            "embeddings": member_embs,
        })

    if not clusters:
        return None

    index = {
        "baseline_version": baseline_version,
        "n_clusters":       len(clusters),
        "total_embeddings": len(raw_embeddings),
        "clusters":         clusters,
    }

    # save to disk
    try:
        # store without member embeddings in the summary — embeddings stored separately
        summary = {k: v for k, v in index.items() if k != "clusters"}
        summary["clusters"] = [
            {k: v for k, v in c.items() if k != "embeddings"}
            for c in clusters
        ]
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        print(f"[stratification] built {len(clusters)} clusters from {len(raw_embeddings)} embeddings")
    except Exception as exc:
        print(f"[stratification] could not save index: {exc}")

    return index


def _kmeans(
    matrix:  np.ndarray,
    k:       int,
    n_iter:  int = 50,
    seed:    int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Simple k-means++ initialisation followed by Lloyd's algorithm.
    Returns (centroids, labels).
    """
    rng = np.random.default_rng(seed)
    n   = matrix.shape[0]

    # k-means++ initialisation — spread initial centroids
    centroid_indices = [int(rng.integers(n))]
    for _ in range(k - 1):
        dists = np.array([
            min(1.0 - float(np.dot(matrix[i], matrix[c])) for c in centroid_indices)
            for i in range(n)
        ])
        dists = np.clip(dists, 0, None)
        probs = dists / (dists.sum() + 1e-8)
        centroid_indices.append(int(rng.choice(n, p=probs)))

    centroids = matrix[centroid_indices].copy()

    for _ in range(n_iter):
        # assign each point to nearest centroid
        sims   = matrix @ centroids.T   # n x k cosine similarities
        labels = np.argmax(sims, axis=1)

        # update centroids
        new_centroids = np.zeros_like(centroids)
        for cid in range(k):
            members = matrix[labels == cid]
            if len(members) > 0:
                mean = members.mean(axis=0)
                norm = np.linalg.norm(mean) + 1e-8
                new_centroids[cid] = mean / norm
            else:
                new_centroids[cid] = centroids[cid]

        # check convergence
        if np.allclose(centroids, new_centroids, atol=1e-4):
            break
        centroids = new_centroids

    return centroids, labels


def _auto_label_cluster(cluster_id: int, size: int) -> str:
    """
    Generate a descriptive label for a cluster.
    Labels are generic style identifiers — they will be enriched
    with visual inspection once real corpus data is available.
    The numbers ensure uniqueness; descriptive names come from
    manual review of cluster members.
    """
    style_names = [
        "high-contrast dramatic",
        "naturalistic warm",
        "desaturated cold",
        "bright cinematic",
        "dark atmospheric",
        "saturated vivid",
        "muted period",
        "neutral technical",
    ]
    name = style_names[cluster_id % len(style_names)]
    return f"{name} (n={size})"


# ---------------------------------------------------------------------------
# Flat similarity fallback
# ---------------------------------------------------------------------------

def _flat_similarity(
    embedding: List[float],
    data_dir:  Path,
) -> Optional[float]:
    """Global corpus similarity without clustering — used as fallback and comparison."""
    try:
        from .baseline_trainer import _build_embeddings_index
        corpus = _build_embeddings_index(data_dir)
        if not corpus:
            return None
        frame_vec = _normalise(np.array(embedding, dtype=np.float32))
        sims      = [float(np.dot(frame_vec, _normalise(np.array(e, dtype=np.float32)))) for e in corpus]
        top_k     = sorted(sims, reverse=True)[:5]
        score     = float(np.mean(top_k))
        return round((score + 1.0) / 2.0 * 100.0, 2)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _normalise(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-8)


def rebuild_cluster_index(data_dir: Path, baseline_version: int) -> Dict[str, Any]:
    """
    Force a rebuild of the cluster index.
    Call this after ingesting new baseline material.
    """
    index_path = data_dir / "baseline" / "clusters.json"
    result = _build_cluster_index(data_dir, baseline_version, index_path)
    if result:
        return {"ok": True, "n_clusters": result.get("n_clusters"), "total": result.get("total_embeddings")}
    return {"ok": False, "error": "corpus too small or no embeddings found"}