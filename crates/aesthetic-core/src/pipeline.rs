//! Core Analysis Pipeline Coordinator
//!
//! Orchestrates matte detection, 79-metric computation, automatic style discovery,
//! 4-output structuring, and batch video analysis.

use crate::baseline_store::BaselineStore;
use crate::export::{
    export_shot_sidecars, generate_cmx3600_edl, generate_contact_sheet_html, generate_csv_selects,
    generate_fcpxml,
};
use crate::inference::ModelInferenceEngine;
use crate::video::{extract_frame_rgb, extract_trimmed_clip, probe_video_metadata};
use aesthetic_metrics::compute_objective_physics;
use aesthetic_metrics::matte::detect_active_picture;
use aesthetic_models::baseline::MetricQuantiles;
use aesthetic_models::forensics::DiagnosticFlag;
use aesthetic_models::manifest::VideoSourceInfo;
use aesthetic_models::window::{DiscoveredStyle, PillarScores, ShotTake};
use image::RgbImage;
use std::path::{Path, PathBuf};

/// Configuration options for batch video analysis and selects generation.
#[derive(Debug, Clone)]
pub struct BatchOptions {
    pub min_take_duration_sec: f64,
    pub max_take_duration_sec: f64,
    pub sample_step_sec: f64,
    pub handle_sec: f64,
    pub top_n: Option<usize>,
    pub export_edl_path: Option<PathBuf>,
    pub export_csv_path: Option<PathBuf>,
    pub export_fcpxml_path: Option<PathBuf>,
    pub export_contact_sheet_path: Option<PathBuf>,
    pub export_sidecars_dir: Option<PathBuf>,
    pub export_clips_dir: Option<PathBuf>,
}

impl Default for BatchOptions {
    fn default() -> Self {
        Self {
            min_take_duration_sec: 1.5,
            max_take_duration_sec: 4.0,
            sample_step_sec: 1.0,
            handle_sec: 0.5,
            top_n: None,
            export_edl_path: None,
            export_csv_path: None,
            export_fcpxml_path: None,
            export_contact_sheet_path: None,
            export_sidecars_dir: None,
            export_clips_dir: None,
        }
    }
}

/// The results of a batch video analysis run.
#[derive(Debug, Clone)]
pub struct BatchAnalysisResult {
    pub video_info: VideoSourceInfo,
    pub ranked_takes: Vec<ShotTake>,
    pub edl_content: String,
    pub csv_content: String,
    pub fcpxml_content: Option<String>,
    pub contact_sheet_html: Option<String>,
    pub sidecars_count: usize,
    pub extracted_clips_count: usize,
}

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
        style_family: "Prestige Naturalism".to_string(),
    };

    // 4. Calculate tangible 0-100 scores using baseline calibration
    let dr_score = dr_quantiles.compute_percentile_score(physics.exposure.dynamic_range_stops);
    let rolloff_score =
        rolloff_quantiles.compute_percentile_score(physics.exposure.highlight_rolloff);
    let sharp_score =
        sharpness_quantiles.compute_percentile_score(physics.optics.sharpness_laplacian);

    let technical_score =
        (dr_score * 0.35 + rolloff_score * 0.35 + sharp_score * 0.30).clamp(0.0, 100.0);
    let creative_score = 80.0;
    let temporal_score = 85.0;
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

/// Executes full end-to-end batch analysis on a video file.
pub fn analyze_video_file(
    video_path: &Path,
    options: &BatchOptions,
) -> Result<BatchAnalysisResult, String> {
    let video_info = probe_video_metadata(video_path)?;
    if video_info.duration_sec <= 0.0 {
        return Err("Video has zero or unknown duration".to_string());
    }

    let store = BaselineStore::new();
    let inference = ModelInferenceEngine::new();

    let mut candidate_timestamps = Vec::new();
    let mut t = 0.0;
    while t < video_info.duration_sec {
        candidate_timestamps.push(t);
        t += options.sample_step_sec;
    }

    let mut takes = Vec::new();
    for (idx, &ts) in candidate_timestamps.iter().enumerate() {
        if let Ok(frame) = extract_frame_rgb(video_path, ts) {
            let take_id = format!("take_{:03}", idx + 1);
            let mut take = evaluate_candidate_frame(
                &frame,
                &take_id,
                idx + 1,
                ts,
                &store.manifest.dynamic_range_quantiles,
                &store.manifest.highlight_rolloff_quantiles,
                &store.manifest.sharpness_quantiles,
            );

            // Craft & embedding matching
            let craft = inference.infer_craft(&frame);
            let depth_quality = (craft.staging.depth_separation_score * 0.5
                + craft.staging.silhouette_clarity * 0.5)
                .clamp(0.0, 100.0);
            let color_harmony = take.measured.color.harmonic_palette_score;
            let staging_poise = craft.staging.gaze_poise_score;
            let lighting_quality = ((craft.lighting.catchlight_intensity * 0.20)
                + (craft.lighting.key_to_fill_ratio.min(8.0) / 8.0) * 80.0)
                .clamp(0.0, 100.0);

            take.scores.creative = (depth_quality * 0.25
                + color_harmony * 0.25
                + staging_poise * 0.30
                + lighting_quality * 0.20)
                .clamp(0.0, 100.0);

            let emb = inference.infer_embedding(&frame);
            if let Some(dp) =
                store.match_master_cinematographer(&emb, craft.lighting.key_to_fill_ratio)
            {
                take.style.cinematographer_match =
                    Some(format!("{} ({})", dp.dp_name, dp.reference_film));
                take.style.match_confidence = dp.visual_similarity;
                take.style.style_family = dp.style_family;
                take.scores.creative =
                    (take.scores.creative * 0.70 + dp.visual_similarity * 30.0).clamp(0.0, 100.0);
            }

            take.scores.overall = (take.scores.technical * 0.45
                + take.scores.creative * 0.35
                + take.scores.temporal * 0.20)
                .clamp(0.0, 100.0);

            takes.push(take);
        }
    }

    takes.sort_by(|a, b| {
        b.scores
            .overall
            .partial_cmp(&a.scores.overall)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    if let Some(n) = options.top_n {
        if n > 0 && n < takes.len() {
            takes.truncate(n);
        }
    }

    let title = video_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("AESTHETIC_SELECTS");
    let clip_name = video_path
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("SOURCE.MOV");

    let edl_content = generate_cmx3600_edl(title, clip_name, &takes, video_info.frame_rate);
    let csv_content = generate_csv_selects(clip_name, &takes, video_info.frame_rate);

    if let Some(ref edl_path) = options.export_edl_path {
        std::fs::write(edl_path, &edl_content)
            .map_err(|e| format!("Failed to write EDL: {}", e))?;
    }

    if let Some(ref csv_path) = options.export_csv_path {
        std::fs::write(csv_path, &csv_content)
            .map_err(|e| format!("Failed to write CSV: {}", e))?;
    }

    let mut fcpxml_content = None;
    if let Some(ref fcpxml_path) = options.export_fcpxml_path {
        let xml = generate_fcpxml(
            title,
            &video_path.to_string_lossy(),
            &takes,
            video_info.frame_rate,
        );
        std::fs::write(fcpxml_path, &xml).map_err(|e| format!("Failed to write FCPXML: {}", e))?;
        fcpxml_content = Some(xml);
    }

    let mut contact_sheet_html = None;
    if let Some(ref cs_path) = options.export_contact_sheet_path {
        let html =
            generate_contact_sheet_html(title, clip_name, &takes, options.top_n.unwrap_or(0));
        std::fs::write(cs_path, &html)
            .map_err(|e| format!("Failed to write Contact Sheet: {}", e))?;
        contact_sheet_html = Some(html);
    }

    let mut sidecars_count = 0;
    if let Some(ref sidecars_dir) = options.export_sidecars_dir {
        sidecars_count = export_shot_sidecars(sidecars_dir, clip_name, &takes)?;
    }

    let mut extracted_clips_count = 0;
    if let Some(ref clips_dir) = options.export_clips_dir {
        std::fs::create_dir_all(clips_dir)
            .map_err(|e| format!("Failed to create clips dir: {}", e))?;
        for take in &takes {
            let out_clip_name = format!("{}_{:.1}s.mov", take.take_id, take.start_sec);
            let out_path = clips_dir.join(out_clip_name);
            let start = (take.start_sec - options.handle_sec).max(0.0);
            let duration = take.duration_sec + (options.handle_sec * 2.0);
            if extract_trimmed_clip(video_path, start, duration, &out_path).is_ok() {
                extracted_clips_count += 1;
            }
        }
    }

    Ok(BatchAnalysisResult {
        video_info,
        ranked_takes: takes,
        edl_content,
        csv_content,
        fcpxml_content,
        contact_sheet_html,
        sidecars_count,
        extracted_clips_count,
    })
}
