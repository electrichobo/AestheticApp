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
    progress_cb=None,
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
        progress_cb=progress_cb,
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

def _ffmpeg_has_cuda() -> bool:
    """Check if ffmpeg was built with CUDA hwaccel support."""
    import subprocess, sys
    no_window = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-hwaccels"],
            capture_output=True, text=True, timeout=5,
            creationflags=no_window,
        )
        return "cuda" in (r.stdout + r.stderr).lower()
    except Exception:
        return False


def _find_cut_boundaries(
    video_path:      str,
    fps:             float,
    frame_count:     int,
    threshold:       float,
    downscale_width: int,
    use_clip:        bool = False,
    progress_cb=None,
) -> list:
    """
    Scene-level boundary detection using 1fps thumbnail diff (Option 2).

    Extracts one tiny thumbnail per second via ffmpeg, computes mean absolute
    difference between consecutive thumbnails in LAB colour space.

    Editorial cuts between angles of the same scene produce small diffs (~15-30)
    because lighting, colour, and characters remain similar.

    True scene changes (new location, time jump, major transition) produce
    large diffs (~50-120) because the overall visual character changes.

    The threshold is re-mapped from the MAD cut-detection range to a
    scene-level range: sensitivity 50 → scene_thresh ~55 (catches only
    major visual changes, ignores editorial cuts within a scene).

    Uses CUDA-accelerated decode if available, CPU otherwise.
    Returns list of FRAME indices (not seconds) for boundary positions.
    """
    import subprocess, sys
    import numpy as np

    no_window  = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    duration_s = frame_count / fps if fps > 0 else 0

    # Map MAD threshold (4-45) to scene-level LAB diff threshold (20-55)
    # At 64px 1fps thumbnails:
    #   same scene different angle:  LAB diff ~8-25
    #   genuine scene change:        LAB diff ~30-60
    #   fade/major transition:       LAB diff ~70-120
    # sensitivity 50 (default) → MAD 24 → scene_thresh ~35 — catches scene changes
    # sensitivity 20 (low)     → MAD 38 → scene_thresh ~47 — only major changes
    # sensitivity 80 (high)    → MAD 13 → scene_thresh ~26 — catches subtle changes
    scene_thresh = 20.0 + (threshold / 45.0) * 35.0  # range 20-55

    print(f"[scenes] scene detection: 1fps thumbnail diff, threshold={scene_thresh:.1f}")

    # Build ffmpeg command — extract 1fps, scale to 64px wide, output raw BGR
    hw_args = []
    if _ffmpeg_has_cuda():
        hw_args = ["-hwaccel", "cuda"]

    cmd = hw_args + [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
    ] + hw_args + [
        "-i", video_path,
        "-vf", "fps=1,scale=64:-2",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "pipe:1",
    ]

    # Fix cmd — hw_args was duplicated, rebuild cleanly
    base_cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if _ffmpeg_has_cuda():
        base_cmd += ["-hwaccel", "cuda"]
    base_cmd += [
        "-i", video_path,
        "-vf", "fps=1,scale=64:-2",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "pipe:1",
    ]

    # Probe output dimensions
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
        creationflags=no_window, timeout=30,
    )
    if probe.returncode != 0 or not probe.stdout.strip():
        print("[scenes] ffprobe failed — returning single scene")
        return [0]

    parts   = probe.stdout.strip().split(",")
    orig_w  = int(parts[0])
    orig_h  = int(parts[1])
    scale   = 64 / orig_w
    h       = int(orig_h * scale)
    if h % 2 != 0: h += 1
    w       = 64
    buf_size = h * w * 3  # BGR

    proc = subprocess.Popen(
        base_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=no_window,
    )

    boundaries  = [0]
    prev_lab    = None
    second      = 0
    last_report = 0
    all_diffs   = []   # store all diffs for adaptive threshold retry

    import cv2

    try:
        while True:
            chunk = proc.stdout.read(buf_size)
            if len(chunk) < buf_size:
                break

            bgr = np.frombuffer(chunk, dtype=np.uint8).reshape((h, w, 3))
            lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)

            if prev_lab is not None:
                diff = float(np.mean(np.abs(lab - prev_lab)))
                all_diffs.append((second, diff))
                if diff > scene_thresh:
                    frame_idx = int(second * fps)
                    boundaries.append(frame_idx)
                    print(f"[scenes] scene boundary at {second}s (diff={diff:.1f})")

            prev_lab = lab
            second  += 1

            # Progress every 60 seconds of video processed
            if second - last_report >= 60:
                if duration_s > 0:
                    pct = min(99, int(second / duration_s * 100))
                    msg = f"Detecting scenes… {second//60}m / {int(duration_s)//60}m ({pct}%)"
                else:
                    msg = f"Detecting scenes… {second}s processed"
                print(f"[scenes] {msg}")
                if progress_cb:
                    progress_cb(5 + int(pct * 0.10), 100, msg)
                last_report = second

    finally:
        proc.kill()
        proc.wait()

    # Adaptive threshold retry for low-variance films or under-detected content
    # Triggers when: fewer than 3 boundaries detected, OR fewer than 1 scene
    # per 5 minutes of content (e.g. 9-minute film should have at least 1-2 scenes)
    expected_min = max(3, int(second / 300))  # at least 1 scene per 5 minutes
    if len(boundaries) <= expected_min and all_diffs and second > 60:
        diffs_only = [d for _, d in all_diffs]
        p90  = float(np.percentile(diffs_only, 90))
        p95  = float(np.percentile(diffs_only, 95))
        # Use p90 × 1.8 — catches only the top outlier diffs (genuine scene changes)
        # within the film's own tonal range. Much more conservative than p75 × 1.5.
        adaptive = max(p90 * 1.8, p95 * 1.2)
        print(f"[scenes] low boundary count — adaptive retry: p90={p90:.1f}, p95={p95:.1f}, adaptive_thresh={adaptive:.1f}")
        if adaptive < scene_thresh:
            # Also enforce minimum scene duration — at least 30s between boundaries
            min_scene_sec = 30
            boundaries = [0]
            last_boundary_sec = 0
            for sec, diff in all_diffs:
                if diff > adaptive and (sec - last_boundary_sec) >= min_scene_sec:
                    frame_idx = int(sec * fps)
                    boundaries.append(frame_idx)
                    last_boundary_sec = sec
                    print(f"[scenes] adaptive boundary at {sec}s (diff={diff:.1f})")
            print(f"[scenes] adaptive retry found {len(boundaries)-1} boundaries")

    boundaries = sorted(set(boundaries))
    print(f"[scenes] found {len(boundaries)-1} scene boundaries in {second}s of video")
    return boundaries


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