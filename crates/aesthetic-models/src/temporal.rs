//! Layer 4: Temporal & Editorial Models
//!
//! Evaluates footage in motion across continuous time windows rather than
//! isolated, disconnected frames.

use serde::{Deserialize, Serialize};

/// A continuous temporal window that maintains high quality and stability criteria.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct UsableWindow {
    /// In-point timestamp in seconds
    pub start_sec: f64,
    /// Out-point timestamp in seconds
    pub end_sec: f64,
    /// Continuous usable duration in seconds
    pub duration_sec: f64,
    /// Overall composite quality score across this continuous take (0.0 - 100.0)
    pub window_score: f32,
    /// Mechanical and framing stability score
    pub stability_score: f32,
    /// Recommended trim in-point (accounting for handles and settling)
    pub recommended_in_sec: f64,
    /// Recommended trim out-point
    pub recommended_out_sec: f64,
}

/// Editorial dynamics and pacing metrics for a take or sequence.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct TakeEditorial {
    /// Percentage of time the take holds high-standard visual metrics
    pub quality_persistence: f32,
    /// Seconds elapsed before visual payoff or principal action settles
    pub time_to_visual_payoff_sec: f32,
    /// Cleanliness of take initiation (avoids mid-reframing starts)
    pub entrance_quality: f32,
    /// Cleanliness of take conclusion (avoids abrupt cuts or operator drops)
    pub exit_quality: f32,
    /// How quickly framing settles following a camera or subject move
    pub move_settle_quality: f32,
    /// Viewer center-of-mass jump fatigue across cut boundaries
    pub visual_fatigue_index: f32,
    /// Identified usable windows within the take
    pub usable_windows: Vec<UsableWindow>,
}
