//! Multi-Camera Setup & Cross-Angle Continuity Matching Models
//!
//! Evaluates multi-camera setups within a scene or sequence, computing
//! cross-angle exposure, color temperature, and lighting consistency,
//! and generating recommended ASC CDL color grading corrections to match
//! secondary angles to the Hero Master.

use serde::{Deserialize, Serialize};

/// Industry-standard American Society of Cinematographers Color Decision List (ASC CDL) correction.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AscCdlCorrection {
    /// Slope (Gain): Multiplier for highlights per RGB channel (nominally 1.0)
    pub slope: [f32; 3],
    /// Offset (Lift): Additive shift for shadows per RGB channel (nominally 0.0)
    pub offset: [f32; 3],
    /// Power (Gamma): Exponential curve for midtones per RGB channel (nominally 1.0)
    pub power: [f32; 3],
    /// Saturation: Global chroma multiplier (nominally 1.0)
    pub saturation: f32,
    /// Concise grading directive describing what adjustments to make
    pub summary_guidance: String,
}

impl Default for AscCdlCorrection {
    fn default() -> Self {
        Self {
            slope: [1.0, 1.0, 1.0],
            offset: [0.0, 0.0, 0.0],
            power: [1.0, 1.0, 1.0],
            saturation: 1.0,
            summary_guidance: "Neutral: Angle is perfectly matched to Master".to_string(),
        }
    }
}

/// Pairwise match metrics and grading guidance between two setups/angles.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PairwiseSetupDelta {
    pub source_take_id: String,
    pub target_take_id: String,
    /// Exposure difference in EV stops (positive = source is brighter than target)
    pub exposure_stops_delta: f32,
    /// White balance temperature difference in Kelvin (positive = source is warmer)
    pub kelvin_delta: f32,
    /// Perceptual color difference (CIE Delta E 2000)
    pub color_delta_e: f32,
    /// Lighting key-to-fill ratio difference
    pub key_to_fill_ratio_delta: f32,
    /// Acutance / sharpness ratio (source / target)
    pub sharpness_ratio: f32,
    /// Categorical matching classification:
    /// "Matched (< 1.5 ΔE)", "Minor Trim Needed (1.5–3.0 ΔE)", or "Grading Correction Advised (> 3.0 ΔE)"
    pub match_status: String,
    /// Recommended ASC CDL values to align source angle to target master
    pub recommended_cdl: AscCdlCorrection,
}

/// Comprehensive cross-angle setup continuity report for a scene or episode.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct CrossAngleMatchReport {
    pub group_name: String,
    pub hero_master_take_id: String,
    pub total_takes: usize,
    pub average_scene_delta_e: f32,
    pub max_exposure_stops_delta: f32,
    pub max_kelvin_delta: f32,
    /// Overall multi-camera continuity score (0.0 - 100.0)
    pub overall_consistency_score: f32,
    /// Detailed pairwise deltas and CDL recommendations against the Hero Master
    pub pairwise_matches: Vec<PairwiseSetupDelta>,
}
