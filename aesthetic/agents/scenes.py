# aesthetic/agents/scenes.py
#
# Scene detection agent.
# Reads a video file, steps through frames looking for content changes,
# and returns a list of Scene models with accurate in/out timecodes.
#
# Detection uses a multi-signal approach:
#   1. MAD (mean absolute difference) — fast pixel diff, catches hard cuts
#   2. Quadrant diff — splits frame into 4 regions, detects subject position
#      changes even when overall brightness is similar (reverse angles)
#   3. SSIM — structural similarity, detects layout changes in similar-looking frames
#   4. CLIP embedding distance — semantic change detection, most accurate,
#      optional (enabled via config features.clip_scene_detection)
#
# A cut is flagged when ANY signal exceeds its threshold.
# This combination catches hard cuts, reverse angles, coverage changes,
# and subtle transitions that MAD alone misses.
#
# Edge cases handled:
#   - Scenes shorter than min_scene_len_frames are merged with their neighbour
#   - Flash cuts (very short spikes) are ignored
#   - First and last frames are always scene boundaries
#   - Videos with no detected cuts produce one scene covering the full duration

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim_func

from ..models.job import VideoMeta, Scene


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def detect_scenes(
    video_meta:           VideoMeta,
    job_dir:              Path,
    threshold:            float = 22.0,
    min_scene_len_frames: int   = 12,
    downscale_width:      int   = 320,
    seed:                 int   = 42,
    config:               Optional[Dict] = None,
) -> List[Scene]:
    """
    Detect scene boundaries in the video described by video_meta.

    Args:
        video_meta:           Validated VideoMeta from the ingest agent.
        job_dir:              Path to the job directory — scenes.json written here.
        threshold:            Primary MAD threshold. Lower = more sensitive.
        min_scene_len_frames: Scenes shorter than this are merged.
        downscale_width:      Frame width for diff computation.
        seed:                 Stamped into output for determinism tracing.
        config:               Full config dict — used for feature flags.

    Returns:
        List of Scene models sorted by scene_id.
    """
    cfg      = config or {}
    features = cfg.get("features", {})
    use_clip = bool(features.get("clip_scene_detection", False))

    boundaries = _find_cut_boundaries(
        video_path=video_meta.path,
        fps=video_meta.fps,
        frame_count=video_meta.frame_count,
        threshold=threshold,
        downscale_width=downscale_width,
        use_clip=use_clip,
    )

    scenes = _boundaries_to_scenes(
        boundaries,
        video_meta.frame_count,
        video_meta.fps,
        min_scene_len_frames,
    )

    _write_scenes_json(scenes, job_dir)

    # --- Transition classification (optional, requires trained model) ---
    try:
        from pathlib import Path as _Path
        from ..config import DATA_DIR as _DATA_DIR
        _model_path = str(_DATA_DIR / "transition_model.pkl")
        if _Path(_model_path).exists() and len(scenes) > 1:
            from .transition_classifier import classify_boundaries_batch
            boundary_frames = [s.start_frame for s in scenes[1:]]  # skip first scene
            results = classify_boundaries_batch(
                video_meta.path, boundary_frames, video_meta.fps, _model_path
            )
            for scene, (t_type, t_conf) in zip(scenes[1:], results):
                scene.transition_type = t_type
                scene.transition_conf = round(t_conf, 3)
            _write_scenes_json(scenes, job_dir)  # re-write with transition types
            print(f"[scenes] transition types classified for {len(results)} boundaries")
    except Exception as _tc_exc:
        print(f"[scenes] transition classification skipped: {_tc_exc}")

    return scenes


# ---------------------------------------------------------------------------
# Sensitivity slider mapping
# ---------------------------------------------------------------------------

def sensitivity_to_threshold(sensitivity: int) -> float:
    """
    Map the UI sensitivity slider (1-100) to a MAD threshold.

    High sensitivity (100) -> low threshold (4.0)  -> more cuts detected.
    Low sensitivity  (1)   -> high threshold (45.0) -> fewer cuts detected.
    Default at sensitivity 50 = ~24.0.

    Quadrant and SSIM thresholds are derived from this value automatically.
    """
    sensitivity = max(1, min(100, sensitivity))
    return round(45.0 - (sensitivity - 1) * (41.0 / 99.0), 2)


# ---------------------------------------------------------------------------
# Core detection — multi-signal
# ---------------------------------------------------------------------------

def _open_video_capture(video_path: str) -> cv2.VideoCapture:
    """
    Open a video file for reading. Tries direct OpenCV first, then
    falls back to ffmpeg pipe for problematic codecs (MKV, HEVC, etc.)
    """
    cap = cv2.VideoCapture(video_path)
    if cap.isOpened():
        # Quick read test — some codecs open but stall on first read
        ok, _ = cap.read()
        if ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return cap
        cap.release()

    # Fallback: force ffmpeg backend
    cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
    if cap.isOpened():
        return cap

    raise RuntimeError(f"Could not open video (tried OpenCV + ffmpeg backend): {video_path}")


def _find_cut_boundaries(
    video_path:      str,
    fps:             float,
    frame_count:     int,
    threshold:       float,
    downscale_width: int,
    use_clip:        bool = False,
) -> List[int]:
    """
    Step through the video and return frame indices where cuts occur.
    Combines MAD + quadrant diff + SSIM. CLIP is optional.
    Uses ffmpeg backend for MKV/HEVC files that stall OpenCV's default decoder.
    """
    cap = _open_video_capture(video_path)

    # derive secondary thresholds from primary
    quadrant_threshold = threshold * 0.6   # tighter — localised changes
    ssim_threshold     = max(0.55, 0.85 - (threshold / 100.0))  # lower = more different

    boundaries: List[int] = [0]
    prev_gray:  Optional[np.ndarray] = None
    frame_idx:  int = 0

    # CLIP setup
    clip_model      = None
    clip_preprocess = None
    clip_device     = "cpu"
    prev_embedding: Optional[np.ndarray] = None
    clip_interval   = max(1, int(fps / 2))   # sample at ~2fps

    if use_clip:
        clip_model, clip_preprocess, clip_device = _load_clip_for_scenes()

    # Sample every N frames — cuts are never sub-frame events.
    # At 24fps step=2 → 12 comparisons/sec. At 60fps step=5 → 12 comparisons/sec.
    # Reduces detection time by 50-75% on long films with no accuracy loss.
    step = max(1, int(round(fps / 12)))

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if frame is None or frame_idx > frame_count + 100:
                frame_idx += 1
                continue

            # Skip to next sample position
            if frame_idx % step != 0:
                frame_idx += 1
                continue

            gray = _preprocess_frame(frame, downscale_width)

            if prev_gray is not None:
                cut_detected = False

                # signal 1 — MAD
                if _mean_absolute_diff(prev_gray, gray) > threshold:
                    cut_detected = True

                # signal 2 — quadrant diff (reverse angles, coverage changes)
                if not cut_detected:
                    if _quadrant_diff(prev_gray, gray) > quadrant_threshold:
                        cut_detected = True

                # signal 3 — SSIM (structural layout change)
                if not cut_detected:
                    if _ssim_diff(prev_gray, gray) < ssim_threshold:
                        cut_detected = True

                # signal 4 — CLIP semantic distance (optional)
                if not cut_detected and use_clip and clip_model is not None:
                    if frame_idx % clip_interval == 0:
                        emb = _clip_embedding_for_frame(
                            frame, clip_model, clip_preprocess, clip_device
                        )
                        if emb is not None and prev_embedding is not None:
                            cos_dist = 1.0 - float(np.dot(emb, prev_embedding))
                            if cos_dist > 0.15:
                                cut_detected = True
                        if emb is not None:
                            prev_embedding = emb

                if cut_detected:
                    # suppress duplicate boundaries on consecutive frames (flash cut)
                    if not boundaries or frame_idx - boundaries[-1] > 2:
                        boundaries.append(frame_idx)

            prev_gray = gray
            frame_idx += 1

    finally:
        cap.release()

    last_frame = frame_idx - 1
    if last_frame > 0 and boundaries[-1] != last_frame:
        boundaries.append(last_frame)

    return boundaries


# ---------------------------------------------------------------------------
# Signal implementations
# ---------------------------------------------------------------------------

def _preprocess_frame(frame: np.ndarray, downscale_width: int) -> np.ndarray:
    """Downscale and convert to greyscale."""
    h, w = frame.shape[:2]
    new_h = max(1, int(h * downscale_width / w))
    small = cv2.resize(frame, (downscale_width, new_h), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)


def _mean_absolute_diff(a: np.ndarray, b: np.ndarray) -> float:
    """Global mean absolute pixel difference."""
    return float(np.mean(np.abs(a.astype(np.int32) - b.astype(np.int32))))


def _quadrant_diff(a: np.ndarray, b: np.ndarray) -> float:
    """
    Split frames into 4 quadrants and return the MAXIMUM quadrant MAD.

    A reverse angle or coverage change will spike one or two quadrants
    (subject moves sides) while the overall MAD stays low.
    This is the key signal for catching similar-background cuts.
    """
    h, w = a.shape
    mh, mw = h // 2, w // 2

    quads_a = [a[:mh, :mw], a[:mh, mw:], a[mh:, :mw], a[mh:, mw:]]
    quads_b = [b[:mh, :mw], b[:mh, mw:], b[mh:, :mw], b[mh:, mw:]]

    diffs = [
        float(np.mean(np.abs(qa.astype(np.int32) - qb.astype(np.int32))))
        for qa, qb in zip(quads_a, quads_b)
    ]

    return float(max(diffs))


def _ssim_diff(a: np.ndarray, b: np.ndarray) -> float:
    """
    SSIM between two greyscale frames. Lower = more structurally different.
    Sensitive to compositional layout changes even in tonally similar frames.
    """
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return float(ssim_func(a, b, data_range=255))
    except Exception:
        return 1.0


def _load_clip_for_scenes() -> Tuple:
    """Load CLIP for scene detection. Returns (model, preprocess, device)."""
    try:
        from .model_utils import load_model, get_device
        device = get_device()
        model, preprocess, _, _ = load_model(device)
        return model, preprocess, device
    except Exception:
        return None, None, "cpu"


def _clip_embedding_for_frame(
    frame:      np.ndarray,
    model,
    preprocess,
    device:     str,
) -> Optional[np.ndarray]:
    """Generate a normalised CLIP embedding for a video frame."""
    try:
        import torch
        from PIL import Image
        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img    = Image.fromarray(rgb)
        tensor = preprocess(img).unsqueeze(0).to(device)
        with torch.no_grad():
            emb = model.encode_image(tensor)
            emb = emb / emb.norm(dim=-1, keepdim=True)
        return emb.squeeze().cpu().numpy()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Boundary → Scene conversion
# ---------------------------------------------------------------------------

def _boundaries_to_scenes(
    boundaries:           List[int],
    total_frames:         int,
    fps:                  float,
    min_scene_len_frames: int,
) -> List[Scene]:
    """Convert boundary indices into Scene models, merging short scenes."""
    if len(boundaries) < 2:
        return [_make_scene(1, 0, total_frames - 1, fps)]

    spans: List[Tuple[int, int]] = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end   = boundaries[i + 1] - 1
        spans.append((start, end))
    spans[-1] = (spans[-1][0], total_frames - 1)

    merged: List[Tuple[int, int]] = []
    i = 0
    while i < len(spans):
        start, end = spans[i]
        length = end - start + 1

        if length < min_scene_len_frames and i < len(spans) - 1:
            next_start, next_end = spans[i + 1]
            spans[i + 1] = (start, next_end)
            i += 1
            continue

        if length < min_scene_len_frames and merged:
            prev_start, _ = merged[-1]
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))

        i += 1

    if not merged:
        return [_make_scene(1, 0, total_frames - 1, fps)]

    return [
        _make_scene(scene_id, start, end, fps)
        for scene_id, (start, end) in enumerate(merged, start=1)
    ]


def _make_scene(scene_id: int, start_frame: int, end_frame: int, fps: float) -> Scene:
    return Scene(
        scene_id=scene_id,
        start_frame=start_frame,
        end_frame=end_frame,
        start_time=round(start_frame / fps, 6),
        end_time=round(end_frame / fps, 6),
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _write_scenes_json(scenes: List[Scene], job_dir: Path) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    out_path = job_dir / "scenes.json"
    data = [s.model_dump(mode="json") for s in scenes]
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")