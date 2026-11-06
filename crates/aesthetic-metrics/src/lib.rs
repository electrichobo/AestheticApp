//! AESTHETIC Metrics
//!
//! High-performance, multi-threaded pure Rust algorithms for Objective Physics
//! and mathematical frame evaluation.

pub mod color;
pub mod exposure;
pub mod matte;
pub mod optics;
pub mod scopes;

pub use exposure::{
    compute_el_zone_map, compute_frame_pair_psnr_and_ssim, el_zone_color_for_stops,
    luma_to_el_zone_stops,
};
pub use matte::{detect_active_picture, ActiveCropBounds};
pub use scopes::{
    compute_cie_chromaticity_map, compute_histograms, compute_parade, compute_vectorscope,
    compute_waveform, ChannelHistogram, CieChromaticityMap, LumaWaveform, RgbParade, Vectorscope,
};

use aesthetic_models::physics::ObjectivePhysics;
use image::RgbImage;

/// Compute the complete Objective Physics bundle for an RGB image.
pub fn compute_objective_physics(img: &RgbImage) -> ObjectivePhysics {
    let exposure = exposure::analyze_exposure(img);
    let optics = optics::analyze_optics(img);
    let color = color::analyze_color(img);

    ObjectivePhysics {
        exposure,
        optics,
        color,
    }
}
