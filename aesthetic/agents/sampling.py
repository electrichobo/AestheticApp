# aesthetic/agents/sampling.py
#
# Candidate sampling agent.
# For each detected scene, samples N candidate frames distributed across
# the shot duration with seeded jitter. Extracts those frames to disk
# via ffmpeg and writes candidates.json to the job directory.
#
# Design decisions:
#   - Jitter is seeded so results are deterministic across runs
#   - Frames already on disk are reused (cache hit) — ffmpeg is not re-run
#   - Sampling positions are distributed evenly then jittered within each
#     interval, so coverage of the shot is consistent regardless of N
#   - Frames are named with zero-padded scene and frame indices so they
#     sort correctly in Finder/Explorer

from __future__ import annotations

import json
import random
import subprocess
import shutil
from pathlib import Path
from typing import List

from ..models.job import VideoMeta, Scene, CandidateFrame


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def sample_candidates(
    video_meta:           VideoMeta,
    scenes:               List[Scene],
    job_dir:              Path,
    per_scene_candidates: int = 9,
    seed:                 int = 42,
) -> List[CandidateFrame]:
    """
    Sample candidate frames from each scene and extract them to disk.

    Args:
        video_meta:           Validated VideoMeta from the ingest agent.
        scenes:               List of Scene models from the scene detection agent.
        job_dir:              Path to the job directory.
        per_scene_candidates: Number of candidate frames to sample per scene.
        seed:                 Random seed for jitter — same seed = same frames.

    Returns:
        List of CandidateFrame models for all scenes, sorted by scene then timestamp.

    Raises:
        RuntimeError: if ffmpeg is not on PATH.
    """
    _check_ffmpeg()

    frames_dir = job_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    all_candidates: List[CandidateFrame] = []

    for scene in scenes:
        candidates = _sample_scene(
            video_meta=video_meta,
            scene=scene,
            frames_dir=frames_dir,
            per_scene_candidates=per_scene_candidates,
            rng=rng,
        )
        all_candidates.extend(candidates)

    _write_candidates_json(all_candidates, job_dir)

    return all_candidates


# ---------------------------------------------------------------------------
# Per-scene sampling
# ---------------------------------------------------------------------------

def _sample_scene(
    video_meta:           VideoMeta,
    scene:                Scene,
    frames_dir:           Path,
    per_scene_candidates: int,
    rng:                  random.Random,
) -> List[CandidateFrame]:
    """
    Sample per_scene_candidates frames from a single scene.

    Strategy: divide the scene duration into N equal intervals.
    Within each interval, pick a random position (jitter).
    This gives even coverage of the shot while avoiding always
    landing on the same relative position (e.g. always the midpoint).
    """
    duration = scene.duration_sec
    if duration <= 0:
        return []

    n = max(1, per_scene_candidates)

    # compute evenly spaced sample positions with jitter
    interval = duration / n
    timestamps: List[float] = []

    for i in range(n):
        interval_start = scene.start_time + i * interval
        interval_end   = interval_start + interval
        # jitter within the interval, but keep a small margin from edges
        # to avoid extracting frames right at a cut boundary
        margin = interval * 0.05
        t = rng.uniform(
            interval_start + margin,
            max(interval_start + margin + 0.001, interval_end - margin),
        )
        # clamp to scene bounds
        t = max(scene.start_time, min(scene.end_time, t))
        timestamps.append(round(t, 6))

    # extract each frame
    candidates: List[CandidateFrame] = []
    for idx, timestamp in enumerate(timestamps, start=1):
        frame_id   = f"scene_{scene.scene_id:04d}_frame_{idx:04d}"
        frame_path = frames_dir / f"{frame_id}.jpg"

        is_cached = frame_path.exists()
        if not is_cached:
            _extract_frame(video_meta.path, timestamp, frame_path)

        # convert timestamp to absolute frame index
        frame_index = int(timestamp * video_meta.fps)

        candidates.append(CandidateFrame(
            frame_id=frame_id,
            scene_id=scene.scene_id,
            frame_index=frame_index,
            timestamp=timestamp,
            path=str(frame_path),
            is_cached=is_cached,
        ))

    return candidates


# ---------------------------------------------------------------------------
# Frame extraction via ffmpeg
# ---------------------------------------------------------------------------

def _check_ffmpeg() -> None:
    """Raise a clear error if ffmpeg is not available on PATH."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg not found on PATH. "
            "Install FFmpeg and ensure ffmpeg is available: https://ffmpeg.org/download.html"
        )


def _extract_frame(video_path: str, timestamp: float, output_path: Path) -> None:
    """
    Extract a single frame from the video at the given timestamp (seconds)
    and write it as a JPEG to output_path.

    Uses -ss before -i for fast seek (keyframe seek), then -vframes 1
    to grab the single nearest frame. Quality is set to 2 (high, scale 1-31).
    """
    cmd = [
        "ffmpeg",
        "-ss", str(timestamp),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        "-y",                       # overwrite without asking
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg timed out extracting frame at {timestamp:.3f}s")
    except Exception as exc:
        raise RuntimeError(f"ffmpeg failed: {exc}") from exc

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg returned error {result.returncode} extracting frame at "
            f"{timestamp:.3f}s.\nstderr: {result.stderr.strip()}"
        )

    if not output_path.exists():
        raise RuntimeError(
            f"ffmpeg completed but output frame not found: {output_path}"
        )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _write_candidates_json(candidates: List[CandidateFrame], job_dir: Path) -> None:
    """Write candidates list to jobs/<job_id>/candidates.json."""
    out_path = job_dir / "candidates.json"
    data = [c.model_dump(mode="json") for c in candidates]
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")