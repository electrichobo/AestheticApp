//! Core Analysis Pipeline Coordinator
//!
//! Orchestrates matte detection, 79-metric computation, automatic style discovery,
//! and 4-output structuring.

use aesthetic_metrics::compute_objective_physics;
use aesthetic_metrics::matte::detect_active_picture;
use aesthetic_models::baseline::MetricQuantiles;
use aesthetic_models::forensics::DiagnosticFlag;
use aesthetic_models::window::{DiscoveredStyle, PillarScores, ShotTake};
use image::RgbImage;

/// Analyze a single candidate frame and produce a structured 4-output evaluation.
pub fn evaluate_candidate_frame(
    img: &RgbImage,
    take_id: &str,
    scene_idx: usize,
    timestamp_sec: f64,
    dr_quantiles: &MetricQuantiles,
    rolloff_quantiles: &MetricQuantiles,
    sharpness_quantiles: &MetricQuantiles,
) -> ShotTake {
    // 1. Detect active picture area (crop out black letterbox bars)
    let crop = detect_active_picture(img);
    let active_img = if crop.width == img.width() && crop.height == img.height() {
        img.clone()
    } else {
        image::imageops::crop_imm(img, crop.x, crop.y, crop.width, crop.height).to_image()
    };

    // 2. Compute full Objective Physics measurements
    let physics = compute_objective_physics(&active_img);

    // 3. Automatic Lighting Key and Style Discovery
    let zones = &physics.exposure.false_color_zones;
    let lighting_key = if zones.highlight_zone_pct > 25.0 || zones.skin_zone_pct > 35.0 {
        "High-Key".to_string()
    } else if zones.black_clip_pct > 15.0 || zones.shadow_zone_pct > 40.0 {
        "Low-Key Chiaroscuro".to_string()
    } else {
        "Mid-Key Naturalistic".to_string()
    };

    let discovered_style = DiscoveredStyle {
        lighting_key,
        motion_type: "Stable Take".to_string(),
        shot_scale: "Medium".to_string(),
        cinematographer_match: None,
        match_confidence: 0.0,
    };

    // 4. Calculate tangible 0-100 scores using baseline calibration
    let dr_score = dr_quantiles.compute_percentile_score(physics.exposure.dynamic_range_stops);
    let rolloff_score =
        rolloff_quantiles.compute_percentile_score(physics.exposure.highlight_rolloff);
    let sharp_score =
        sharpness_quantiles.compute_percentile_score(physics.optics.sharpness_laplacian);

    let technical_score =
        (dr_score * 0.35 + rolloff_score * 0.35 + sharp_score * 0.30).clamp(0.0, 100.0);
    let creative_score = 80.0; // Baseline similarity proxy until M3 ONNX model wiring
    let temporal_score = 85.0; // Window stability score proxy
    let overall_score = technical_score * 0.50 + creative_score * 0.30 + temporal_score * 0.20;

    let mut concerns = Vec::new();
    if physics.exposure.highlight_clip_pct > 5.0 {
        concerns.push(DiagnosticFlag {
            code: "HIGHLIGHT_CLIPPING".to_string(),
            title: "Specular Highlights Exceeded".to_string(),
            description: format!(
                "Clipped highlight area is {:.1}% of active raster",
                physics.exposure.highlight_clip_pct
            ),
            severity: aesthetic_models::forensics::DiagnosticSeverity::Warning,
            timestamp_sec,
            affected_region: None,
        });
    }

    ShotTake {
        take_id: take_id.to_string(),
        scene_index: scene_idx,
        start_sec: timestamp_sec,
        end_sec: timestamp_sec + 2.5,
        duration_sec: 2.5,
        hero_frame_index: Some(0),
        hero_timestamp_sec: timestamp_sec,
        scores: PillarScores {
            overall: overall_score,
            technical: technical_score,
            creative: creative_score,
            temporal: temporal_score,
        },
        style: discovered_style,
        measured: physics,
        concerns,
    }
}
