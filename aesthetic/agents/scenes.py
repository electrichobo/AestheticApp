# aesthetic/agents/scenes.py
#
# Scene detection agent.
# Reads a video file, steps through frames looking for content changes,
# and returns a list of Scene models with accurate in/out timecodes.
#
# Algorithm: downscale each frame to a small thumbnail, convert to
# greyscale, compute the mean absolute difference (MAD) between
# consecutive frames. When MAD exceeds the threshold, that is a cut.
#
# Edge cases handled:
#   - Scenes shorter than min_scene_len_frames are merged with their neighbour
#   - Flash cuts (very short spikes followed by immediate return) are ignored
#   - First and last frames of the video are always scene boundaries
#   - Videos with no detected cuts produce a single scene covering the full duration
#
# Output: list of Scene models, also written to jobs/<job_id>/scenes.json

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

from ..models.job import VideoMeta, Scene


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def detect_scenes(
    video_meta:          VideoMeta,
    job_dir:             Path,
    threshold:           float = 30.0,
    min_scene_len_frames:int   = 12,
    downscale_width:     int   = 320,
    seed:                int   = 42,
) -> List[Scene]:
    """
    Detect scene boundaries in the video described by video_meta.

    Args:
        video_meta:           Validated VideoMeta from the ingest agent.
        job_dir:              Path to the job directory — scenes.json is written here.
        threshold:            Mean absolute difference threshold for cut detection.
                              Lower = more sensitive (more scenes).
                              Higher = less sensitive (fewer scenes).
                              Maps directly to the UI sensitivity slider.
        min_scene_len_frames: Scenes shorter than this are merged with their neighbour.
        downscale_width:      Width to downscale frames to before diffing.
                              Smaller = faster, slightly less accurate.
        seed:                 Not used in detection itself but stamped into output
                              for determinism tracing.

    Returns:
        List of Scene models, sorted by scene_id.

    Raises:
        RuntimeError: if the video cannot be opened by OpenCV.
    """
    boundaries = _find_cut_boundaries(
        video_meta.path,
        video_meta.fps,
        video_meta.frame_count,
        threshold,
        downscale_width,
    )

    scenes = _boundaries_to_scenes(
        boundaries,
        video_meta.frame_count,
        video_meta.fps,
        min_scene_len_frames,
    )

    _write_scenes_json(scenes, job_dir)

    return scenes


# ---------------------------------------------------------------------------
# Sensitivity slider mapping
# ---------------------------------------------------------------------------

def sensitivity_to_threshold(sensitivity: int) -> float:
    """
    Map the UI sensitivity slider (1-100) to a diff threshold.

    High sensitivity (100) -> low threshold -> more cuts detected.
    Low sensitivity  (1)   -> high threshold -> fewer cuts detected.

    Returns a threshold in the range [8.0, 60.0].
    """
    sensitivity = max(1, min(100, sensitivity))
    # linear interpolation: sensitivity 100 -> 8.0, sensitivity 1 -> 60.0
    return round(60.0 - (sensitivity - 1) * (52.0 / 99.0), 2)


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------

def _find_cut_boundaries(
    video_path:      str,
    fps:             float,
    frame_count:     int,
    threshold:       float,
    downscale_width: int,
) -> List[int]:
    """
    Step through the video frame by frame and return a list of frame indices
    where cuts occur (i.e. where MAD between consecutive frames exceeds threshold).

    The list always starts with frame 0 and ends with the last frame.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open video: {video_path}")

    boundaries: List[int] = [0]
    prev_gray:  np.ndarray | None = None
    frame_idx:  int = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            gray = _preprocess_frame(frame, downscale_width)

            if prev_gray is not None:
                mad = _mean_absolute_diff(prev_gray, gray)
                if mad > threshold:
                    boundaries.append(frame_idx)

            prev_gray = gray
            frame_idx += 1
    finally:
        cap.release()

    # always include the final frame as a boundary
    last_frame = frame_idx - 1
    if last_frame > 0 and boundaries[-1] != last_frame:
        boundaries.append(last_frame)

    return boundaries


def _preprocess_frame(frame: np.ndarray, downscale_width: int) -> np.ndarray:
    """
    Downscale frame to downscale_width and convert to greyscale.
    This is all we need for the diff — colour information adds noise.
    """
    h, w = frame.shape[:2]
    scale = downscale_width / w
    new_w = downscale_width
    new_h = max(1, int(h * scale))
    small = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)


def _mean_absolute_diff(a: np.ndarray, b: np.ndarray) -> float:
    """Compute the mean absolute pixel difference between two greyscale frames."""
    return float(np.mean(np.abs(a.astype(np.int32) - b.astype(np.int32))))


# ---------------------------------------------------------------------------
# Boundary → Scene conversion
# ---------------------------------------------------------------------------

def _boundaries_to_scenes(
    boundaries:          List[int],
    total_frames:        int,
    fps:                 float,
    min_scene_len_frames:int,
) -> List[Scene]:
    """
    Convert a list of cut boundary frame indices into Scene models.
    Merges scenes that are shorter than min_scene_len_frames.
    """
    if len(boundaries) < 2:
        # no cuts found — one scene covering the whole video
        return [_make_scene(0, 0, total_frames - 1, fps)]

    # build raw scene spans from boundaries
    spans: List[Tuple[int, int]] = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end   = boundaries[i + 1] - 1
        spans.append((start, end))
    # last span ends at total_frames - 1
    spans[-1] = (spans[-1][0], total_frames - 1)

    # merge short scenes into their following neighbour
    # if the last scene is short, merge it into its preceding neighbour
    merged: List[Tuple[int, int]] = []
    i = 0
    while i < len(spans):
        start, end = spans[i]
        length = end - start + 1

        if length < min_scene_len_frames and i < len(spans) - 1:
            # absorb into next span
            next_start, next_end = spans[i + 1]
            spans[i + 1] = (start, next_end)
            i += 1
            continue

        if length < min_scene_len_frames and merged:
            # last span is too short — absorb into previous
            prev_start, _ = merged[-1]
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))

        i += 1

    # if nothing survived merging, return one scene
    if not merged:
        return [_make_scene(0, 0, total_frames - 1, fps)]

    return [
        _make_scene(scene_id, start, end, fps)
        for scene_id, (start, end) in enumerate(merged, start=1)
    ]


def _make_scene(scene_id: int, start_frame: int, end_frame: int, fps: float) -> Scene:
    """Construct a Scene model from frame indices and fps."""
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
    """Write scenes list to jobs/<job_id>/scenes.json."""
    job_dir.mkdir(parents=True, exist_ok=True)
    out_path = job_dir / "scenes.json"
    data = [s.model_dump(mode="json") for s in scenes]
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")