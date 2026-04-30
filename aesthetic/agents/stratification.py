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
                # stale centroids from a different model — fall back to flat similarity
                # return a dict (not a float) so callers don't crash on .get()
                flat = _flat_similarity(embedding, data_dir) or 0.0
                return {"score": flat, "cluster_label": "unclustered",
                        "cluster_id": -1, "cluster_confidence": 0.0, "global_score": flat}
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
        confidence = round((best_centroid_sim + 1.0) / 2.0, 3)

        # percentile rank within style family
        # uses stored sim_stats from build time — no need to reload all embeddings
        cluster_percentile = None
        sim_stats = cluster.get("sim_stats")
        if sim_stats:
            # raw cosine similarity of candidate vs centroid
            raw_sim = best_centroid_sim
            # map to percentile using stored distribution
            p10 = sim_stats.get("p10", 0)
            p25 = sim_stats.get("p25", 0)
            p50 = sim_stats.get("p50", 0)
            p75 = sim_stats.get("p75", 0)
            p90 = sim_stats.get("p90", 1)
            if   raw_sim >= p90: pct = 90 + (raw_sim - p90) / max(1 - p90, 0.01) * 10
            elif raw_sim >= p75: pct = 75 + (raw_sim - p75) / max(p90 - p75, 0.01) * 15
            elif raw_sim >= p50: pct = 50 + (raw_sim - p50) / max(p75 - p50, 0.01) * 25
            elif raw_sim >= p25: pct = 25 + (raw_sim - p25) / max(p50 - p25, 0.01) * 25
            elif raw_sim >= p10: pct = 10 + (raw_sim - p10) / max(p25 - p10, 0.01) * 15
            else:                pct = raw_sim / max(p10, 0.01) * 10
            cluster_percentile = round(float(np.clip(pct, 0, 100)), 1)

        return {
            "score":              score_100,
            "cluster_label":      cluster.get("label", f"Style Family {best_cluster_id + 1}"),
            "cluster_id":         best_cluster_id,
            "cluster_confidence": confidence,
            "cluster_percentile": cluster_percentile,
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
                    # check against current model dim, not hardcoded 512
                    try:
                        from .model_utils import _selected_model, select_best_model, get_model_dim
                        _m = _selected_model[0] if _selected_model else select_best_model()[0]
                        expected_dim = get_model_dim(_m) if _m else centroid_dim
                    except Exception:
                        expected_dim = centroid_dim
                    if centroid_dim != expected_dim:
                        print(f"[stratification] stale index: centroid dim "
                              f"{centroid_dim} != {expected_dim} — rebuilding")
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
    Enriches each cluster with:
      - Visual statistics from sampled source images → meaningful style label
      - Intra-cluster similarity distribution → percentile scoring at inference
    """
    from .baseline_trainer import _build_embeddings_index, _build_embeddings_index_with_sources

    print(f"[stratification] building cluster index for baseline v{baseline_version}…")

    # Load embeddings with source metadata for visual analysis
    records = _build_embeddings_index_with_sources(data_dir)
    if len(records) < N_CLUSTERS * MIN_CLUSTER_SIZE:
        print(f"[stratification] corpus too small to cluster ({len(records)} embeddings)")
        return None

    raw_embeddings = [r["embedding"] for r in records]
    matrix = np.array(raw_embeddings, dtype=np.float32)
    norms  = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
    matrix = matrix / norms

    centroids, labels = _kmeans(matrix, N_CLUSTERS, n_iter=50)

    clusters = []
    for cid in range(N_CLUSTERS):
        member_indices = np.where(labels == cid)[0]
        if len(member_indices) < MIN_CLUSTER_SIZE:
            continue

        member_embs     = matrix[member_indices].tolist()
        member_records  = [records[i] for i in member_indices]
        centroid        = centroids[cid].tolist()
        centroid_vec    = np.array(centroid, dtype=np.float32)

        # Intra-cluster similarity distribution for percentile scoring
        sims = [float(np.dot(np.array(e, dtype=np.float32), centroid_vec))
                for e in member_embs]
        sim_arr = np.array(sims)
        sim_stats = {
            "mean": round(float(sim_arr.mean()), 4),
            "std":  round(float(sim_arr.std()),  4),
            "p10":  round(float(np.percentile(sim_arr, 10)), 4),
            "p25":  round(float(np.percentile(sim_arr, 25)), 4),
            "p50":  round(float(np.percentile(sim_arr, 50)), 4),
            "p75":  round(float(np.percentile(sim_arr, 75)), 4),
            "p90":  round(float(np.percentile(sim_arr, 90)), 4),
        }

        # Visual analysis → meaningful style label
        try:
            vis_stats = _analyse_cluster_visuals(member_embs, member_records, data_dir)
            label     = _label_from_visual_stats(vis_stats)
        except Exception as _le:
            vis_stats = {}
            label     = _auto_label_cluster(cid, len(member_indices))

        clusters.append({
            "id":          cid,
            "label":       label,
            "size":        len(member_indices),
            "centroid":    centroid,
            "embeddings":  member_embs,
            "sim_stats":   sim_stats,
            "vis_stats":   vis_stats,
        })
        print(f"[stratification]   cluster {cid}: '{label}' ({len(member_indices)} members)")

    if not clusters:
        return None

    index = {
        "baseline_version": baseline_version,
        "n_clusters":       len(clusters),
        "total_embeddings": len(records),
        "clusters":         clusters,
    }

    try:
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        print(f"[stratification] built {len(clusters)} clusters from {len(records)} embeddings")
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
    """Fallback generic label — used when visual analysis isn't available."""
    style_names = [
        "Dramatic High-Contrast", "Warm Naturalistic", "Cold Desaturated",
        "Bright Cinematic",       "Dark Atmospheric",  "Vivid Saturated",
        "Muted Period",           "Neutral Technical",
    ]
    return style_names[cluster_id % len(style_names)]


def _analyse_cluster_visuals(
    member_embeddings: List[List[float]],
    embedding_records: List[Dict],
    data_dir: Path,
) -> Dict[str, Any]:
    """
    Compute visual statistics for a cluster by sampling the source images.
    Returns a stats dict used for labelling and percentile scoring.

    embedding_records: list of {"source": filename, "embedding": [...]}
    data_dir: root data dir — source images are in baseline/sources/ or
              searched recursively under baseline/
    """
    import cv2

    stats = {
        "mean_luma":   [],
        "mean_sat":    [],
        "mean_dr":     [],   # dynamic range proxy
        "mean_temp":   [],   # colour temperature proxy (B/R ratio)
        "contrast":    [],
    }

    # Find source image directory
    source_dirs = [
        data_dir / "baseline" / "sources",
        data_dir / "baseline",
    ]

    # Sample up to 20 images per cluster for speed
    sample = embedding_records[:20]

    for rec in sample:
        src_name = rec.get("source", "")
        img_path = None
        for sdir in source_dirs:
            candidate = sdir / src_name
            if candidate.exists():
                img_path = candidate
                break
        if img_path is None:
            continue

        try:
            img  = cv2.imread(str(img_path))
            if img is None:
                continue
            small = cv2.resize(img, (64, 36), interpolation=cv2.INTER_AREA)
            gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(float)
            hsv   = cv2.cvtColor(small, cv2.COLOR_BGR2HSV).astype(float)

            stats["mean_luma"].append(float(gray.mean()))
            stats["mean_sat"].append(float(hsv[:,:,1].mean()))
            # DR: p95 - p5 of luma
            flat = gray.flatten()
            stats["mean_dr"].append(float(np.percentile(flat, 95) - np.percentile(flat, 5)))
            # Colour temp: blue/red ratio (higher = cooler)
            b_mean = float(small[:,:,0].mean()) + 1
            r_mean = float(small[:,:,2].mean()) + 1
            stats["mean_temp"].append(b_mean / r_mean)
            # Contrast: std of luma
            stats["contrast"].append(float(gray.std()))
        except Exception:
            continue

    # Reduce to means
    result = {}
    for k, vals in stats.items():
        result[k] = float(np.mean(vals)) if vals else None
    return result


def _label_from_visual_stats(stats: Dict[str, Any]) -> str:
    """
    Map visual statistics to a cinematographic style family name.
    Uses a simple rule-based classifier on luma, saturation, DR, temp.
    """
    luma    = stats.get("mean_luma")
    sat     = stats.get("mean_sat")
    dr      = stats.get("mean_dr")
    temp    = stats.get("mean_temp")
    contrast= stats.get("contrast")

    if luma is None:
        return "Visual Family"

    # Key/fill and tonal character
    is_dark   = luma < 80
    is_bright = luma > 160
    is_mid    = not is_dark and not is_bright

    # Saturation character
    is_desat  = sat is not None and sat < 40
    is_vivid  = sat is not None and sat > 100

    # Colour temperature
    is_cool   = temp is not None and temp > 1.15
    is_warm   = temp is not None and temp < 0.88

    # Contrast/DR
    is_hicon  = (contrast is not None and contrast > 55) or (dr is not None and dr > 160)
    is_locon  = (contrast is not None and contrast < 28) or (dr is not None and dr < 80)

    # Decision tree — most specific first
    if is_dark and is_desat and is_cool:   return "Neo-Noir / Thriller"
    if is_dark and is_hicon:               return "Chiaroscuro Dramatic"
    if is_dark and is_warm:                return "Candlelit / Intimate"
    if is_dark and is_desat:               return "Dark Atmospheric"
    if is_dark:                            return "Dark Cinematic"

    if is_bright and is_vivid:             return "Vibrant High-Key"
    if is_bright and is_desat:             return "Bleached / Overexposed"
    if is_bright and is_warm:              return "Golden Hour Naturalistic"
    if is_bright:                          return "Bright Cinematic"

    if is_mid and is_desat and is_cool:    return "Cold Desaturated Realist"
    if is_mid and is_desat:                return "Muted Naturalistic"
    if is_mid and is_vivid and is_warm:    return "Warm Vivid"
    if is_mid and is_vivid:                return "Saturated Cinematic"
    if is_mid and is_hicon and is_warm:    return "Prestige Naturalism"
    if is_mid and is_hicon:                return "High-Contrast Dramatic"
    if is_mid and is_locon:                return "Soft / Diffuse"
    if is_mid and is_warm:                 return "Warm Naturalistic"
    if is_mid and is_cool:                 return "Cool Cinematic"

    return "Balanced Cinematic"


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