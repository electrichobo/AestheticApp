"""
aesthetic/agents/hero_clip.py

Hero clip extraction — Phase 2.

For each selected shot, finds the best 2–6 second window within it using
already-computed per-frame metrics, then extracts a trimmed clip via ffmpeg
with configurable handles, respecting scene boundaries and transition types.

No model re-inference — uses metrics already computed during analysis.

Public API:
    find_best_window(frames, scene, config) → (start_sec, end_sec, score)
    extract_hero_clip(shot, scene, source_file, out_dir, config) → Path | None
    extract_hero_clips_batch(shots_with_scenes, source_file, out_dir, config) → dict
"""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np


# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

DEFAULT_MIN_DURATION  = 2.0    # minimum window duration (seconds)
DEFAULT_MAX_DURATION  = 6.0    # maximum window duration (seconds)
DEFAULT_HANDLE_SEC    = 4.0    # handle length added each side (seconds)
DEFAULT_STEP_SEC      = 0.25   # window slide step (seconds)


# ---------------------------------------------------------------------------
# Per-frame scoring
# ---------------------------------------------------------------------------

def score_frame(fm: "FrameMetrics") -> float:
    """
    Compute a single quality score for one frame using already-computed metrics.

    Combines technical quality (sharpness, exposure, noise) with composition
    and narrative signals. Weights tuned for portfolio/reel use:
    good exposure + sharp + saliency = hero moment candidate.

    Returns a score in 0–100.
    """
    parts: List[Tuple[float, float]] = []  # (value, weight)

    # --- Sharpness (high weight — blurry frame is never hero) ---
    if fm.quality.sharpness_laplacian is not None:
        parts.append((min(100.0, fm.quality.sharpness_laplacian / 400.0 * 100.0), 2.5))

    # --- Focus on subject ---
    if fm.focus.subject_focus_accuracy is not None:
        parts.append((fm.focus.subject_focus_accuracy, 2.0))

    # --- Eye sharpness (strong signal for portrait/dialogue shots) ---
    if fm.focus.eye_sharpness is not None:
        parts.append((fm.focus.eye_sharpness, 1.5))

    # --- Exposure quality ---
    if fm.exposure.exposure_intent is not None:
        parts.append((fm.exposure.exposure_intent, 1.5))
    if fm.exposure.highlight_clip_pct is not None:
        parts.append((max(0.0, 100.0 - fm.exposure.highlight_clip_pct * 20.0), 1.0))

    # --- Saliency / focal point strength ---
    if fm.narrative.saliency_consistency is not None:
        parts.append((fm.narrative.saliency_consistency, 1.5))

    # --- Compelling MOS (composite aesthetic) ---
    if fm.narrative.compelling_mos is not None:
        parts.append((fm.narrative.compelling_mos, 1.0))

    # --- Thumbnail potency (SigLIP zero-shot) ---
    if fm.subject.thumbnail_strength is not None:
        parts.append((fm.subject.thumbnail_strength, 1.5))
    if fm.subject.portfolio_potential is not None:
        parts.append((fm.subject.portfolio_potential, 1.5))

    # --- Emotion intensity (human moment) ---
    if fm.subject.facial_emotion_intensity is not None:
        parts.append((fm.subject.facial_emotion_intensity, 1.0))

    # --- Motion penalty: heavy blur or jerkiness hurts ---
    if fm.movement.jerkiness is not None:
        parts.append((max(0.0, 100.0 - fm.movement.jerkiness), 0.8))
    if fm.quality.over_sharpening is not None:
        parts.append((max(0.0, 100.0 - fm.quality.over_sharpening), 0.5))

    if not parts:
        return 50.0

    total_weight = sum(w for _, w in parts)
    score = sum(v * w for v, w in parts) / total_weight
    return round(float(np.clip(score, 0.0, 100.0)), 2)


# ---------------------------------------------------------------------------
# Best window finder
# ---------------------------------------------------------------------------

def find_best_window(
    frames:      List["FrameMetrics"],
    scene_start: float,
    scene_end:   float,
    min_dur:     float = DEFAULT_MIN_DURATION,
    max_dur:     float = DEFAULT_MAX_DURATION,
    step_sec:    float = DEFAULT_STEP_SEC,
) -> Tuple[float, float, float]:
    """
    Find the highest-scoring contiguous window within the shot's frame sequence.

    Uses a sliding window over the per-frame score series. Frames are sorted
    by timestamp and interpolated to a regular grid for consistent window sizing.

    Returns (window_start_sec, window_end_sec, window_score).
    If the scene is shorter than min_dur, returns the full scene bounds.
    """
    scene_dur = scene_end - scene_start

    # Short scene — return full extent
    if scene_dur <= min_dur:
        return scene_start, scene_end, 50.0

    # Sort frames by timestamp, compute per-frame scores
    sorted_frames = sorted(frames, key=lambda f: f.timestamp)
    if not sorted_frames:
        return scene_start, min(scene_start + max_dur, scene_end), 50.0

    times  = np.array([f.timestamp for f in sorted_frames])
    scores = np.array([score_frame(f) for f in sorted_frames])

    # Clamp times to scene bounds
    times  = np.clip(times, scene_start, scene_end)

    best_score = -1.0
    best_start = scene_start
    best_end   = min(scene_start + min(max_dur, scene_dur), scene_end)

    # Try all window durations from min_dur to max_dur in 0.5s increments
    for win_dur in np.arange(min_dur, min(max_dur, scene_dur) + 0.01, 0.5):
        # Slide window across the scene
        t = scene_start
        while t + win_dur <= scene_end + step_sec * 0.5:
            win_end   = min(t + win_dur, scene_end)
            win_start = max(t, scene_start)

            # Frames inside this window
            mask = (times >= win_start) & (times <= win_end)
            if mask.sum() == 0:
                t += step_sec
                continue

            win_score = float(scores[mask].mean())

            # Bonus for longer windows (more editorial options)
            length_bonus = (win_dur - min_dur) / max(max_dur - min_dur, 1.0) * 3.0
            win_score += length_bonus

            if win_score > best_score:
                best_score = win_score
                best_start = win_start
                best_end   = win_end

            t += step_sec

    best_score = max(0.0, best_score - 3.0)  # remove the length bonus from final score
    return round(best_start, 3), round(best_end, 3), round(best_score, 2)


# ---------------------------------------------------------------------------
# Clip extraction
# ---------------------------------------------------------------------------

def extract_hero_clip(
    shot_id:     str,
    rank:        int,
    total_score: float,
    source_file: str,
    frames:      List["FrameMetrics"],
    scene_start: float,
    scene_end:   float,
    out_dir:     Path,
    handle_sec:  float = DEFAULT_HANDLE_SEC,
    min_dur:     float = DEFAULT_MIN_DURATION,
    max_dur:     float = DEFAULT_MAX_DURATION,
    prev_scene_end:   Optional[float] = None,
    next_scene_start: Optional[float] = None,
    transition_type:  Optional[str]   = None,
) -> Optional[Path]:
    """
    Extract a hero clip for one shot.

    1. Find the best scoring window within the scene
    2. Add handle_sec handles each side
    3. Clamp handles to scene boundaries (hard cuts) or allow slight bleed
       on dissolves/fades (the transition IS part of the shot)
    4. Extract via ffmpeg stream copy

    Returns the output path, or None on failure.
    """
    if not shutil.which("ffmpeg"):
        print("[hero_clip] ffmpeg not on PATH — clip export skipped")
        return None

    if not Path(source_file).exists():
        print(f"[hero_clip] source file not found: {source_file}")
        return None

    # Find best window
    win_start, win_end, win_score = find_best_window(
        frames, scene_start, scene_end, min_dur, max_dur
    )

    # Determine handle boundaries
    # For hard cuts: stay strictly within scene bounds
    # For dissolves/fades/wipes: allow bleeding into the transition zone
    soft_transitions = {"dissolve", "fade_black", "fade_white", "wipe"}
    is_soft = transition_type in soft_transitions

    # Left handle: how far can we go before this scene?
    if is_soft and prev_scene_end is not None:
        # Blend slightly into the previous transition
        left_limit = max(prev_scene_end, scene_start - handle_sec * 0.5)
    else:
        left_limit = scene_start  # hard cut — stay in scene

    # Right handle: how far can we go after this scene?
    if is_soft and next_scene_start is not None:
        right_limit = min(next_scene_start, scene_end + handle_sec * 0.5)
    else:
        right_limit = scene_end   # hard cut — stay in scene

    clip_start = max(left_limit,  win_start - handle_sec)
    clip_end   = min(right_limit, win_end   + handle_sec)
    duration   = round(clip_end - clip_start, 3)

    if duration <= 0:
        print(f"[hero_clip] zero/negative duration for {shot_id} — skipping")
        return None

    out_name = f"{rank:02d}_{total_score:05.1f}_{shot_id}_win{win_score:.0f}.mp4"
    out_path = out_dir / out_name

    success = _ffmpeg_trim(source_file, clip_start, duration, out_path)

    if success:
        print(f"[hero_clip] {shot_id}: {clip_start:.2f}s–{clip_end:.2f}s "
              f"(window score {win_score:.1f}, {duration:.1f}s total)")
        return out_path
    else:
        print(f"[hero_clip] extraction failed for {shot_id}")
        return None


def extract_hero_clips_batch(
    shots_data:  List[Dict[str, Any]],   # list of shot dicts from bridge
    frames_map:  Dict[str, List["FrameMetrics"]],  # shot_id → frame metrics
    scenes_map:  Dict[int, "Scene"],      # scene_id → Scene
    source_file: str,
    out_dir:     Path,
    config:      Dict[str, Any],
) -> Dict[str, Optional[str]]:
    """
    Extract hero clips for all selected shots.

    shots_data: list of shot dicts as returned by the bridge (with rank, score, etc.)
    frames_map: maps shot_id to its list of FrameMetrics
    scenes_map: maps scene_id to Scene (for transition type and boundaries)
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    clip_cfg    = config.get("clip_export", {})
    handle_sec  = float(clip_cfg.get("handle_sec",  DEFAULT_HANDLE_SEC))
    min_dur     = float(clip_cfg.get("min_dur",     DEFAULT_MIN_DURATION))
    max_dur     = float(clip_cfg.get("max_dur",     DEFAULT_MAX_DURATION))

    # Build ordered scene list for prev/next lookup
    ordered_scenes = sorted(scenes_map.values(), key=lambda s: s.scene_id)
    scene_index    = {s.scene_id: i for i, s in enumerate(ordered_scenes)}

    results: Dict[str, Optional[str]] = {}

    for shot in shots_data:
        shot_id  = shot.get("shot_id", "unknown")
        scene_id = shot.get("scene_id")
        rank     = shot.get("rank", 0)
        score    = float(shot.get("total_score") or 0.0)

        frames = frames_map.get(shot_id, [])
        scene  = scenes_map.get(scene_id) if scene_id is not None else None

        if scene is None:
            # Fall back to shot times directly
            scene_start = float(shot.get("start_time", 0.0))
            scene_end   = float(shot.get("end_time", 0.0))
            prev_end    = None
            next_start  = None
            t_type      = None
        else:
            scene_start = scene.start_time
            scene_end   = scene.end_time
            t_type      = scene.transition_type

            # Adjacent scene boundaries
            idx = scene_index.get(scene.scene_id, -1)
            prev_end   = ordered_scenes[idx - 1].end_time   if idx > 0                        else None
            next_start = ordered_scenes[idx + 1].start_time if idx < len(ordered_scenes) - 1  else None

        out_path = extract_hero_clip(
            shot_id=shot_id,
            rank=rank,
            total_score=score,
            source_file=source_file,
            frames=frames,
            scene_start=scene_start,
            scene_end=scene_end,
            out_dir=out_dir,
            handle_sec=handle_sec,
            min_dur=min_dur,
            max_dur=max_dur,
            prev_scene_end=prev_end,
            next_scene_start=next_start,
            transition_type=t_type,
        )

        results[shot_id] = str(out_path) if out_path else None

    return results


# ---------------------------------------------------------------------------
# ffmpeg helpers
# ---------------------------------------------------------------------------

def _ffmpeg_trim(
    source_file: str,
    start_time:  float,
    duration:    float,
    out_path:    Path,
    timeout:     int = 120,
) -> bool:
    """
    Trim a clip using ffmpeg stream copy. Falls back to re-encode on failure.
    """
    cmd = [
        "ffmpeg",
        "-ss",  str(round(start_time, 3)),
        "-i",   source_file,
        "-t",   str(round(duration, 3)),
        "-c",   "copy",
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        "-y",
        str(out_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1024:
            return True
    except Exception:
        pass

    # Stream copy failed — try re-encode with H.264 at source quality
    if out_path.exists():
        out_path.unlink(missing_ok=True)

    cmd_encode = [
        "ffmpeg",
        "-ss",  str(round(start_time, 3)),
        "-i",   source_file,
        "-t",   str(round(duration, 3)),
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-y",
        str(out_path),
    ]
    try:
        r = subprocess.run(cmd_encode, capture_output=True, text=True, timeout=timeout * 2)
        return r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1024
    except Exception:
        return False