# aesthetic/agents/baseline_trainer.py
#
# Golden Baseline trainer.
# Ingests reference stills (or extracted video frames) from a source folder,
# generates CLIP embeddings for each, and stores them in the BaselineStore.
#
# Workflow:
#   1. Scan source folder for image files
#   2. For each image, generate a CLIP embedding via the inference pipeline
#   3. Store embeddings in the staging buffer of BaselineStore
#   4. Optionally promote staging to a new versioned golden file
#
# The baseline stores two things per reference still:
#   - The CLIP embedding vector (for Creative pillar cosine similarity scoring)
#   - Technical metric summary (for Subjective pillar reference distribution)
#
# Adding new material:
#   - New stills go into augment buffer, not staging
#   - Augment is merged with the active golden on next promotion
#   - This preserves the original corpus while extending it
#
# Version history is immutable — every golden version is kept on disk.
# Manifests reference the version hash so results are always reproducible.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..baseline import BaselineStore
from ..agents.inference import _run_clip, _get_device
from ..agents.metrics import compute_frame_metrics
from ..config import DATA_DIR


# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def train_baseline_from_folder(
    source_dir:  str,
    data_dir:    Path,
    config:      Dict[str, Any],
    note:        str = "",
    mode:        str = "staging",
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Ingest all images in source_dir and add them to the Golden Baseline.

    Args:
        source_dir:  Path to folder containing reference stills.
        data_dir:    Root data directory (baseline lives under data_dir/baseline/).
        config:      Full config dict.
        note:        Description stamped into the golden version metadata.
        mode:        "staging" for initial corpus build (promotes to new golden).
                     "augment" for adding new material to an existing golden.
        progress_cb: Optional callback(current, total, filename) for UI progress.

    Returns:
        Summary dict with counts and baseline version info.
    """
    source_path = Path(source_dir)
    if not source_path.exists():
        return {"ok": False, "error": f"Source directory not found: {source_dir}"}

    images = _scan_images(source_path)
    if not images:
        return {"ok": False, "error": f"No supported image files found in: {source_dir}"}

    features  = config.get("features", {})
    gpu       = bool(features.get("gpu_enabled", False))
    device    = _get_device(gpu)

    store     = BaselineStore(data_dir)
    processed = 0
    failed    = 0
    errors    = []

    for idx, img_path in enumerate(images, start=1):
        if progress_cb:
            progress_cb(idx, len(images), img_path.name)

        result = _process_reference_still(img_path, device, config, data_dir)

        if result is None:
            failed += 1
            errors.append(str(img_path.name))
            continue

        # add to the appropriate buffer
        if mode == "augment":
            store.update_augment([result])
        else:
            store.update_staging([result])

        processed += 1

    # promote to golden
    promotion: Dict[str, Any] = {}
    if processed > 0:
        if mode == "augment":
            promotion = store.apply_augment_to_new_golden(
                note=note or f"augmented with {processed} new stills"
            )
        else:
            promotion = store.promote_staging_to_golden(
                note=note or f"initial corpus: {processed} reference stills"
            )

    return {
        "ok":        True,
        "processed": processed,
        "failed":    failed,
        "errors":    errors[:20],   # cap error list for display
        "promotion": promotion,
        "total":     len(images),
    }


def get_baseline_status(data_dir: Path) -> Dict[str, Any]:
    """
    Return a summary of the current baseline state for UI display.
    """
    store = BaselineStore(data_dir)
    return store.get_summary()


# ---------------------------------------------------------------------------
# Per-image processing
# ---------------------------------------------------------------------------

def _process_reference_still(
    img_path: Path,
    device:   str,
    config:   Dict[str, Any],
    data_dir: Path,
) -> Optional[Dict[str, Any]]:
    """
    Process a single reference still:
    - Validate it can be loaded
    - Generate CLIP embedding
    - Compute a lightweight technical metric summary
    - Return a flat dict suitable for BaselineStore.update_staging()

    Returns None on failure.
    """
    try:
        # validate image loads
        img = cv2.imread(str(img_path))
        if img is None:
            return None
        if img.shape[0] < 64 or img.shape[1] < 64:
            return None   # too small to be useful

        # CLIP embedding
        embedding, version = _run_clip(str(img_path), device)
        if embedding is None:
            return None

        # lightweight technical metrics (reuse metrics engine)
        tech = _compute_reference_metrics(img)

        # build the record stored in BaselineStore
        # each key becomes a metric dimension in the online statistics
        record: Dict[str, Any] = {
            # store embedding as a serialized key
            # BaselineStore tracks numeric stats — embeddings stored separately
            "clip_embedding_dim": float(len(embedding)),

            # technical metric seeds for Subjective pillar reference distribution
            "histogram_mean":       tech.get("histogram_mean",       0.0),
            "histogram_std":        tech.get("histogram_std",        0.0),
            "highlight_clip_pct":   tech.get("highlight_clip_pct",   0.0),
            "shadow_clip_pct":      tech.get("shadow_clip_pct",      0.0),
            "snr_luma":             tech.get("snr_luma",             0.0),
            "sharpness_laplacian":  tech.get("sharpness_laplacian",  0.0),
            "saturation_mean":      tech.get("saturation_mean",      0.0),
            "wb_deviation":         tech.get("wb_deviation",         0.0),
            "dynamic_range_stops":  tech.get("dynamic_range_stops",  0.0),
            "palette_entropy":      tech.get("palette_entropy",      0.0),
        }

        # store embedding separately in a companion file
        _store_embedding(img_path, embedding, version, data_dir)

        return record

    except Exception as exc:
        print(f"[trainer] Failed to process {img_path.name}: {exc}")
        return None


def _compute_reference_metrics(img: np.ndarray) -> Dict[str, float]:
    """
    Compute a lightweight metric summary for a reference still.
    Uses direct numpy/opencv rather than the full FrameMetrics pipeline
    to keep training fast — we only need the distribution anchors.
    """
    results: Dict[str, float] = {}

    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        flat = gray.flatten()

        results["histogram_mean"]     = round(float(np.mean(flat)), 2)
        results["histogram_std"]      = round(float(np.std(flat)),  2)
        results["highlight_clip_pct"] = round(float(np.sum(flat >= 250) / len(flat) * 100.0), 3)
        results["shadow_clip_pct"]    = round(float(np.sum(flat <= 5)   / len(flat) * 100.0), 3)

        # SNR proxy
        signal = float(np.mean(flat))
        noise  = float(np.std(flat)) + 1e-6
        results["snr_luma"] = round(20.0 * np.log10(signal / noise) if signal > 0 else 0.0, 2)

        # sharpness
        lap = cv2.Laplacian(gray.astype(np.uint8), cv2.CV_32F)
        results["sharpness_laplacian"] = round(float(lap.var()), 2)

        # color metrics
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2Lab).astype(np.float32)
        a, b = lab[:, :, 1], lab[:, :, 2]
        chroma = np.sqrt(a**2 + b**2)
        results["saturation_mean"] = round(float(np.mean(chroma)), 2)
        results["wb_deviation"]    = round(float(np.sqrt(float(np.mean(a))**2 + float(np.mean(b))**2)), 3)

        # dynamic range proxy
        L = lab[:, :, 0]
        p2, p98 = np.percentile(L, 2), np.percentile(L, 98)
        dr = float(p98 - p2)
        results["dynamic_range_stops"] = round(np.log2(dr / 100.0 * 255.0 + 1.0), 2) if dr > 0 else 0.0

        # palette entropy
        hsv     = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        hue     = hsv[:, :, 0].flatten().astype(np.float32)
        hist, _ = np.histogram(hue, bins=36, range=(0, 180))
        hist    = hist.astype(np.float32) + 1e-6
        hist   /= hist.sum()
        results["palette_entropy"] = round(float(-np.sum(hist * np.log2(hist))), 4)

    except Exception:
        pass

    return results


def _store_embedding(
    img_path:  Path,
    embedding: List[float],
    version:   Optional[str],
    data_dir:  Path,
) -> None:
    """
    Store the CLIP embedding for a reference still in the baseline embeddings index.
    All embeddings are stored in data/baseline/embeddings/<stem>.json.
    This file is what compute_baseline_similarity() reads at scoring time.
    """
    embeddings_dir = data_dir / "baseline" / "embeddings"
    embeddings_dir.mkdir(parents=True, exist_ok=True)

    # use a sanitized version of the filename as the key
    key  = img_path.stem[:64]
    record = {
        "source":    img_path.name,
        "model":     version,
        "embedding": embedding,
    }
    out_path = embeddings_dir / f"{key}.json"
    out_path.write_text(json.dumps(record), encoding="utf-8")


def _build_embeddings_index(data_dir: Path) -> List[List[float]]:
    """
    Load all stored reference embeddings into a list.
    Called by compute_baseline_similarity() at scoring time.
    """
    embeddings_dir = data_dir / "baseline" / "embeddings"
    if not embeddings_dir.exists():
        return []

    embeddings = []
    for p in embeddings_dir.glob("*.json"):
        try:
            record = json.loads(p.read_text(encoding="utf-8"))
            emb    = record.get("embedding")
            if emb and len(emb) > 0:
                embeddings.append(emb)
        except Exception:
            continue

    return embeddings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scan_images(source_dir: Path) -> List[Path]:
    """
    Scan a directory for supported image files.
    Returns a sorted list of Paths.
    """
    images = [
        p for p in source_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(images)