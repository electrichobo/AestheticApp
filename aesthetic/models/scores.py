# aesthetic/models/scores.py
#
# Data contracts for all scoring output.
# FrameMetrics holds raw per-frame measurements from the metrics engine.
# ShotScore holds the aggregated pillar and category scores for a shot.
# Manifest is the final output document written to disk after a completed run.
#
# Every numeric score is in the range 0.0 - 100.0 unless noted otherwise.
# Pydantic v2 is required.

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Score field shorthand
# All scores 0.0 - 100.0, default None (not yet computed)
# ---------------------------------------------------------------------------

def _score() -> Optional[float]:
    return None


# ---------------------------------------------------------------------------
# Exposure metrics
# Produced by agents/metrics.py for a single candidate frame.
# ---------------------------------------------------------------------------

class ExposureMetrics(BaseModel):
    histogram_mean:       Optional[float] = None   # 0-255 luminance mean
    histogram_median:     Optional[float] = None
    histogram_std:        Optional[float] = None
    histogram_skew:       Optional[float] = None
    histogram_kurtosis:   Optional[float] = None
    highlight_clip_pct:   Optional[float] = None   # % of pixels clipped high
    shadow_clip_pct:      Optional[float] = None   # % of pixels clipped low
    psnr:                 Optional[float] = None
    ssim:                 Optional[float] = None
    third_moment_18gray:  Optional[float] = None   # deviation from 18% gray
    snr_luma:             Optional[float] = None
    snr_chroma:           Optional[float] = None
    temporal_consistency: Optional[float] = None   # variance across shot frames
    exposure_intent:      Optional[float] = None   # rule-based intent match score


# ---------------------------------------------------------------------------
# Lighting metrics
# ---------------------------------------------------------------------------

class LightingMetrics(BaseModel):
    dynamic_range_stops:  Optional[float] = None
    key_fill_ratio:       Optional[float] = None
    color_temp_kelvin:    Optional[float] = None
    color_temp_deviation: Optional[float] = None
    shadow_detail:        Optional[float] = None
    shadow_noise:         Optional[float] = None
    transition_hardness:  Optional[float] = None   # 0=soft, 100=hard
    coverage_consistency:    Optional[float] = None   # cross-shot consistency
    light_motivation:        Optional[float] = None   # heuristic motivated/unmotivated
    lighting_style_adherence:Optional[float] = None   # creative: delta vs baseline lighting style


# ---------------------------------------------------------------------------
# Composition metrics
# ---------------------------------------------------------------------------

class CompositionMetrics(BaseModel):
    rule_of_thirds:       Optional[float] = None
    face_placement:       Optional[float] = None   # score for face position in frame
    face_count:           Optional[int]   = None
    center_of_mass_x:     Optional[float] = None   # 0.0-1.0 normalized
    center_of_mass_y:     Optional[float] = None
    negative_space_ratio: Optional[float] = None
    depth_separation:     Optional[float] = None   # MiDaS subject/background separation
    occupancy_map_score:  Optional[float] = None
    symmetry_score:       Optional[float] = None
    headroom:             Optional[float] = None
    lead_room:            Optional[float] = None
    shot_scale:           Optional[str]   = None   # ShotScale enum value
    frame_balance:        Optional[float] = None   # composite balance score


# ---------------------------------------------------------------------------
# Camera movement metrics
# ---------------------------------------------------------------------------

class MovementMetrics(BaseModel):
    optical_flow_mean:    Optional[float] = None   # average flow magnitude
    optical_flow_std:     Optional[float] = None
    smoothness:           Optional[float] = None   # inverse of jerkiness
    jerkiness:            Optional[float] = None
    stabilization:        Optional[float] = None   # residual micro-jitter
    motion_blur_amount:   Optional[float] = None
    motion_blur_direction:Optional[float] = None   # degrees, Radon-based
    movement_type:        Optional[str]   = None   # MovementType enum value
    shot_duration_sec:    Optional[float] = None
    focus_during_movement:Optional[float] = None
    trajectory_smoothness:Optional[float] = None


# ---------------------------------------------------------------------------
# Color metrics
# ---------------------------------------------------------------------------

class ColorMetrics(BaseModel):
    wb_deviation:         Optional[float] = None   # white balance error
    wb_cross_scene_var:   Optional[float] = None
    saturation_mean:      Optional[float] = None   # Lab saturation
    saturation_uniformity:Optional[float] = None
    palette_entropy:      Optional[float] = None
    palette_family:       Optional[str]   = None   # e.g. "warm", "cool", "desaturated"
    color_accuracy_de2000:Optional[float] = None   # ΔE2000 when reference available
    skin_tone_de:         Optional[float] = None   # skin tone ΔE accuracy
    grading_uniformity:   Optional[float] = None   # cross-shot grading consistency
    chroma_noise:         Optional[float] = None   # noise in a* b* channels
    banding_score:        Optional[float] = None   # banding artifact proxy
    color_temp_variance:  Optional[float] = None   # cross-scene color temp variance


# ---------------------------------------------------------------------------
# Image quality metrics
# ---------------------------------------------------------------------------

class QualityMetrics(BaseModel):
    sharpness_laplacian:  Optional[float] = None   # Laplacian variance
    sharpness_edge_density:Optional[float]= None
    mtf_proxy:            Optional[float] = None   # MTF-based sharpness estimate
    lens_distortion:      Optional[float] = None   # % distortion proxy
    vignetting_stops:     Optional[float] = None   # center-to-edge light loss
    ca_width_px:          Optional[float] = None   # chromatic aberration width
    flare_contrast_loss:  Optional[float] = None
    compression_blocking:  Optional[float] = None
    compression_banding:   Optional[float] = None
    compression_mosquito:  Optional[float] = None
    compression_ringing:   Optional[float] = None
    texture_retention:     Optional[float] = None   # local SSIM on textured regions
    vmaf:                  Optional[float] = None   # optional QC pack - requires reference
    psnr_qc:               Optional[float] = None   # optional QC pack - requires reference
    ssim_qc:               Optional[float] = None   # optional QC pack - requires reference


# ---------------------------------------------------------------------------
# Narrative and aesthetic metrics
# ---------------------------------------------------------------------------

class NarrativeMetrics(BaseModel):
    saliency_consistency:        Optional[float] = None   # attention proxy (eye tracking substitute)
    compelling_mos:              Optional[float] = None   # rule-based MOS seed
    visual_storytelling:         Optional[float] = None   # learned classifier — placeholder until Phase 6
    cinematic_technique_quality: Optional[float] = None   # learned classifier — placeholder until Phase 6
    memorability:                Optional[float] = None   # CLIP similarity + aesthetic regressor — Phase 6
    # av_richness intentionally omitted — future placeholder, requires audio analysis


# ---------------------------------------------------------------------------
# AI model inference outputs
# Cached per frame — never re-computed unless model version changes.
# ---------------------------------------------------------------------------

class InferenceOutputs(BaseModel):
    clip_embedding:       Optional[List[float]] = None   # CLIP embedding vector
    clip_model_version:   Optional[str]         = None
    depth_map_path:       Optional[str]         = None   # MiDaS depth map on disk
    detections:           Optional[List[Dict[str, Any]]] = None  # YOLO results
    nima_score:           Optional[float]       = None   # aesthetic predictor score
    laion_score:          Optional[float]       = None   # LAION aesthetic score
    vlm_rationale:        Optional[str]         = None   # VLM explanation text
    vlm_model_version:    Optional[str]         = None


# ---------------------------------------------------------------------------
# FrameMetrics
# Complete per-frame measurement record.
# Written to jobs/<job_id>/metrics/<frame_id>.json as a sidecar.
# ---------------------------------------------------------------------------

class FrameMetrics(BaseModel):
    frame_id:    str
    scene_id:    int
    timestamp:   float
    frame_path:  str

    exposure:    ExposureMetrics    = Field(default_factory=ExposureMetrics)
    lighting:    LightingMetrics    = Field(default_factory=LightingMetrics)
    composition: CompositionMetrics = Field(default_factory=CompositionMetrics)
    movement:    MovementMetrics    = Field(default_factory=MovementMetrics)
    color:       ColorMetrics       = Field(default_factory=ColorMetrics)
    quality:     QualityMetrics     = Field(default_factory=QualityMetrics)
    narrative:   NarrativeMetrics   = Field(default_factory=NarrativeMetrics)
    inference:   InferenceOutputs   = Field(default_factory=InferenceOutputs)

    metrics_version: str = "1.0"   # bump when metric definitions change

    def to_sidecar_dict(self) -> Dict[str, Any]:
        """Serialize to dict for writing to disk as a JSON sidecar."""
        return self.model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# CategoryScore
# Rolled-up score for one category (e.g. Exposure) across all three pillars.
# ---------------------------------------------------------------------------

class CategoryScore(BaseModel):
    technical:  Optional[float] = Field(None, ge=0.0, le=100.0)
    creative:   Optional[float] = Field(None, ge=0.0, le=100.0)
    subjective: Optional[float] = Field(None, ge=0.0, le=100.0)
    total:      Optional[float] = Field(None, ge=0.0, le=100.0)

    def compute_total(
        self,
        w_technical:  float = 0.50,
        w_creative:   float = 0.30,
        w_subjective: float = 0.20,
    ) -> float:
        """Compute weighted total from available pillar scores."""
        parts, weights = [], []
        if self.technical  is not None: parts.append(self.technical  * w_technical);  weights.append(w_technical)
        if self.creative   is not None: parts.append(self.creative   * w_creative);   weights.append(w_creative)
        if self.subjective is not None: parts.append(self.subjective * w_subjective); weights.append(w_subjective)
        if not weights:
            return 0.0
        total = sum(parts) / sum(weights)
        return round(total, 2)


# ---------------------------------------------------------------------------
# ShotScore
# Aggregated score for a complete shot (multiple frames collapsed to one record).
# The temporal variance fields capture consistency across the shot duration.
# ---------------------------------------------------------------------------

class ShotScore(BaseModel):
    shot_id: str
    scene_id: int

    # per-category scores
    exposure:    CategoryScore = Field(default_factory=CategoryScore)
    lighting:    CategoryScore = Field(default_factory=CategoryScore)
    composition: CategoryScore = Field(default_factory=CategoryScore)
    movement:    CategoryScore = Field(default_factory=CategoryScore)
    color:       CategoryScore = Field(default_factory=CategoryScore)
    quality:     CategoryScore = Field(default_factory=CategoryScore)
    narrative:   CategoryScore = Field(default_factory=CategoryScore)

    # pillar subtotals (weighted average across all categories)
    technical_total:  Optional[float] = Field(None, ge=0.0, le=100.0)
    creative_total:   Optional[float] = Field(None, ge=0.0, le=100.0)
    subjective_total: Optional[float] = Field(None, ge=0.0, le=100.0)

    # composite
    total_score: Optional[float] = Field(None, ge=0.0, le=100.0)

    # temporal consistency — high variance within a shot is a negative signal
    temporal_variance: Optional[float] = None

    # baseline reference
    baseline_version:         int           = 0
    baseline_similarity_score: Optional[float] = None   # cosine sim to Golden Baseline

    # explanation
    rationale: Optional[str] = None   # VLM-generated explanation

    # frame count used for aggregation
    frame_count: int = 0

    def category_list(self) -> List[Dict[str, Any]]:
        """Return all category scores as a list for UI rendering."""
        return [
            {"name": "exposure",    "scores": self.exposure.model_dump()},
            {"name": "lighting",    "scores": self.lighting.model_dump()},
            {"name": "composition", "scores": self.composition.model_dump()},
            {"name": "movement",    "scores": self.movement.model_dump()},
            {"name": "color",       "scores": self.color.model_dump()},
            {"name": "quality",     "scores": self.quality.model_dump()},
            {"name": "narrative",   "scores": self.narrative.model_dump()},
        ]


# ---------------------------------------------------------------------------
# Manifest
# The final output document for a completed analysis run.
# Written to outputs/<job_id>/<stem>_<job_id>_manifest.json.
# Human-readable and machine-parseable. Every decision is explained.
# ---------------------------------------------------------------------------

class Manifest(BaseModel):
    schema_version:   str = "1.0"   # bump when manifest structure changes
    job_id:           str
    source_file:      str
    created:          str
    analyzed:         Optional[str] = None
    seed:             int = 42

    # config snapshot — exact config used for this run
    config:           Dict[str, Any] = Field(default_factory=dict)

    # baseline reference
    baseline_version: int           = 0
    baseline_hash:    Optional[str] = None

    # pipeline outputs
    scene_count:      int = 0
    candidate_count:  int = 0
    selected_count:   int = 0
    shots:            List[Dict[str, Any]] = Field(default_factory=list)

    # sidecar index — every artifact this run produced
    sidecars:         List[str] = Field(default_factory=list)

    # export paths
    contact_sheet:    Optional[str] = None
    hero_clips_dir:   Optional[str] = None
    hero_frames_dir:  Optional[str] = None

    # run diagnostics
    pipeline_timing:  Dict[str, float] = Field(default_factory=dict)   # stage: seconds
    warnings:         List[str]        = Field(default_factory=list)
    errors:           List[str]        = Field(default_factory=list)

    def to_output_dict(self) -> Dict[str, Any]:
        """Serialize to dict for writing to disk."""
        return self.model_dump(mode="json", exclude_none=False)