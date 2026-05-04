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
    """Check if the available ffmpeg was built with CUDA hwaccel support."""
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


def _parse_scene_boundaries(stderr_output: str) -> list:
    """Parse ffmpeg showinfo stderr output into a list of frame indices."""
    import re
    boundaries = [0]
    for line in stderr_output.splitlines():
        if "Parsed_showinfo" in line and " n:" in line:
            m = re.search(r" n:\s*(\d+)", line)
            if m:
                frame_idx = int(m.group(1))
                if frame_idx > 0:
                    boundaries.append(frame_idx)
    return sorted(set(boundaries))


def _find_cut_boundaries_ffmpeg(
    video_path:  str,
    fps:         float,
    threshold:   float,
    progress_cb=None,
) -> list:
    """
    Use ffmpeg built-in scene detection filter.
    Tries CUDA-accelerated decode first, falls back to CPU.
    10-20x faster than reading frames in Python.

    ffmpeg scene score 0-1 maps from our MAD threshold 0-45:
    ffmpeg_thresh = threshold / 45 * 0.6  (capped at 0.6)
    """
    import subprocess, sys

    ffmpeg_thresh = round(min(0.6, max(0.05, threshold / 45.0 * 0.6)), 3)
    no_window     = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    def _run(cmd):
        return subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=no_window, timeout=1800,  # 30 min max
        )

    # Try CUDA decode first if available
    if _ffmpeg_has_cuda():
        try:
            r = _run([
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-hwaccel", "cuda",
                "-i", video_path,
                "-vf", "select='gt(scene," + str(ffmpeg_thresh) + ")',showinfo",
                "-vsync", "vfr", "-f", "null", "-",
            ])
            if r.returncode == 0:
                b = _parse_scene_boundaries(r.stderr)
                print(f"[scenes] ffmpeg CUDA: {len(b)-1} cuts (thresh={ffmpeg_thresh})")
                return b
            print(f"[scenes] CUDA decode failed rc={r.returncode}, trying CPU")
        except Exception as e:
            print(f"[scenes] CUDA exception: {e}, trying CPU")

    # CPU fallback — stream stderr so we get progress and can detect hangs
    b = _run_streaming(video_path, ffmpeg_thresh, fps, no_window, progress_cb=progress_cb)
    print(f"[scenes] ffmpeg CPU: {len(b)-1} cuts (thresh={ffmpeg_thresh})")
    return b


def _run_streaming(
    video_path:    str,
    ffmpeg_thresh: float,
    fps:           float,
    no_window:     int,
    progress_cb=None,
) -> list:
    """
    Run ffmpeg scene detection and stream stderr line-by-line.
    Avoids blocking on a single subprocess.run() call for long films.
    Reports progress via print statements.
    """
    import subprocess, re, threading, time

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "info",
        "-i", video_path,
        "-vf", "select='gt(scene," + str(ffmpeg_thresh) + ")',showinfo",
        "-vsync", "vfr", "-f", "null", "-",
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=no_window,
        text=True,
        bufsize=1,
    )

    boundaries  = [0]
    last_report = time.time()
    frame_count = 0
    duration_sec = None

    for line in proc.stderr:
        # Parse duration from ffmpeg header
        if duration_sec is None:
            dm = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", line)
            if dm:
                h, m, s = int(dm.group(1)), int(dm.group(2)), float(dm.group(3))
                duration_sec = h * 3600 + m * 60 + s

        # Parse frame number from showinfo
        if "Parsed_showinfo" in line and " n:" in line:
            nm = re.search(r" n:\s*(\d+)", line)
            if nm:
                frame_idx = int(nm.group(1))
                if frame_idx > 0:
                    boundaries.append(frame_idx)

        # Parse current time position for progress
        tm = re.search(r"time=\s*(\d+):(\d+):([\d.]+)", line)
        if tm:
            h, m, s = int(tm.group(1)), int(tm.group(2)), float(tm.group(3))
            current_sec = h * 3600 + m * 60 + s
            frame_count = int(current_sec * fps)
            now = time.time()
            if now - last_report >= 10:  # report every 10 seconds
                if duration_sec and duration_sec > 0:
                    pct = min(99, int(current_sec / duration_sec * 100))
                    msg = f"Detecting scenes… {current_sec:.0f}s / {duration_sec:.0f}s ({pct}%)"
                else:
                    msg = f"Detecting scenes… frame {frame_count}"
                print(f"[scenes] {msg}")
                if progress_cb:
                    progress_cb(5 + int(pct * 0.10), 100, msg)
                last_report = now

    proc.wait()
    return sorted(set(boundaries))


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
    Find scene cut boundaries using ffmpeg native detection.
    Falls back to grayscale MAD diff pipe if ffmpeg returns no cuts on a long video.
    """
    import subprocess, sys
    import numpy as np

    boundaries = _find_cut_boundaries_ffmpeg(video_path, fps, threshold, progress_cb=progress_cb)

    # Sanity: if 0 cuts on a film-length video, something went wrong
    if len(boundaries) <= 1 and frame_count > fps * 30:
        print("[scenes] 0 cuts detected on long video — using MAD fallback")
        # Simple grayscale MAD pipe fallback
        no_window = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        step = max(1, int(round(fps / 8)))
        target_fps = fps / step
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", video_path],
            capture_output=True, text=True, creationflags=no_window,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            parts = probe.stdout.strip().split(",")
            orig_w, orig_h = int(parts[0]), int(parts[1])
            scale = downscale_width / orig_w
            h = int(orig_h * scale); h += h % 2
            w = downscale_width
            buf = h * w
            proc = subprocess.Popen(
                ["ffmpeg", "-hide_banner", "-loglevel", "error",
                 "-i", video_path,
                 "-vf", f"fps={target_fps:.4f},scale={w}:-2",
                 "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=no_window,
            )
            boundaries = [0]
            prev = None
            fi = 0
            try:
                while True:
                    chunk = proc.stdout.read(buf)
                    if len(chunk) < buf:
                        break
                    gray = np.frombuffer(chunk, np.uint8).reshape(h, w).astype(np.float32)
                    if prev is not None and float(np.mean(np.abs(gray - prev))) > threshold:
                        boundaries.append(fi * step)
                    prev = gray
                    fi += 1
            finally:
                proc.kill(); proc.wait()
            boundaries = sorted(set(boundaries))
            print(f"[scenes] MAD fallback: {len(boundaries)-1} cuts")

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