# tests/conftest.py
#
# Shared pytest fixtures available to all test modules.
# Generates synthetic test data so tests run without real video files.

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import cv2
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Synthetic frame fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_frame_gray():
    """A simple 320x180 greyscale frame with known properties."""
    frame = np.zeros((180, 320), dtype=np.uint8)
    # centre region at 128 luminance — well-exposed, no clipping
    frame[40:140, 80:240] = 128
    # corners at 40 — some shadow detail
    frame[:40, :80] = 40
    return frame


@pytest.fixture
def synthetic_frame_bgr(synthetic_frame_gray):
    """BGR colour version of the synthetic frame."""
    return cv2.cvtColor(synthetic_frame_gray, cv2.COLOR_GRAY2BGR)


@pytest.fixture
def clipped_frame_bgr():
    """A frame with severe highlight and shadow clipping."""
    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    frame[:90, :] = 255   # top half blown out
    frame[90:, :] = 0     # bottom half crushed
    return frame


@pytest.fixture
def flat_frame_bgr():
    """A near-uniform grey frame — simulates title card or flat image."""
    return np.full((180, 320, 3), 200, dtype=np.uint8)


@pytest.fixture
def synthetic_frame_file(synthetic_frame_bgr, tmp_path):
    """Write synthetic frame to disk and return path string."""
    path = tmp_path / "test_frame.jpg"
    cv2.imwrite(str(path), synthetic_frame_bgr)
    return str(path)


@pytest.fixture
def clipped_frame_file(clipped_frame_bgr, tmp_path):
    """Write clipped frame to disk and return path string."""
    path = tmp_path / "clipped_frame.jpg"
    cv2.imwrite(str(path), clipped_frame_bgr)
    return str(path)


@pytest.fixture
def flat_frame_file(flat_frame_bgr, tmp_path):
    """Write flat frame to disk and return path string."""
    path = tmp_path / "flat_frame.jpg"
    cv2.imwrite(str(path), flat_frame_bgr)
    return str(path)


# ---------------------------------------------------------------------------
# Config fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def base_config() -> Dict[str, Any]:
    """Minimal config dict for pipeline tests."""
    return {
        "runtime":  {"seed": 42, "cpu_guard_pct": 85},
        "extract":  {"per_scene_candidates": 3, "per_scene_keep_pct": 0.5},
        "scenes":   {"threshold": 22.0, "min_scene_len_frames": 12, "downscale_width": 320},
        "weights":  {"technical": 0.50, "creative": 0.30, "subjective": 0.20},
        "selection":{"top_k": 5, "min_shot_duration_sec": 1.0, "soft_min_duration_sec": 0.5,
                     "enforce_narrative_diversity": False},
        "scoring":  {"alignment_threshold": 72.0, "alignment_bonus_cap": 12.0,
                     "technical_floor": 25.0, "technical_floor_cap": 72.0},
        "features": {"clip_enabled": False, "midas_enabled": False,
                     "yolo_enabled": False, "gpu_enabled": False,
                     "vlm_rationale_enabled": False},
        "category_weights": {
            "exposure": 0.18, "lighting": 0.18, "composition": 0.18,
            "movement": 0.14, "color": 0.14, "quality": 0.10, "narrative": 0.08,
        },
    }


# ---------------------------------------------------------------------------
# Synthetic video fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_video(tmp_path) -> str:
    """
    Create a minimal synthetic MP4 video with 3 distinct scenes.
    Uses OpenCV VideoWriter — no ffmpeg required for creation.
    Returns path to the video file.
    """
    path    = tmp_path / "test_video.mp4"
    fps     = 24.0
    w, h    = 320, 180
    fourcc  = cv2.VideoWriter_fourcc(*"mp4v")
    writer  = cv2.VideoWriter(str(path), fourcc, fps, (w, h))

    # scene 1: bright frame (60 frames = 2.5s)
    for _ in range(60):
        frame = np.full((h, w, 3), 180, dtype=np.uint8)
        writer.write(frame)

    # hard cut to dark frame — scene 2 (48 frames = 2s)
    for _ in range(48):
        frame = np.full((h, w, 3), 30, dtype=np.uint8)
        writer.write(frame)

    # hard cut to mid-grey — scene 3 (60 frames = 2.5s)
    for _ in range(60):
        frame = np.full((h, w, 3), 128, dtype=np.uint8)
        writer.write(frame)

    writer.release()
    return str(path)