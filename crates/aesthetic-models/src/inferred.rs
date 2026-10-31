//! Layer 2: Model-Inferred Craft Models
//!
//! Properties estimated through machine perception models (depth, optical flow,
//! facial landmarks, bounding boxes, and lighting geometry).

use serde::{Deserialize, Serialize};

/// Lighting geometry and directional balance inferred from scene geometry.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct LightingGeometry {
    pub key_to_fill_ratio: f32,
    /// Estimated horizontal angle of dominant light source in degrees (-180 to 180)
    pub key_azimuth_deg: Option<f32>,
    /// Estimated elevation angle of dominant light source in degrees (0 to 90)
    pub key_elevation_deg: Option<f32>,
    /// Rim or edge lighting separation score (0.0 - 100.0)
    pub rim_light_separation: f32,
    /// Shadow boundary gradient width (soft vs hard light)
    pub shadow_softness: f32,
    /// Catchlight specular reflection intensity in subject eyes/face (0.0 - 100.0)
    #[serde(default)]
    pub catchlight_intensity: f32,
}

/// Focus behavior and optical transitions inferred over time.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct FocusOptics {
    pub subject_focus_accuracy: f32,
    pub eye_sharpness: Option<f32>,
    pub focus_hunting_score: f32,
    pub focus_breathing_score: f32,
    pub rack_focus_detected: bool,
}

/// Motion intentionality and dynamics distinguishing camera vs subject movement.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct MotionDynamics {
    pub optical_flow_mean: f32,
    pub optical_flow_std: f32,
    /// Proportion of motion caused by camera movement vs independent subject movement
    pub camera_motion_ratio: f32,
    /// High-frequency accidental camera shake / micro-jitter
    pub micro_jitter_score: f32,
    /// Parallax differentiation across depth layers
    pub parallax_strength: f32,
    /// Risk of strobe or judder from excessive pan/tilt angular velocity at frame rate
    pub judder_risk_score: f32,
}

/// Staging, gaze vectors, and spatial composition.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct StagingEyeline {
    pub gaze_vector_x: Option<f32>,
    pub gaze_vector_y: Option<f32>,
    pub looking_room_score: f32,
    pub depth_separation_score: f32,
    pub depth_plane_count: u32,
    pub silhouette_clarity: f32,
    pub face_count: u32,
    /// Gaze poise score (0.0 - 100.0) balancing headroom, lead room, and eyeline on thirds
    #[serde(default)]
    pub gaze_poise_score: f32,
}

/// Combined Model-Inferred Craft bundle.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct ModelInferredCraft {
    pub lighting: LightingGeometry,
    pub focus: FocusOptics,
    pub motion: MotionDynamics,
    pub staging: StagingEyeline,
}
