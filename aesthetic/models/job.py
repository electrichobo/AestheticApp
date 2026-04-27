# aesthetic/models/job.py
#
# Data contracts for jobs, video metadata, and shots.
# Every pipeline stage that produces or consumes these types
# imports from here. Nothing in the pipeline passes raw dicts
# for these concepts — always use these models.
#
# Pydantic v2 is required.

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    QUEUED    = "queued"
    INGESTING = "ingesting"
    DETECTING = "detecting"
    SAMPLING  = "sampling"
    METRICS   = "metrics"
    INFERENCE = "inference"
    SELECTING = "selecting"
    EXPORTING = "exporting"
    COMPLETE  = "complete"
    FAILED    = "failed"


class MovementType(str, Enum):
    STATIC   = "static"
    PAN      = "pan"
    TILT     = "tilt"
    DOLLY    = "dolly"
    HANDHELD = "handheld"
    DRONE    = "drone"
    UNKNOWN  = "unknown"


class ShotScale(str, Enum):
    EXTREME_CLOSE  = "extreme_close"
    CLOSE          = "close"
    MEDIUM_CLOSE   = "medium_close"
    MEDIUM         = "medium"
    MEDIUM_WIDE    = "medium_wide"
    WIDE           = "wide"
    EXTREME_WIDE   = "extreme_wide"
    UNKNOWN        = "unknown"


class SceneType(str, Enum):
    INTERIOR_DAY   = "interior_day"
    INTERIOR_NIGHT = "interior_night"
    EXTERIOR_DAY   = "exterior_day"
    EXTERIOR_NIGHT = "exterior_night"
    UNKNOWN        = "unknown"


# ---------------------------------------------------------------------------
# VideoMeta
# Produced by agents/ingest.py from ffprobe output.
# ---------------------------------------------------------------------------

class VideoMeta(BaseModel):
    path:         str
    duration_sec: float           = Field(gt=0)
    fps:          float           = Field(gt=0)
    frame_count:  int             = Field(gt=0)
    width:        int             = Field(gt=0)
    height:       int             = Field(gt=0)
    sar:          str             = "1:1"        # sample aspect ratio
    codec:        str             = "unknown"
    bit_rate:     Optional[int]   = None         # bits per second
    color_space:    Optional[str]   = None
    color_range:    Optional[str]   = None
    color_primaries:Optional[str]   = None   # e.g. bt709, bt2020
    color_trc:      Optional[str]   = None   # transfer characteristic: bt709, smpte2084, arib-std-b67, log, log316
    color_matrix:   Optional[str]   = None   # matrix coefficients: bt709, bt2020nc

    @property
    def is_log_encoded(self) -> bool:
        """True if footage appears to be log-encoded (not display-referred)."""
        log_curves = {
            "slog", "slog2", "slog3",
            "log", "log316",
            "log_c", "log3g10",
            "v_log", "vlog",
            "d_log", "dlog",
            "bt2020-10", "bt2020-12",
            "smpte2084",             # PQ / HDR
            "arib-std-b67",          # HLG / HDR
        }
        trc = (self.color_trc or "").lower().replace("-", "_")
        return any(lc in trc for lc in log_curves)

    @field_validator("fps")
    @classmethod
    def fps_reasonable(cls, v: float) -> float:
        if not (1.0 <= v <= 240.0):
            raise ValueError(f"fps {v} is outside expected range 1-240")
        return v

    @property
    def aspect_ratio(self) -> str:
        from math import gcd
        g = gcd(self.width, self.height)
        return f"{self.width // g}:{self.height // g}"

    @property
    def is_anamorphic(self) -> bool:
        return self.sar not in ("1:1", "1/1", "0:1")


# ---------------------------------------------------------------------------
# Scene
# One detected scene (shot boundary to shot boundary).
# Produced by agents/scenes.py.
# ---------------------------------------------------------------------------

class Scene(BaseModel):
    scene_id:    int
    start_frame: int   = Field(ge=0)
    end_frame:   int   = Field(ge=0)
    start_time:  float = Field(ge=0.0)   # seconds
    end_time:    float = Field(ge=0.0)   # seconds

    @field_validator("end_frame")
    @classmethod
    def end_after_start_frame(cls, v: int, info: Any) -> int:
        if "start_frame" in info.data and v <= info.data["start_frame"]:
            raise ValueError("end_frame must be greater than start_frame")
        return v

    @field_validator("end_time")
    @classmethod
    def end_after_start_time(cls, v: float, info: Any) -> float:
        if "start_time" in info.data and v <= info.data["start_time"]:
            raise ValueError("end_time must be greater than start_time")
        return v

    @property
    def duration_sec(self) -> float:
        return round(self.end_time - self.start_time, 3)

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame


# ---------------------------------------------------------------------------
# CandidateFrame
# A single extracted frame from a scene, awaiting metric scoring.
# Produced by agents/sampling.py.
# ---------------------------------------------------------------------------

class CandidateFrame(BaseModel):
    frame_id:    str          # unique id, e.g. "scene_001_frame_00420"
    scene_id:    int
    frame_index: int          # absolute frame number in source video
    timestamp:   float        # seconds from start of video
    path:        str          # path to extracted frame image on disk
    is_cached:   bool = False # true if frame was reused from a previous run


# ---------------------------------------------------------------------------
# Shot
# A scene that has been scored and selected as a candidate hero shot.
# The primary output unit — has accurate in/out timecodes for export.
# Produced after selection in agents/selection.py.
# ---------------------------------------------------------------------------

class Shot(BaseModel):
    shot_id:       str
    scene_id:      int
    start_time:    float = Field(ge=0.0)   # seconds — accurate for ffmpeg trim
    end_time:      float = Field(ge=0.0)   # seconds — accurate for ffmpeg trim
    start_frame:   int   = Field(ge=0)
    end_frame:     int   = Field(ge=0)
    frame_paths:   List[str] = Field(default_factory=list)   # sampled candidate frames
    hero_frame:    Optional[str] = None                      # best single representative frame
    movement_type: MovementType  = MovementType.UNKNOWN
    shot_scale:    ShotScale     = ShotScale.UNKNOWN
    scene_type:    SceneType     = SceneType.UNKNOWN

    @property
    def duration_sec(self) -> float:
        return round(self.end_time - self.start_time, 3)


# ---------------------------------------------------------------------------
# Job
# Top-level container for a single analysis run.
# Created by bridge/api.py and persisted to jobs/<job_id>/manifest.json.
# ---------------------------------------------------------------------------

class Job(BaseModel):
    job_id:           str
    source_file:      str
    status:           JobStatus = JobStatus.QUEUED
    created:          str       = Field(
                          default_factory=lambda: datetime.now(timezone.utc)
                                                          .replace(microsecond=0)
                                                          .isoformat()
                      )
    analyzed:         Optional[str]       = None
    config:           Dict[str, Any]      = Field(default_factory=dict)
    video_meta:       Optional[VideoMeta] = None
    scenes:           List[Scene]         = Field(default_factory=list)
    shots:            List[Shot]          = Field(default_factory=list)
    baseline_version: int                 = 0
    seed:             int                 = 42
    error:            Optional[str]       = None

    @property
    def source_stem(self) -> str:
        return Path(self.source_file).stem

    def to_manifest_dict(self) -> Dict[str, Any]:
        """Serialize to a clean dict suitable for manifest.json on disk."""
        return self.model_dump(mode="json", exclude_none=False)