//! AESTHETIC Metrics
//!
//! High-performance, multi-threaded pure Rust algorithms for Objective Physics
//! and mathematical frame evaluation.

pub mod color;
pub mod exposure;
pub mod matte;
pub mod optics;

pub use matte::{detect_active_picture, ActiveCropBounds};

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
