//! Layer 1: Objective Physics Models
//!
//! Pure mathematical pixel calculations that are directly measurable,
//! reproducible, and deterministic.

use serde::{Deserialize, Serialize};

/// Distribution across false-color exposure zones (in percentages 0.0 - 100.0).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct FalseColorZones {
    /// Crushed black / sub-zero IRE (< 2% IRE)
    pub black_clip_pct: f32,
    /// Shadow detail zone (2% - 20% IRE)
    pub shadow_zone_pct: f32,
    /// 18% middle gray target zone (35% - 45% IRE)
    pub middle_gray_pct: f32,
    /// Caucasian / healthy skin tone zone (50% - 65% IRE)
    pub skin_zone_pct: f32,
    /// High-key / highlight modeling zone (70% - 90% IRE)
    pub highlight_zone_pct: f32,
    /// Specular clipping ceiling (> 98% IRE)
    pub specular_clip_pct: f32,
}

/// Exposure and tonal physics measurements.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct ExposurePhysics {
    pub histogram_mean: f32,
    pub histogram_median: f32,
    pub histogram_std: f32,
    pub histogram_skew: f32,
    pub histogram_kurtosis: f32,
    pub highlight_clip_pct: f32,
    pub shadow_clip_pct: f32,
    /// Smoothness of highlight compression gradient (0.0 = hard digital clip, 100.0 = smooth roll-off)
    pub highlight_rolloff: f32,
    pub dynamic_range_stops: f32,
    pub snr_luma: f32,
    pub snr_chroma: f32,
    pub false_color_zones: FalseColorZones,
}

/// Optical, sharpness, and lens physics measurements.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct OpticalPhysics {
    /// Laplacian operator variance (high frequency sharpness)
    pub sharpness_laplacian: f32,
    /// Edge density (proportion of strong gradient pixels)
    pub edge_density: f32,
    /// Modulation Transfer Function (MTF) proxy estimate
    pub mtf_proxy: f32,
    /// Center-to-corner light falloff in stops
    pub vignetting_stops: f32,
    /// Estimated chromatic aberration fringe width in pixels
    pub chromatic_aberration_px: f32,
}

/// Color science and gamut physics measurements.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct ColorPhysics {
    pub estimated_kelvin: f32,
    pub wb_deviation: f32,
    pub saturation_mean: f32,
    pub palette_entropy: f32,
    pub delta_e_d65: f32,
    pub skin_tone_delta_e: Option<f32>,
    pub gamut_coverage_srgb: f32,
    pub gamut_coverage_p3: f32,
    pub gamut_coverage_rec2020: f32,
    /// Angular separation between highlight and shadow color vectors (0 - 180 deg). ~180 = complementary split-toning
    pub split_toning_separation_deg: f32,
    /// Harmonic color harmony score (0.0 - 100.0) based on complementary color modeling
    pub harmonic_palette_score: f32,
}

/// Combined Objective Physics metrics bundle.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct ObjectivePhysics {
    pub exposure: ExposurePhysics,
    pub optics: OpticalPhysics,
    pub color: ColorPhysics,
}
