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
}
