"""
aesthetic/agents/transition_classifier.py

Transition type classifier — trained on labelled video clips, infers the
type of cut at each detected scene boundary during analysis.

Classes:  hard_cut | dissolve | fade_black | fade_white | wipe

Architecture:
  Feature extraction → LightGBM classifier
  ~30 temporal features computed from a 16-frame window around each boundary.
  CPU-only inference. No GPU required. Model stored as a single .pkl file.

Training:
  Run from the Baseline tab, or directly:
    python -m aesthetic.agents.transition_classifier \
        --data E:\\transitiontrainer \
        --output E:\\AestheticApp\\aesthetic\\data\\transition_model.pkl

Inference:
  Called automatically during scene detection when a trained model is present.
  Annotates Scene.transition_type and Scene.transition_conf.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLASSES         = ["hard_cut", "dissolve", "fade_black", "fade_white", "wipe"]
N_FRAMES        = 16      # frames to sample around each transition midpoint
FEATURE_VERSION = 1       # bump when feature schema changes
MODEL_FILENAME  = "transition_model.pkl"


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def extract_features_from_clip(video_path: str, n_frames: int = N_FRAMES) -> Optional[np.ndarray]:
    """
    Extract temporal features from a transition clip.

    Samples n_frames evenly across the clip, computes per-frame and
    inter-frame signals, then reduces to a fixed-length feature vector.

    Returns None if the clip cannot be read.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < 4:
        cap.release()
        return None

    # Sample frame indices evenly across the clip
    indices = np.linspace(0, total - 1, n_frames, dtype=int)
    frames  = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if ok and frame is not None:
            frames.append(cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA))
    cap.release()

    if len(frames) < 4:
        return None

    frames = np.array(frames, dtype=np.float32)  # (N, H, W, 3)

    # --- Per-frame signals ---
    gray   = frames.mean(axis=3)                    # (N, H, W) luma
    luma   = gray.mean(axis=(1, 2))                 # (N,) mean luminance
    bright = (gray > 240).mean(axis=(1, 2))         # (N,) highlight fraction
    dark   = (gray < 16).mean(axis=(1, 2))          # (N,) shadow fraction

    # --- Inter-frame difference signals ---
    diffs     = []
    flow_mags = []
    hist_diffs= []

    for i in range(len(frames) - 1):
        f0 = frames[i].astype(np.uint8)
        f1 = frames[i + 1].astype(np.uint8)
        g0 = cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY)
        g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)

        # Frame difference (MAD)
        diffs.append(float(np.mean(np.abs(g0.astype(float) - g1.astype(float)))))

        # Optical flow magnitude
        try:
            flow = cv2.calcOpticalFlowFarneback(
                g0, g1, None,
                pyr_scale=0.5, levels=2, winsize=9,
                iterations=2, poly_n=5, poly_sigma=1.1, flags=0
            )
            flow_mags.append(float(np.mean(np.sqrt(flow[..., 0]**2 + flow[..., 1]**2))))
        except Exception:
            flow_mags.append(0.0)

        # Colour histogram L1 distance
        h0 = cv2.calcHist([f0], [0, 1, 2], None, [8, 8, 8], [0,256,0,256,0,256])
        h1 = cv2.calcHist([f1], [0, 1, 2], None, [8, 8, 8], [0,256,0,256,0,256])
        h0 = h0.flatten() / (h0.sum() + 1e-8)
        h1 = h1.flatten() / (h1.sum() + 1e-8)
        hist_diffs.append(float(np.sum(np.abs(h0 - h1))))

    diffs      = np.array(diffs,      dtype=np.float32)
    flow_mags  = np.array(flow_mags,  dtype=np.float32)
    hist_diffs = np.array(hist_diffs, dtype=np.float32)

    # --- Feature assembly ---
    def curve_stats(arr: np.ndarray) -> List[float]:
        """mean, std, min, max, argmax_norm, is_monotonic, peak_ratio, slope"""
        if len(arr) == 0:
            return [0.0] * 8
        n = len(arr)
        mn, mx, sd = float(arr.mean()), float(arr.max()), float(arr.std())
        argmx = float(np.argmax(arr)) / max(n - 1, 1)
        mono  = float(all(arr[i] <= arr[i+1] for i in range(n-1)) or
                      all(arr[i] >= arr[i+1] for i in range(n-1)))
        peak  = float((mx - mn) / (sd + 1e-8))
        slope = float(np.polyfit(np.arange(n), arr, 1)[0]) if n > 1 else 0.0
        return [mn, sd, float(arr.min()), mx, argmx, mono, peak, slope]

    # Luma curve (key for fade detection — monotonic ramp)
    f_luma     = curve_stats(luma)
    # Bright/dark fraction curves (fade_white: bright rises; fade_black: dark rises)
    f_bright   = curve_stats(bright)
    f_dark     = curve_stats(dark)
    # Difference curve (hard_cut: single spike; dissolve: broad plateau)
    f_diffs    = curve_stats(diffs)
    # Flow curve (wipe: directional motion; hard_cut: zero then high)
    f_flow     = curve_stats(flow_mags)
    # Histogram distance curve
    f_hist     = curve_stats(hist_diffs)

    # Transition shape: is the peak at the start, middle, or end?
    mid_idx = len(diffs) // 2
    peak_pos = np.argmax(diffs) if len(diffs) > 0 else 0
    peak_early  = float(peak_pos < mid_idx * 0.4)
    peak_mid    = float(0.4 <= peak_pos / max(len(diffs)-1, 1) <= 0.6)
    peak_late   = float(peak_pos > mid_idx * 1.6)

    # Asymmetry: is the transition symmetric? (dissolve=yes, wipe=partial, fade=no)
    if len(diffs) >= 4:
        half = len(diffs) // 2
        asymmetry = float(np.mean(np.abs(diffs[:half] - diffs[half:half*2][::-1])))
    else:
        asymmetry = 0.0

    # Luma monotonicity confidence: strong ramp = fade
    luma_range  = float(luma.max() - luma.min())
    luma_mono   = float(np.corrcoef(np.arange(len(luma)), luma)[0, 1]
                        if len(luma) > 2 else 0.0)
    luma_mono   = 0.0 if np.isnan(luma_mono) else luma_mono

    # Single-frame spike vs gradual: kurtosis of diff curve
    diff_kurt   = float(_safe_kurtosis(diffs))
    flow_kurt   = float(_safe_kurtosis(flow_mags))

    extra = [peak_early, peak_mid, peak_late, asymmetry,
             luma_range, luma_mono, diff_kurt, flow_kurt,
             float(len(frames))]

    features = (f_luma + f_bright + f_dark +
                f_diffs + f_flow + f_hist + extra)

    return np.array(features, dtype=np.float32)


def _safe_kurtosis(arr: np.ndarray) -> float:
    if len(arr) < 4:
        return 0.0
    mu  = arr.mean()
    std = arr.std()
    if std < 1e-8:
        return 0.0
    return float(np.mean(((arr - mu) / std) ** 4)) - 3.0


# ---------------------------------------------------------------------------
# Training pipeline
# ---------------------------------------------------------------------------

def build_training_data(
    data_dir: str,
    n_frames:  int = N_FRAMES,
    verbose:   bool = True,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Walk the transitiontrainer directory structure and extract features.

    Expected layout:
        data_dir/
          <class_name>/
            videos/          ← clip files (.mp4, .mov, .avi, .mkv)
            labels/          ← optional per-clip JSON annotations
            sources/         ← original source (ignored during training)
          manifest.json      ← optional metadata

    Returns: X (n_samples, n_features), y (n_samples,), label_names
    """
    root     = Path(data_dir)
    X_rows: List[np.ndarray] = []
    y_rows: List[int]        = []
    label_map = {cls: i for i, cls in enumerate(CLASSES)}

    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".mxf", ".webm"}

    for cls_name in CLASSES:
        cls_dir    = root / cls_name / "videos"
        if not cls_dir.exists():
            if verbose:
                print(f"[transition] skipping {cls_name} — no videos dir")
            continue

        clips = [p for p in cls_dir.iterdir() if p.suffix.lower() in video_exts]
        if verbose:
            print(f"[transition] {cls_name}: {len(clips)} clips")

        for clip_path in clips:
            feats = extract_features_from_clip(str(clip_path), n_frames=n_frames)
            if feats is None:
                continue
            X_rows.append(feats)
            y_rows.append(label_map[cls_name])

    if not X_rows:
        raise ValueError(f"No usable clips found in {data_dir}")

    X = np.vstack(X_rows)
    y = np.array(y_rows, dtype=np.int32)

    if verbose:
        for i, cls in enumerate(CLASSES):
            n = int((y == i).sum())
            print(f"  {cls}: {n} samples")
        print(f"  Total: {len(y)} samples, {X.shape[1]} features")

    return X, y, CLASSES


def train(
    data_dir:   str,
    output_dir: Optional[str] = None,
    n_frames:   int = N_FRAMES,
    verbose:    bool = True,
) -> Path:
    """
    Train the transition classifier and save the model.

    Returns path to saved model file.
    """
    try:
        import lightgbm as lgb
        from sklearn.model_selection import StratifiedKFold, cross_val_score
        from sklearn.preprocessing import LabelEncoder
    except ImportError as e:
        raise ImportError(
            f"Training requires lightgbm and scikit-learn: pip install lightgbm scikit-learn\n{e}"
        )

    if verbose:
        print("[transition] Extracting features from training clips…")

    X, y, label_names = build_training_data(data_dir, n_frames=n_frames, verbose=verbose)

    # Cross-validation to report accuracy before saving
    clf_cv = lgb.LGBMClassifier(
        n_estimators=200,
        num_leaves=31,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        class_weight="balanced",
        random_state=42,
        verbose=-1,
    )
    skf    = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(clf_cv, X, y, cv=skf, scoring="accuracy")
    if verbose:
        print(f"[transition] 5-fold CV accuracy: {scores.mean():.3f} ± {scores.std():.3f}")

    # Train final model on all data
    clf = lgb.LGBMClassifier(
        n_estimators=300,
        num_leaves=31,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        class_weight="balanced",
        random_state=42,
        verbose=-1,
    )
    clf.fit(X, y)

    # Save
    if output_dir is None:
        output_dir = Path(__file__).resolve().parent.parent / "data"
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / MODEL_FILENAME

    payload = {
        "model":           clf,
        "classes":         label_names,
        "n_frames":        n_frames,
        "feature_version": FEATURE_VERSION,
        "cv_accuracy":     float(scores.mean()),
        "n_samples":       len(y),
    }
    with open(model_path, "wb") as f:
        pickle.dump(payload, f, protocol=4)

    if verbose:
        print(f"[transition] Model saved → {model_path}")
        print(f"[transition] CV accuracy: {scores.mean()*100:.1f}%")

    return model_path


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

_MODEL_CACHE: dict = {}  # path → payload


def load_model(model_path: str) -> Optional[dict]:
    """Load and cache the trained model payload."""
    global _MODEL_CACHE
    if model_path in _MODEL_CACHE:
        return _MODEL_CACHE[model_path]
    p = Path(model_path)
    if not p.exists():
        return None
    try:
        with open(p, "rb") as f:
            payload = pickle.load(f)
        _MODEL_CACHE[model_path] = payload
        print(f"[transition] model loaded ({payload.get('cv_accuracy',0)*100:.1f}% CV acc, "
              f"{payload.get('n_samples',0)} training samples)")
        return payload
    except Exception as e:
        print(f"[transition] model load failed: {e}")
        return None


def classify_boundary(
    video_path:  str,
    boundary_frame: int,
    fps:         float,
    model_path:  str,
    window_sec:  float = 1.0,
) -> Tuple[str, float]:
    """
    Classify the transition type at a scene boundary.

    Extracts a window of frames centred on the boundary frame,
    runs feature extraction, returns (class_name, confidence).

    Falls back to 'hard_cut' with confidence 0.0 on any error.
    """
    payload = load_model(model_path)
    if payload is None:
        return "hard_cut", 0.0

    clf       = payload["model"]
    classes   = payload["classes"]
    n_frames  = payload.get("n_frames", N_FRAMES)

    # Extract window around boundary
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return "hard_cut", 0.0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    half_window  = int(window_sec * fps / 2)
    start_f      = max(0, boundary_frame - half_window)
    end_f        = min(total_frames - 1, boundary_frame + half_window)

    if end_f - start_f < 4:
        cap.release()
        return "hard_cut", 0.0

    indices = np.linspace(start_f, end_f, n_frames, dtype=int)
    frames  = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if ok and frame is not None:
            frames.append(cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA))
    cap.release()

    if len(frames) < 4:
        return "hard_cut", 0.0

    # Build a temporary clip-like array and extract features
    # We write to a temp file to reuse extract_features_from_clip
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".avi", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        h, w = frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        writer = cv2.VideoWriter(tmp_path, fourcc, fps, (w, h))
        for fr in frames:
            writer.write(fr)
        writer.release()

        feats = extract_features_from_clip(tmp_path, n_frames=n_frames)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if feats is None:
        return "hard_cut", 0.0

    try:
        proba  = clf.predict_proba(feats.reshape(1, -1))[0]
        best   = int(np.argmax(proba))
        conf   = float(proba[best])
        label  = classes[best] if best < len(classes) else "hard_cut"
        return label, conf
    except Exception as e:
        print(f"[transition] inference error: {e}")
        return "hard_cut", 0.0


def classify_boundaries_batch(
    video_path:      str,
    boundary_frames: List[int],
    fps:             float,
    model_path:      str,
    window_sec:      float = 1.0,
) -> List[Tuple[str, float]]:
    """
    Classify multiple boundaries in one video. More efficient than calling
    classify_boundary() in a loop — shares the cap and model load.
    """
    results = []
    payload = load_model(model_path)
    if payload is None:
        return [("hard_cut", 0.0)] * len(boundary_frames)

    clf      = payload["model"]
    classes  = payload["classes"]
    n_frames = payload.get("n_frames", N_FRAMES)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return [("hard_cut", 0.0)] * len(boundary_frames)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    import tempfile, os
    for bf in boundary_frames:
        half_window = int(window_sec * fps / 2)
        start_f     = max(0, bf - half_window)
        end_f       = min(total_frames - 1, bf + half_window)

        if end_f - start_f < 4:
            results.append(("hard_cut", 0.0))
            continue

        indices = np.linspace(start_f, end_f, n_frames, dtype=int)
        frames  = []
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if ok and frame is not None:
                frames.append(cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA))

        if len(frames) < 4:
            results.append(("hard_cut", 0.0))
            continue

        with tempfile.NamedTemporaryFile(suffix=".avi", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            h, w   = frames[0].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            writer = cv2.VideoWriter(tmp_path, fourcc, fps, (w, h))
            for fr in frames:
                writer.write(fr)
            writer.release()
            feats = extract_features_from_clip(tmp_path, n_frames=n_frames)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        if feats is None:
            results.append(("hard_cut", 0.0))
            continue

        try:
            proba  = clf.predict_proba(feats.reshape(1, -1))[0]
            best   = int(np.argmax(proba))
            conf   = float(proba[best])
            label  = classes[best] if best < len(classes) else "hard_cut"
            results.append((label, conf))
        except Exception:
            results.append(("hard_cut", 0.0))

    cap.release()
    return results


# ---------------------------------------------------------------------------
# CLI entry point for training
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Train AESTHETIC transition classifier")
    parser.add_argument("--data",    required=True, help="Path to transitiontrainer directory")
    parser.add_argument("--output",  default=None,  help="Output directory for model file")
    parser.add_argument("--frames",  type=int, default=N_FRAMES, help="Frames to sample per clip")
    args = parser.parse_args()

    model_path = train(
        data_dir=args.data,
        output_dir=args.output,
        n_frames=args.frames,
        verbose=True,
    )
    print(f"\nDone. Model at: {model_path}")
    print(f"Usage: python -m aesthetic.agents.transition_classifier "
          f"--data {args.data} --output {args.output or 'aesthetic/data'}")