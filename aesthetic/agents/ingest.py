# aesthetic/agents/ingest.py
#
# Ingest agent — reads video file metadata via ffprobe and returns a
# validated VideoMeta model. This is always the first stage in the pipeline.
#
# Requires ffprobe on PATH. Fails fast and clearly if it is not available.

from __future__ import annotations

import json
import subprocess
import sys as _sys
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if _sys.platform == "win32" else 0
import sys as _sys
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if _sys.platform == "win32" else 0
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from ..models.job import VideoMeta


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def ingest(source_path: str) -> VideoMeta:
    """
    Run ffprobe on the given video file and return a validated VideoMeta.

    Raises:
        RuntimeError: if ffprobe is not on PATH
        FileNotFoundError: if source_path does not exist
        ValueError: if ffprobe output cannot be parsed into a valid VideoMeta
    """
    _check_ffprobe()

    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    if not path.is_file():
        raise ValueError(f"Source path is not a file: {source_path}")

    raw = _run_ffprobe(path)
    return _parse_ffprobe(path, raw)


# ---------------------------------------------------------------------------
# ffprobe helpers
# ---------------------------------------------------------------------------

def _check_ffprobe() -> None:
    """Raise a clear error if ffprobe is not available on PATH."""
    if shutil.which("ffprobe") is None:
        raise RuntimeError(
            "ffprobe not found on PATH. "
            "Install FFmpeg and ensure ffprobe is available: https://ffmpeg.org/download.html"
        )


def _run_ffprobe(path: Path) -> Dict[str, Any]:
    """
    Run ffprobe in JSON mode and return the parsed output dict.
    Uses -v quiet to suppress progress output.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timed out on: {path}")
    except Exception as exc:
        raise RuntimeError(f"ffprobe failed to run: {exc}") from exc

    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe returned error code {result.returncode}.\n"
            f"stderr: {result.stderr.strip()}"
        )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"ffprobe output could not be parsed as JSON: {exc}") from exc


def _parse_ffprobe(path: Path, raw: Dict[str, Any]) -> VideoMeta:
    """
    Extract the fields we need from the ffprobe JSON output and
    construct a validated VideoMeta.

    ffprobe returns a list of streams. We look for the first video stream.
    """
    streams = raw.get("streams", [])
    fmt     = raw.get("format", {})

    # find the first video stream
    video_stream: Optional[Dict[str, Any]] = None
    for stream in streams:
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if video_stream is None:
        raise ValueError(f"No video stream found in: {path}")

    # --- duration ---
    # prefer stream duration, fall back to format duration
    duration_sec = _float_or(video_stream.get("duration")) \
                or _float_or(fmt.get("duration"))
    if duration_sec is None or duration_sec <= 0:
        raise ValueError(f"Could not determine video duration for: {path}")

    # --- frame rate ---
    # r_frame_rate is the "real" frame rate, e.g. "24000/1001" or "25/1"
    fps = _parse_fraction(video_stream.get("r_frame_rate", "0/1"))
    if fps <= 0:
        fps = _parse_fraction(video_stream.get("avg_frame_rate", "0/1"))
    if fps <= 0:
        raise ValueError(f"Could not determine frame rate for: {path}")

    # --- frame count ---
    frame_count = _int_or(video_stream.get("nb_frames"))
    if frame_count is None or frame_count <= 0:
        # estimate from duration and fps
        frame_count = max(1, int(duration_sec * fps))

    # --- dimensions ---
    width  = _int_or(video_stream.get("width"))
    height = _int_or(video_stream.get("height"))
    if not width or not height:
        raise ValueError(f"Could not determine video dimensions for: {path}")

    # --- sample aspect ratio ---
    sar = video_stream.get("sample_aspect_ratio", "1:1") or "1:1"
    # normalise "0:1" (unknown) to "1:1"
    if sar in ("0:1", "0/1", ""):
        sar = "1:1"

    # --- bit rate ---
    bit_rate = _int_or(video_stream.get("bit_rate")) \
            or _int_or(fmt.get("bit_rate"))

    return VideoMeta(
        path=str(path),
        duration_sec=round(duration_sec, 6),
        fps=round(fps, 6),
        frame_count=frame_count,
        width=width,
        height=height,
        sar=sar,
        codec=video_stream.get("codec_name", "unknown"),
        bit_rate=bit_rate,
        color_space=video_stream.get("color_space"),
        color_range=video_stream.get("color_range"),
    )


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------

def _float_or(value: Any) -> Optional[float]:
    """Convert value to float, return None on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or(value: Any) -> Optional[int]:
    """Convert value to int, return None on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_fraction(frac: str) -> float:
    """
    Parse a fraction string like '24000/1001' or '25/1' into a float.
    Returns 0.0 on failure.
    """
    try:
        parts = frac.split("/")
        if len(parts) == 2:
            num, den = float(parts[0]), float(parts[1])
            return num / den if den != 0 else 0.0
        return float(frac)
    except (ValueError, ZeroDivisionError):
        return 0.0