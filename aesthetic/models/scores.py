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

from typing import Any, ClassVar, Dict, List, Optional
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
    # --- exposure refinement ---
    highlight_rolloff:    Optional[float] = None   # 0=hard clip, 100=smooth shoulder
    midtone_separation:   Optional[float] = None   # midband histogram spread (0-100)
    toe_character:        Optional[float] = None   # shadow curve shape score
    shoulder_character:   Optional[float] = None   # highlight curve shape score
    skin_ire_placement:   Optional[float] = None   # face luma % IRE (0=crushed,100=clipped)
    flicker_score:        Optional[float] = None   # temporal luma variance (0=clean,100=bad)


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
    # --- lighting design ---
    lighting_complexity:  Optional[float] = None   # estimated number of distinct light sources
    atmosphere_density:   Optional[float] = None   # haze/fog/smoke scattering signal (0-100)


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
    # --- composition sophistication ---
    depth_plane_count:    Optional[float] = None   # distinct MiDaS depth layers with content
    silhouette_clarity:   Optional[float] = None   # subject edge contrast vs background


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

class FocusMetrics(BaseModel):
    """Per-frame focus quality and temporal focus behaviour."""
    subject_focus_accuracy: Optional[float] = None  # sharpness in subject region (0-100)
    eye_sharpness:          Optional[float] = None  # Laplacian in detected eye region (0-100)
    catchlight_quality:     Optional[float] = None  # specular highlight in eye (0=none,100=good)
    rack_focus_detected:    Optional[float] = None  # 0=no rack, 1=rack detected
    focus_hunting:          Optional[float] = None  # oscillating sharpness variance (0=clean)
    focus_breathing:        Optional[float] = None  # apparent magnification change during focus


class SubjectMetrics(BaseModel):
    """SigLIP zero-shot + emotion model — subjective signal."""
    # readability
    subject_clarity:        Optional[float] = None  # SigLIP: clear subject vs ambiguous frame
    mood_clarity:           Optional[float] = None  # SigLIP: immediate emotional tone clarity
    one_sec_comprehension:  Optional[float] = None  # SigLIP: immediately understandable
    # thumbnail potency
    thumbnail_strength:     Optional[float] = None  # SigLIP: compelling at small size
    portfolio_potential:    Optional[float] = None  # SigLIP: portfolio/showreel hero frame
    graphic_simplicity:     Optional[float] = None  # SigLIP: graphically simple and strong
    # human moment
    facial_emotion_intensity:Optional[float]= None  # emotion model: peak emotion confidence
    dominant_emotion:        Optional[str]  = None  # emotion label (happy/sad/neutral/etc.)
    gesture_readability:     Optional[float] = None  # SigLIP: clear body language
    presence_signal:         Optional[float] = None  # SigLIP: screen presence / charisma
    gaze_direction_score:    Optional[float] = None  # lead_room proxy (already in composition)
    silhouette_readability:  Optional[float] = None  # SigLIP: strong silhouette read
    # world/mood
    atmosphere_mood:        Optional[float] = None  # SigLIP: cohesive atmosphere/world


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
    # --- colour design ---
    complementary_use:    Optional[float] = None   # complementary hue pair presence (0-100)
    analogous_use:        Optional[float] = None   # analogous palette coherence (0-100)
    warm_cool_contrast:   Optional[float] = None   # warm vs cool pixel area ratio distance
    color_separation:     Optional[float] = None   # inter-region colour distinguishability


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
    # --- production artifact detection ---
    over_sharpening:       Optional[float] = None   # halo energy around edges (0=clean,100=bad)
    dead_pixel_score:      Optional[float] = None   # isolated extreme pixels (0=clean,100=bad)
    rolling_shutter_wobble:Optional[float] = None   # non-uniform horizontal flow distortion
    moire_score:           Optional[float] = None   # periodic high-freq FFT pattern energy
    ai_upscaling_artifact: Optional[float] = None   # texture anomaly + edge pattern score
    dirty_lens_score:      Optional[float] = None   # diffuse low-freq blob in frame edge
    unwanted_reflection:   Optional[float] = None   # specular patch inconsistency score


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
    midas_depth_separation: Optional[float]     = None   # depth separation score from MiDaS (0-100)
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
    focus:       FocusMetrics       = Field(default_factory=FocusMetrics)
    subject:     SubjectMetrics     = Field(default_factory=SubjectMetrics)
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

    NEUTRAL: ClassVar[float] = 50.0   # unknown = neutral, not penalised

    @property
    def technical_or_neutral(self) -> float:
        """Return technical score, or 50 if not yet computed. Never penalises."""
        return self.technical if self.technical is not None else self.NEUTRAL

    @property
    def creative_or_neutral(self) -> float:
        return self.creative if self.creative is not None else self.NEUTRAL

    @property
    def subjective_or_neutral(self) -> float:
        return self.subjective if self.subjective is not None else self.NEUTRAL

    def compute_total(
        self,
        w_technical:  float = 0.50,
        w_creative:   float = 0.30,
        w_subjective: float = 0.20,
    ) -> float:
        """Compute weighted total from available pillar scores.
        Missing scores use neutral midpoint (50) rather than being
        excluded, so all pillar weights are always active."""
        tech = self.technical  if self.technical  is not None else self.NEUTRAL
        creat= self.creative   if self.creative   is not None else self.NEUTRAL
        subj = self.subjective if self.subjective is not None else self.NEUTRAL
        total = tech * w_technical + creat * w_creative + subj * w_subjective
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

    # per-metric detail — averaged raw metric values per category
    # structure: {category: {metric_name: avg_value}}
    metric_detail: Optional[Dict[str, Dict[str, float]]] = None

    # colour analysis
    delta_e_d65:        Optional[float] = None
    delta_e_baseline:   Optional[float] = None
    gamut_coverage:     Optional[Dict[str, float]] = None
    dominant_colours:   Optional[List[List[float]]] = None
    per_frame_colours:  Optional[List[List[List[float]]]] = None  # per-frame CIE clusters
    waveform:           Optional[List[List[float]]] = None         # [col][p5,p25,p50,p75,p95]
    parade_r:           Optional[List[List[float]]] = None
    parade_g:           Optional[List[List[float]]] = None
    parade_b:           Optional[List[List[float]]] = None
    skin_tone_detected: bool = False

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