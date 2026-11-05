//! Core Analysis Pipeline Coordinator
//!
//! Orchestrates matte detection, 79-metric computation, automatic style discovery,
//! 4-output structuring, and batch video analysis.

use crate::baseline_store::BaselineStore;
use crate::export::{
    export_shot_sidecars_with_frames, generate_cmx3600_edl,
    generate_contact_sheet_html_with_frames, generate_csv_selects, generate_fcpxml,
};
use crate::inference::ModelInferenceEngine;
use crate::video::{
    extract_frame_rgb, extract_frames_burst, extract_trimmed_clip, probe_video_metadata,
};
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
    let is_black_or_credits = physics.exposure.histogram_mean < 14.0
        || physics.exposure.shadow_clip_pct > 78.0
        || physics.exposure.el_zones.zone_0_black_pct > 82.0
        || physics.color.palette_entropy < 1.0;

    let zones = &physics.exposure.false_color_zones;
    let lighting_key = if is_black_or_credits {
        "Black / Credits Leader".to_string()
    } else if zones.highlight_zone_pct > 25.0 || zones.skin_zone_pct > 35.0 {
        "High-Key".to_string()
    } else if zones.black_clip_pct > 15.0 || zones.shadow_zone_pct > 40.0 {
        "Low-Key Chiaroscuro".to_string()
    } else {
        "Mid-Key Naturalistic".to_string()
    };

    let discovered_style = DiscoveredStyle {
        lighting_key,
        // Not measurable from a single frame; populated only when actually measured.
        motion_type: String::new(),
        shot_scale: String::new(),
        cinematographer_match: None,
        match_confidence: 0.0,
        style_family: String::new(),
    };

    // 4. Calculate tangible 0-100 scores using baseline calibration
    let dr_score = dr_quantiles.compute_percentile_score(physics.exposure.dynamic_range_stops);
    let rolloff_score =
        rolloff_quantiles.compute_percentile_score(physics.exposure.highlight_rolloff);
    let sharp_score =
        sharpness_quantiles.compute_percentile_score(physics.optics.sharpness_laplacian);

    let mut technical_score =
        (dr_score * 0.35 + rolloff_score * 0.35 + sharp_score * 0.30).clamp(0.0, 100.0);
    if is_black_or_credits {
        technical_score = (technical_score * 0.20).min(18.0);
    }
    // Creative (craft) and temporal pillars are filled in by `enrich_take` when measured.
    // Until then the overall score reflects only what was actually measured.
    let creative_score = 0.0;
    let temporal_score = 0.0;
    let overall_score = technical_score;

    let mut concerns = Vec::new();
    if is_black_or_credits {
        concerns.push(DiagnosticFlag {
            code: "NON_PHOTOGRAPHIC_OR_CREDITS".to_string(),
            title: "Black Leader or Title/Credits Graphic".to_string(),
            description: format!(
                "Frame is {:.1}% black floor (mean luma {:.1}, entropy {:.2} bits) — deprioritized from hero cinematography selects",
                physics.exposure.el_zones.zone_0_black_pct,
                physics.exposure.histogram_mean,
                physics.color.palette_entropy
            ),
            severity: aesthetic_models::forensics::DiagnosticSeverity::Warning,
            timestamp_sec,
            affected_region: None,
        });
    }
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
            temporal_measured: false,
        },
        style: discovered_style,
        measured: physics,
        concerns,
        craft: None,
        golden_baseline: Vec::new(),
    }
}

/// Enriches a physics-evaluated take with the model-inferred craft layer, the
/// craft (creative) pillar score, and its position inside the measured
/// award-cinema Golden Baseline distribution.
///
/// `frame` must be the same frame the take was measured from. When a second
/// frame (`next_frame`, `dt_sec` later) is supplied, motion dynamics are
/// measured and the temporal pillar becomes a real measurement.
pub fn enrich_take(
    take: &mut ShotTake,
    frame: &RgbImage,
    next_frame: Option<(&RgbImage, f64)>,
    store: &BaselineStore,
    inference: &ModelInferenceEngine,
) {
    let mut craft = inference.infer_craft(frame);

    // Motion is only reported when actually measured between two frames.
    if let Some((next, dt)) = next_frame {
        // Block-matching search window is +/-6 px, so measure on a 480 px-wide proxy
        // to keep realistic camera moves inside the search range.
        let proxy = |img: &RgbImage| -> RgbImage {
            let (w, h) = img.dimensions();
            if w <= 480 {
                return img.clone();
            }
            let nh = ((h as f32) * 480.0 / (w as f32)).round().max(1.0) as u32;
            image::imageops::resize(img, 480, nh, image::imageops::FilterType::Triangle)
        };
        let a = proxy(frame);
        let b = proxy(next);
        let depth = inference.infer_depth(&a);
        craft.motion = crate::inference::compute_motion_dynamics(
            &a,
            &b,
            (dt as f32).max(1e-3),
            Some(&depth),
        );
        let m = &craft.motion;
        // Temporal stability: penalise micro-jitter and judder risk (0-100 scales).
        take.scores.temporal =
            (100.0 - m.micro_jitter_score * 2.0 - m.judder_risk_score * 0.5).clamp(0.0, 100.0);
        take.scores.temporal_measured = true;
        take.style.motion_type = if m.optical_flow_mean < 2.0 {
            "Static".to_string()
        } else if m.camera_motion_ratio >= 0.6 {
            if m.micro_jitter_score > 8.0 {
                "Handheld Camera Move".to_string()
            } else {
                "Smooth Camera Move".to_string()
            }
        } else {
            "Subject Motion".to_string()
        };
    } else {
        craft.motion = Default::default();
    }

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

    let is_non_photographic = take
        .concerns
        .iter()
        .any(|c| c.code == "NON_PHOTOGRAPHIC_OR_CREDITS");
    if is_non_photographic {
        take.scores.creative = (take.scores.creative * 0.20).min(18.0);
    }

    let raw_overall = if take.scores.temporal_measured {
        take.scores.technical * 0.45 + take.scores.creative * 0.35 + take.scores.temporal * 0.20
    } else {
        // Temporal not measured: renormalise over the pillars that were measured.
        (take.scores.technical * 0.45 + take.scores.creative * 0.35) / 0.80
    }
    .clamp(0.0, 100.0);

    take.scores.overall = if is_non_photographic {
        (raw_overall * 0.25).min(18.0)
    } else {
        raw_overall
    };

    // Golden Baseline: where this shot sits inside award cinema.
    take.golden_baseline =
        store.compare_to_golden_baseline(&take.measured, Some(craft.lighting.key_to_fill_ratio));

    // Ancillary tag only: nearest measured award reference or closest master DP signature.
    let emb = inference.infer_embedding(frame);
    if store.measured_shots().len() >= crate::baseline_store::MIN_MEASURED_SHOTS_FOR_CALIBRATION {
        if let Some((shot, sim)) = store.nearest_measured_reference(&emb) {
            take.style.cinematographer_match =
                Some(format!("{} ({})", shot.cinematographer, shot.film_title));
            take.style.match_confidence = (sim * 100.0).clamp(0.0, 100.0);
            take.style.style_family = shot.style_label.clone();
        }
    } else if let Some(m) =
        store.match_master_cinematographer(&emb, craft.lighting.key_to_fill_ratio)
    {
        take.style.cinematographer_match = Some(format!("{} ({})", m.dp_name, m.reference_film));
        take.style.match_confidence = m.visual_similarity.clamp(0.0, 100.0);
        take.style.style_family = m.style_family;
    }

    take.craft = Some(craft);
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
    let (dr_q, rolloff_q, sharp_q, _) = store.scoring_quantiles();

    // Adaptive step scaling: if default 1.0s step is passed on a long video (> 24s),
    // sample ~20 evenly distributed windows across the active program (skipping 3% head/tail leader).
    let effective_step = if (options.sample_step_sec - 1.0).abs() < 1e-4
        && video_info.duration_sec > 24.0
    {
        (video_info.duration_sec * 0.94 / 20.0).max(2.0)
    } else {
        options.sample_step_sec.max(0.5)
    };

    let start_offset = if video_info.duration_sec > 10.0 {
        (video_info.duration_sec * 0.03).min(5.0)
    } else {
        0.0
    };
    let end_limit = if video_info.duration_sec > 10.0 {
        video_info.duration_sec * 0.97
    } else {
        video_info.duration_sec
    };

    let mut candidate_timestamps = Vec::new();
    let mut t = start_offset;
    while t < end_limit {
        candidate_timestamps.push(t);
        t += effective_step;
    }

    let mut takes = Vec::new();
    let mut hero_frames: std::collections::HashMap<String, RgbImage> =
        std::collections::HashMap::new();
    for (idx, &ts) in candidate_timestamps.iter().enumerate() {
        let frames_opt = extract_frames_burst(video_path, ts, 2, 4.0, None)
            .ok()
            .or_else(|| extract_frame_rgb(video_path, ts).ok().map(|f| vec![f]));

        if let Some(frames) = frames_opt {
            if let Some(frame) = frames.first() {
                let take_id = format!("take_{:03}", idx + 1);
                let mut take = evaluate_candidate_frame(
                    frame,
                    &take_id,
                    idx + 1,
                    ts,
                    &dr_q,
                    &rolloff_q,
                    &sharp_q,
                );

                let next_ref = frames.get(1).map(|nf| (nf, 0.25));
                enrich_take(&mut take, frame, next_ref, &store, &inference);

                if take.style.shot_scale.is_empty() {
                    take.style.shot_scale = if take.measured.optics.edge_density > 0.14 {
                        "Wide".to_string()
                    } else if take.measured.optics.vignetting_stops > 0.35 {
                        "Medium Close-Up".to_string()
                    } else {
                        "Medium".to_string()
                    };
                }

                hero_frames.insert(take_id, frame.clone());
                takes.push(take);
            }
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
        let html = generate_contact_sheet_html_with_frames(
            title,
            clip_name,
            &takes,
            options.top_n.unwrap_or(0),
            &hero_frames,
        );
        std::fs::write(cs_path, &html)
            .map_err(|e| format!("Failed to write Contact Sheet: {}", e))?;
        contact_sheet_html = Some(html);
    }

    let mut sidecars_count = 0;
    if let Some(ref sidecars_dir) = options.export_sidecars_dir {
        sidecars_count =
            export_shot_sidecars_with_frames(sidecars_dir, clip_name, &takes, &hero_frames)?;
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
