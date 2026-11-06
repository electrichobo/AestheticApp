//! Window, Take, and 4-Output Shot Analysis Structures

use crate::baseline::BaselineMetricComparison;
use crate::forensics::DiagnosticFlag;
use crate::inferred::ModelInferredCraft;
use crate::physics::ObjectivePhysics;
use serde::{Deserialize, Serialize};

/// Concrete pillar scores normalized to 0.0 - 100.0 based on empirical baseline distribution.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct PillarScores {
    /// Overall composite score (0.0 - 100.0)
    pub overall: f32,
    /// Objective physical quality (0.0 - 100.0)
    pub technical: f32,
    /// Aesthetic & baseline corpus similarity (0.0 - 100.0)
    pub creative: f32,
    /// Sustained temporal stability and window quality (0.0 - 100.0)
    pub temporal: f32,
    /// True only when `temporal` was actually measured from motion between frames.
    /// When false, `temporal` is not a measurement and is excluded from `overall`.
    #[serde(default)]
    pub temporal_measured: bool,
    /// Hero-frame potency (0.0 - 100.0): suitability as a representative showreel thumbnail/still.
    #[serde(default)]
    pub hero_potency_score: f32,
    /// Three-second impact (0.0 - 100.0): immediate visual authority in the opening 3 seconds.
    #[serde(default)]
    pub three_second_impact_score: f32,
    /// Authorship & distinctiveness (0.0 - 100.0): intentional visual signature strength.
    #[serde(default)]
    pub authorship_distinctiveness_score: f32,
    /// Visual storytelling effectiveness (0.0 - 100.0): multi-plane staging, lead room, and lighting motivation.
    #[serde(default)]
    pub storytelling_score: f32,
    /// Cinematic technique quality (0.0 - 100.0): camera control, motion coherence, bokeh falloff, and roll-off.
    #[serde(default)]
    pub cinematic_technique_score: f32,
    /// Visual memorability (0.0 - 100.0): focal saliency concentration, chromatic/tonal contrast, and baseline alignment.
    #[serde(default)]
    pub memorability_score: f32,
}

/// Automatically discovered style and visual classification.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct DiscoveredStyle {
    /// Automatic lighting key classification: "High-Key", "Mid-Key", or "Low-Key Chiaroscuro"
    pub lighting_key: String,
    /// Movement type: "Static", "Smooth Track / Dolly", "Cinematic Handheld", "Kinetic Pan"
    pub motion_type: String,
    /// Framing scale: "Extreme Wide", "Wide", "Medium", "Close-Up", "Extreme Close-Up"
    pub shot_scale: String,
    /// Closest Cinematographer style signature (e.g. "Roger Deakins (Skyfall)")
    pub cinematographer_match: Option<String>,
    /// Match confidence (0.0 - 100.0)
    pub match_confidence: f32,
    /// Style Family Cluster: "Chiaroscuro Noir", "Prestige Naturalism", "Expressive Color", "High-Key Pastel", "Documentary Vérité", "Atmospheric Silver"
    pub style_family: String,
    /// Chromatic palette family: "Warm Tungsten / Amber", "Cool Cyan / Moonlight", "Complementary Teal-Orange", "Desaturated Silver", "Natural Daylight"
    #[serde(default)]
    pub palette_family: String,
    /// Multi-signal scene environment classification: "Exterior Daylight", "Interior Warm / Practical", "Night / Low-Key", "Controlled Studio"
    #[serde(default)]
    pub scene_type: String,
    /// Narrative shot intent: "Intimate Character", "Establishing / Architectural", "Kinetic Action", "Dialogue / Two-Shot", "Atmospheric / Transitional"
    #[serde(default)]
    pub shot_intent: String,
}

/// User select feedback event logged to `assets/feedback/events.jsonl` to personalize reranker heads.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SelectFeedbackEvent {
    pub timestamp_unix: u64,
    pub take_id: String,
    /// Action: "promote_hero", "pin_select", "reject_take", "trim_handles"
    pub action: String,
    pub style_family: String,
    pub shot_scale: String,
    pub overall_score: f32,
    pub hero_potency_score: f32,
    pub storytelling_score: f32,
    pub memorability_score: f32,
}

/// The 4-Output structured evaluation of a candidate shot / take.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct ShotTake {
    pub take_id: String,
    pub scene_index: usize,
    pub start_sec: f64,
    pub end_sec: f64,
    pub duration_sec: f64,
    pub hero_frame_index: Option<u64>,
    pub hero_timestamp_sec: f64,

    // Output 1: Tangible 0-100 Pillar Scores
    pub scores: PillarScores,

    // Output 2: Automatic Style & Master Fingerprint
    pub style: DiscoveredStyle,

    // Output 3: Raw Measured Properties
    pub measured: ObjectivePhysics,

    // Output 4: Non-Punitive Technical Concerns / Diagnostic Flags
    pub concerns: Vec<DiagnosticFlag>,

    /// Model-inferred craft layer (lighting geometry, focus, staging, motion) when computed.
    #[serde(default)]
    pub craft: Option<ModelInferredCraft>,

    /// Measured metrics placed within the measured award-cinema Golden Baseline distribution.
    #[serde(default)]
    pub golden_baseline: Vec<BaselineMetricComparison>,

    /// Concise, deterministic natural-language DP & Editorial rationale explaining the shot's ranking (M20).
    #[serde(default)]
    pub rationale_summary: String,
}
