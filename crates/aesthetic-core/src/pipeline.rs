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
use aesthetic_models::temporal::ReelSequenceMetrics;
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
    pub sequence_metrics: ReelSequenceMetrics,
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
        palette_family: String::new(),
        scene_type: String::new(),
        shot_intent: String::new(),
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
            hero_potency_score: technical_score,
            three_second_impact_score: technical_score,
            authorship_distinctiveness_score: 50.0,
            storytelling_score: technical_score,
            cinematic_technique_score: technical_score,
            memorability_score: technical_score,
        },
        style: discovered_style,
        measured: physics,
        concerns,
        craft: None,
        golden_baseline: Vec::new(),
        rationale_summary: String::new(),
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
        let (psnr_db, ssim_score) = aesthetic_metrics::compute_frame_pair_psnr_and_ssim(&a, &b);
        take.measured.exposure.psnr_db = psnr_db;
        take.measured.exposure.ssim_score = ssim_score;
        let depth = inference.infer_depth(&a);
        craft.motion = crate::inference::compute_motion_dynamics(
            &a,
            &b,
            (dt as f32).max(1e-3),
            Some(&depth),
        );
        let m = &craft.motion;
        // Temporal stability: penalise micro-jitter and judder risk + reward directional motion blur coherence (M19).
        let raw_stability =
            (100.0 - m.micro_jitter_score * 2.0 - m.judder_risk_score * 0.5).clamp(0.0, 100.0);
        take.scores.temporal =
            (raw_stability * 0.80 + m.motion_coherence_score * 0.20).clamp(0.0, 100.0);
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

    // Automatic Palette Family classification & intentionality scoring (M19)
    let cct = take.measured.color.estimated_kelvin;
    let sat = take.measured.color.saturation_mean;
    let split_deg = take.measured.color.split_toning_separation_deg;
    let (palette_family, palette_intent_score) = if sat < 10.0 {
        ("Desaturated Silver / Monochrome", 86.0f32)
    } else if split_deg >= 125.0 && sat >= 16.0 {
        ("Complementary Teal-Orange", 92.0f32)
    } else if cct < 4100.0 {
        ("Warm Tungsten / Amber", 88.0f32)
    } else if cct > 5900.0 {
        ("Cool Cyan / Moonlight", 87.0f32)
    } else if take.measured.exposure.histogram_mean > 0.55 {
        ("High-Key Naturalist", 82.0f32)
    } else {
        ("Natural Daylight", 80.0f32)
    };
    take.style.palette_family = palette_family.to_string();

    // Log-aware CIE 1931 gamut coverage + palette family intentionality integration into color harmony score
    let is_flat_log = detect_flat_log_encoding(&take.measured);
    let gamut_score = if is_flat_log {
        // On ungraded log plates, do not penalize compressed Rec.709 gamut volume before LUT transform
        72.0
    } else {
        (take.measured.color.gamut_coverage_srgb * 1.4
            + take.measured.color.gamut_coverage_p3 * 0.6)
            .clamp(35.0, 100.0)
    };
    let color_harmony = (take.measured.color.harmonic_palette_score * 0.65
        + gamut_score * 0.20
        + palette_intent_score * 0.15)
        .clamp(0.0, 100.0);

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

    // Narrative & Aesthetic Reranker Heads (M18):
    // 1. Hero-Frame Potency: suitability as a representative showreel still/thumbnail
    let clip_penalty =
        (take.measured.exposure.highlight_clip_pct + take.measured.exposure.shadow_clip_pct * 0.5)
            .min(30.0);
    let hero_potency = (craft.focus.subject_focus_accuracy * 0.30
        + staging_poise * 0.25
        + craft.staging.silhouette_clarity * 0.20
        + craft.lighting.catchlight_intensity * 0.15
        + take.scores.technical * 0.20
        - clip_penalty)
        .clamp(0.0, 100.0);

    // 2. Three-Second Impact: immediate visual authority in the opening 3 seconds
    let dr_norm = ((take.measured.exposure.dynamic_range_stops / 11.5) * 100.0).clamp(0.0, 100.0);
    let split_norm =
        ((take.measured.color.split_toning_separation_deg / 150.0) * 100.0).clamp(0.0, 100.0);
    let motion_settle = if take.scores.temporal_measured {
        take.scores.temporal
    } else {
        80.0
    };
    let three_sec_impact = (dr_norm * 0.30
        + lighting_quality * 0.25
        + split_norm * 0.20
        + motion_settle * 0.25)
        .clamp(0.0, 100.0);

    // 3. Authorship & Distinctiveness: intentional visual signature strength
    let entropy_norm = ((take.measured.color.palette_entropy / 4.2) * 100.0).clamp(0.0, 100.0);
    let authorship = (depth_quality * 0.35
        + lighting_quality * 0.35
        + entropy_norm * 0.15
        + split_norm * 0.15)
        .clamp(0.0, 100.0);

    // 4. Visual Storytelling Effectiveness (M19): multi-plane staging, lead room, and lighting motivation
    let plane_bonus = ((craft.staging.depth_plane_count as f32).min(4.0) / 4.0) * 100.0;
    let storytelling = (craft.staging.looking_room_score * 0.30
        + craft.staging.depth_separation_score * 0.25
        + plane_bonus * 0.15
        + lighting_quality * 0.30)
        .clamp(0.0, 100.0);

    // 5. Cinematic Technique Quality (M19): camera control, motion coherence, bokeh isolation, and roll-off
    let motion_tech = if take.scores.temporal_measured {
        (take.scores.temporal * 0.60 + craft.motion.motion_coherence_score * 0.40).clamp(0.0, 100.0)
    } else {
        take.scores.technical
    };
    let cinematic_technique = (craft.focus.subject_focus_accuracy * 0.30
        + take.measured.exposure.highlight_rolloff * 0.25
        + motion_tech * 0.25
        + craft.lighting.rim_light_separation * 0.20)
        .clamp(0.0, 100.0);

    // 6. Visual Memorability (M19): focal saliency concentration, chromatic/tonal contrast, and signature poise
    let memorability = (hero_potency * 0.35
        + three_sec_impact * 0.35
        + authorship * 0.30)
        .clamp(0.0, 100.0);

    if is_non_photographic {
        take.scores.hero_potency_score = (hero_potency * 0.20).min(15.0);
        take.scores.three_second_impact_score = (three_sec_impact * 0.20).min(15.0);
        take.scores.authorship_distinctiveness_score = (authorship * 0.20).min(15.0);
        take.scores.storytelling_score = (storytelling * 0.20).min(15.0);
        take.scores.cinematic_technique_score = (cinematic_technique * 0.20).min(15.0);
        take.scores.memorability_score = (memorability * 0.20).min(15.0);
    } else {
        take.scores.hero_potency_score = hero_potency;
        take.scores.three_second_impact_score = three_sec_impact;
        take.scores.authorship_distinctiveness_score = authorship;
        take.scores.storytelling_score = storytelling;
        take.scores.cinematic_technique_score = cinematic_technique;
        take.scores.memorability_score = memorability;
    }

    // Ancillary tag only: nearest measured award reference or closest master DP signature.
    let emb = inference.infer_embedding(frame);
    if store.measured_shots().len() >= crate::baseline_store::MIN_MEASURED_SHOTS_FOR_CALIBRATION {
        if let Some((shot, sim)) = store.nearest_measured_reference_with_craft(
            &emb,
            take.measured.exposure.dynamic_range_stops,
            take.measured.optics.sharpness_laplacian,
            craft.lighting.key_to_fill_ratio,
        ) {
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

    // Golden Baseline (M15): global award-cinema percentiles + within-style-cluster percentiles + motion velocity.
    let measured_flow = if take.scores.temporal_measured {
        Some(craft.motion.optical_flow_mean)
    } else {
        None
    };
    take.golden_baseline = store.compare_to_golden_baseline_with_style(
        &take.measured,
        Some(craft.lighting.key_to_fill_ratio),
        Some(take.style.style_family.as_str()),
        measured_flow,
    );

    // Automatic Shot Scale classification from Z-plane focus isolation, depth planes,
    // specular catchlights, and spatial edge density.
    if take.style.shot_scale.is_empty() {
        let focus_acc = craft.focus.subject_focus_accuracy;
        let depth_sep = craft.staging.depth_separation_score;
        let catch = craft.lighting.catchlight_intensity;
        let edge_d = take.measured.optics.edge_density;

        take.style.shot_scale = if (depth_sep >= 52.0 && focus_acc >= 68.0)
            || (depth_sep >= 38.0 && catch > 65.0)
        {
            "Close-Up".to_string()
        } else if depth_sep >= 34.0
            || focus_acc >= 64.0
            || take.measured.optics.vignetting_stops > 0.38
        {
            "Medium Close-Up".to_string()
        } else if edge_d > 0.14 || depth_sep < 22.0 {
            "Wide".to_string()
        } else {
            "Medium".to_string()
        };
    }

    // Multi-signal Scene Type & Shot Intent classification (M19)
    if take.style.scene_type.is_empty() {
        let mut ext_votes = 0i32;
        let mut int_votes = 0i32;
        if cct > 5600.0 {
            ext_votes += 2;
        } else if cct < 4100.0 {
            int_votes += 2;
        }
        if take.measured.exposure.dynamic_range_stops > 10.6 {
            ext_votes += 2;
        } else if take.measured.exposure.dynamic_range_stops < 8.5 {
            int_votes += 1;
        }
        if sat > 22.0 && take.measured.exposure.histogram_mean > 0.42 {
            ext_votes += 1;
        }
        take.style.scene_type = if take.measured.exposure.histogram_mean < 0.22 {
            "Night / Low-Key".to_string()
        } else if ext_votes > int_votes {
            "Exterior Daylight".to_string()
        } else if int_votes > ext_votes {
            "Interior Warm / Practical".to_string()
        } else {
            "Controlled Studio / Stage".to_string()
        };
    }

    if take.style.shot_intent.is_empty() {
        take.style.shot_intent = if take.style.shot_scale.contains("Close-Up") {
            "Intimate Character".to_string()
        } else if take.style.shot_scale == "Wide" {
            "Establishing / Architectural".to_string()
        } else if craft.motion.optical_flow_mean > 14.0 {
            "Kinetic Action".to_string()
        } else if craft.staging.face_count > 0 {
            "Dialogue / Staging".to_string()
        } else {
            "Atmospheric / Transitional".to_string()
        };
    }

    // Flat / ungraded log signal check (pixel-level milk-gray floor + compressed midtone std + low saturation)
    if !is_non_photographic && detect_flat_log_encoding(&take.measured) {
        let already_flagged = take.concerns.iter().any(|c| c.code == "LOG_ENCODED_SIGNAL");
        if !already_flagged {
            take.concerns.push(DiagnosticFlag {
                code: "LOG_ENCODED_SIGNAL".to_string(),
                title: "Camera Log / Flat Transfer Profile Suspected".to_string(),
                description: format!(
                    "Compressed tonal std ({:.1}) with elevated black floor (Zone 0 {:.1}%) and low saturation ({:.1}) indicates ungraded log footage; ΔE2000 & contrast reflect ungraded plate",
                    take.measured.exposure.histogram_std,
                    take.measured.exposure.el_zones.zone_0_black_pct,
                    take.measured.color.saturation_mean
                ),
                severity: aesthetic_models::forensics::DiagnosticSeverity::Info,
                timestamp_sec: take.hero_timestamp_sec,
                affected_region: None,
            });
        }
    }

    // M16 Forensic Diagnostics: Subtitle / lower-third burn-in & Rolling-shutter skew risk
    if !is_non_photographic
        && detect_subtitle_or_lower_third_burnin(frame)
        && !take
            .concerns
            .iter()
            .any(|c| c.code == "SUBTITLE_OR_LOWER_THIRD_BURNIN")
    {
        take.concerns.push(DiagnosticFlag {
            code: "SUBTITLE_OR_LOWER_THIRD_BURNIN".to_string(),
            title: "Subtitle or Lower-Third Graphic Detected".to_string(),
            description: "High-contrast sharp horizontal glyph edges detected in lower 18% of raster (burned-in captions or broadcast chyron)".to_string(),
            severity: aesthetic_models::forensics::DiagnosticSeverity::Info,
            timestamp_sec: take.hero_timestamp_sec,
            affected_region: None,
        });
    }

    if take.scores.temporal_measured
        && craft.motion.optical_flow_mean > 14.0
        && craft.motion.micro_jitter_score > 11.0
        && !take
            .concerns
            .iter()
            .any(|c| c.code == "ROLLING_SHUTTER_SKEW_RISK")
    {
        take.concerns.push(DiagnosticFlag {
            code: "ROLLING_SHUTTER_SKEW_RISK".to_string(),
            title: "Rolling Shutter Skew / Whip-Pan Wobble Risk".to_string(),
            description: format!(
                "High optical flow velocity ({:.1} px/f) combined with elevated spatial micro-jitter ({:.1}) indicates CMOS rolling-shutter skew risk",
                craft.motion.optical_flow_mean,
                craft.motion.micro_jitter_score
            ),
            severity: aesthetic_models::forensics::DiagnosticSeverity::Warning,
            timestamp_sec: take.hero_timestamp_sec,
            affected_region: None,
        });
    }

    take.craft = Some(craft);
    take.rationale_summary = generate_cinematographic_rationale(take);
}

/// Generates a deterministic, data-backed DP & Editorial rationale paragraph explaining why
/// the candidate take was ranked where it is relative to the Award-Winning Cinema Golden Baseline (M20).
pub fn generate_cinematographic_rationale(take: &ShotTake) -> String {
    if take
        .concerns
        .iter()
        .any(|c| c.code == "NON_PHOTOGRAPHIC_OR_CREDITS")
    {
        return format!(
            "Non-photographic black leader or title/credits card ({:.1}% Zone 0 black floor, entropy {:.2} bits); automatically deprioritized from hero cinematography selects.",
            take.measured.exposure.el_zones.zone_0_black_pct,
            take.measured.color.palette_entropy
        );
    }

    let scale = if take.style.shot_scale.is_empty() {
        "Medium"
    } else {
        take.style.shot_scale.as_str()
    };
    let intent = if take.style.shot_intent.is_empty() {
        "Narrative Setup"
    } else {
        take.style.shot_intent.as_str()
    };
    let scene_env = if take.style.scene_type.is_empty() {
        "Controlled Lighting"
    } else {
        take.style.scene_type.as_str()
    };
    let motion_label = if take.style.motion_type.is_empty() {
        "Static"
    } else {
        take.style.motion_type.as_str()
    };

    let dr = take.measured.exposure.dynamic_range_stops;
    let rolloff = take.measured.exposure.highlight_rolloff;
    let cct = take.measured.color.estimated_kelvin;
    let palette = if take.style.palette_family.is_empty() {
        "Natural Daylight"
    } else {
        take.style.palette_family.as_str()
    };

    let (kf, poise, depth_planes, focus_acc) = if let Some(ref c) = take.craft {
        (
            c.lighting.key_to_fill_ratio,
            c.staging.gaze_poise_score,
            c.staging.depth_plane_count,
            c.focus.subject_focus_accuracy,
        )
    } else {
        (2.5, 75.0, 2, 75.0)
    };

    let ref_note = take
        .style
        .cinematographer_match
        .as_deref()
        .unwrap_or("Award-Winning Cinema Baseline");

    format!(
        "{} ({}, {:.1}s {}) exhibiting {:.1} stops dynamic range ({:.0}% highlight roll-off) and {:.1}:1 {} lighting contrast. Chromatic profile anchored in {} ({:.0}K) with {}-plane Z-depth separation (focus isolation {:.0}/100, eyeline poise {:.0}/100). Nearest measured reference affinity: {} [{}].",
        scale,
        intent,
        take.duration_sec.max(1.5),
        motion_label,
        dr,
        rolloff,
        kf,
        take.style.lighting_key,
        palette,
        cct,
        depth_planes.max(1),
        focus_acc,
        poise,
        ref_note,
        scene_env
    )
}

/// Heuristic detector for ungraded camera log plates when container transfer tags are stripped.
pub fn detect_flat_log_encoding(physics: &aesthetic_models::physics::ObjectivePhysics) -> bool {
    let exp = &physics.exposure;
    let col = &physics.color;
    exp.shadow_clip_pct < 0.05
        && exp.highlight_clip_pct < 0.05
        && exp.el_zones.zone_0_black_pct < 0.25
        && exp.el_zones.zone_1_purple_pct < 1.5
        && exp.histogram_mean >= 75.0
        && exp.histogram_mean <= 162.0
        && exp.histogram_std < 25.0
        && col.saturation_mean < 12.5
}

/// Detects burned-in subtitles or broadcast lower-third graphics in the bottom 18% of the frame.
pub fn detect_subtitle_or_lower_third_burnin(img: &RgbImage) -> bool {
    let (w, h) = img.dimensions();
    if w < 160 || h < 90 {
        return false;
    }
    let x_start = w / 5;
    let x_end = (w * 4) / 5;
    let y_mid_start = h / 4;
    let y_mid_end = (h * 3) / 4;
    let y_low_start = (h * 82) / 100;
    let y_low_end = (h * 96) / 100;

    let mut mid_edges = 0usize;
    let mut mid_samples = 0usize;
    for y in (y_mid_start..y_mid_end).step_by(3) {
        for x in (x_start..x_end.saturating_sub(2)).step_by(3) {
            let p0 = img.get_pixel(x, y);
            let p1 = img.get_pixel(x + 2, y);
            let l0 = 0.2126 * p0[0] as f32 + 0.7152 * p0[1] as f32 + 0.0722 * p0[2] as f32;
            let l1 = 0.2126 * p1[0] as f32 + 0.7152 * p1[1] as f32 + 0.0722 * p1[2] as f32;
            if (l0 - l1).abs() > 75.0 {
                mid_edges += 1;
            }
            mid_samples += 1;
        }
    }

    let mut low_edges = 0usize;
    let mut bright_glyphs = 0usize;
    let mut low_samples = 0usize;
    for y in (y_low_start..y_low_end).step_by(2) {
        for x in (x_start..x_end.saturating_sub(2)).step_by(2) {
            let p0 = img.get_pixel(x, y);
            let p1 = img.get_pixel(x + 2, y);
            let l0 = 0.2126 * p0[0] as f32 + 0.7152 * p0[1] as f32 + 0.0722 * p0[2] as f32;
            let l1 = 0.2126 * p1[0] as f32 + 0.7152 * p1[1] as f32 + 0.0722 * p1[2] as f32;
            if (l0 - l1).abs() > 85.0 && (l0 > 225.0 || l1 > 225.0) {
                low_edges += 1;
            }
            if l0 > 235.0 {
                bright_glyphs += 1;
            }
            low_samples += 1;
        }
    }

    if low_samples == 0 || mid_samples == 0 {
        return false;
    }
    let mid_density = mid_edges as f32 / mid_samples as f32;
    let low_density = low_edges as f32 / low_samples as f32;
    let glyph_pct = bright_glyphs as f32 / low_samples as f32;

    low_density > 0.045 && low_density > (mid_density * 3.2).max(0.04) && glyph_pct > 0.015 && glyph_pct < 0.28
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
    // sample ~26 evenly distributed windows across the active program (skipping 3% head/tail leader).
    let effective_step = if (options.sample_step_sec - 1.0).abs() < 1e-4
        && video_info.duration_sec > 24.0
    {
        (video_info.duration_sec * 0.94 / 26.0).max(2.0)
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

    let mut takes: Vec<ShotTake> = Vec::new();
    let mut hero_frames: std::collections::HashMap<String, RgbImage> =
        std::collections::HashMap::new();
    let mut prev_setup_frame: Option<(RgbImage, f64, f64)> = None; // (last_frame, setup_start_sec, setup_end_sec)
    let mut setup_counter = 0usize;

    for &ts in &candidate_timestamps {
        let frames_opt = extract_frames_burst(video_path, ts, 3, 4.0, None)
            .ok()
            .or_else(|| extract_frame_rgb(video_path, ts).ok().map(|f| vec![f]));

        if let Some(frames) = frames_opt {
            if frames.is_empty() {
                continue;
            }
            // Cut-aware pair selection within the 3-frame burst (0.25s spacing):
            // If a hard cut occurs between frames[0] and frames[1], step past the cut to (frames[1], frames[2]).
            let (frame, next_ref, eff_ts) = if frames.len() >= 3 {
                let d01 = crate::scene::compute_frame_difference(&frames[0], &frames[1]);
                let d12 = crate::scene::compute_frame_difference(&frames[1], &frames[2]);
                if d01 > 26.0 && d12 <= 26.0 {
                    (&frames[1], Some((&frames[2], 0.25)), ts + 0.25)
                } else if d01 <= 26.0 {
                    (&frames[0], Some((&frames[1], 0.25)), ts)
                } else {
                    (&frames[0], None, ts)
                }
            } else if frames.len() == 2 {
                let d01 = crate::scene::compute_frame_difference(&frames[0], &frames[1]);
                if d01 <= 26.0 {
                    (&frames[0], Some((&frames[1], 0.25)), ts)
                } else {
                    (&frames[0], None, ts)
                }
            } else {
                (&frames[0], None, ts)
            };

            // Check if this sample belongs to the same continuous camera setup as the previous take
            let same_setup = if let Some((ref prev_img, _, _)) = prev_setup_frame {
                crate::scene::compute_frame_difference(prev_img, frame) < 10.5
            } else {
                false
            };

            let temp_id = format!("take_{:03}", setup_counter + 1);
            let mut candidate = evaluate_candidate_frame(
                frame,
                &temp_id,
                setup_counter + 1,
                eff_ts,
                &dr_q,
                &rolloff_q,
                &sharp_q,
            );
            enrich_take(&mut candidate, frame, next_ref, &store, &inference);

            // M16 Forensic Diagnostic: Practical light flicker across 3-frame burst within same setup
            if frames.len() >= 3
                && detect_burst_light_flicker(&frames[0], &frames[1], &frames[2])
                && !candidate
                    .concerns
                    .iter()
                    .any(|c| c.code == "PRACTICAL_LIGHT_FLICKER")
            {
                candidate.concerns.push(DiagnosticFlag {
                    code: "PRACTICAL_LIGHT_FLICKER".to_string(),
                    title: "Practical Light / Mains Flicker Detected".to_string(),
                    description: "Alternating mean luminance oscillation across consecutive burst frames indicates PWM or mains practical light flicker".to_string(),
                    severity: aesthetic_models::forensics::DiagnosticSeverity::Warning,
                    timestamp_sec: eff_ts,
                    affected_region: None,
                });
            }

            if same_setup && !takes.is_empty() {
                let (_, setup_start, _) = prev_setup_frame.take().unwrap();
                let setup_end = (eff_ts + options.min_take_duration_sec).min(video_info.duration_sec);
                let prev_take = takes.last_mut().unwrap();
                let existing_id = prev_take.take_id.clone();
                let existing_scene = prev_take.scene_index;

                // Keep the higher-scoring hero moment within this continuous camera setup
                if candidate.scores.overall > prev_take.scores.overall {
                    candidate.take_id = existing_id.clone();
                    candidate.scene_index = existing_scene;
                    let win_dur = (setup_end - setup_start)
                        .clamp(options.min_take_duration_sec, options.max_take_duration_sec);
                    let win_start = (eff_ts - win_dur * 0.35)
                        .max(setup_start)
                        .min((setup_end - win_dur).max(setup_start));
                    candidate.start_sec = win_start;
                    candidate.end_sec = win_start + win_dur;
                    candidate.duration_sec = win_dur;
                    candidate.hero_timestamp_sec = eff_ts;
                    *prev_take = candidate;
                    hero_frames.insert(existing_id, frame.clone());
                } else {
                    let win_dur = (setup_end - setup_start)
                        .clamp(options.min_take_duration_sec, options.max_take_duration_sec);
                    let hero_t = prev_take.hero_timestamp_sec;
                    let win_start = (hero_t - win_dur * 0.35)
                        .max(setup_start)
                        .min((setup_end - win_dur).max(setup_start));
                    prev_take.start_sec = win_start;
                    prev_take.end_sec = win_start + win_dur;
                    prev_take.duration_sec = win_dur;
                }
                prev_setup_frame = Some((frame.clone(), setup_start, setup_end));
            } else {
                setup_counter += 1;
                let take_id = format!("take_{:03}", setup_counter);
                candidate.take_id = take_id.clone();
                candidate.scene_index = setup_counter;
                let setup_end = (eff_ts + 2.5).min(video_info.duration_sec);
                candidate.start_sec = eff_ts;
                candidate.end_sec = setup_end;
                candidate.duration_sec = (setup_end - eff_ts).max(options.min_take_duration_sec);
                hero_frames.insert(take_id, frame.clone());
                takes.push(candidate);
                prev_setup_frame = Some((frame.clone(), eff_ts, setup_end));
            }
        }
    }

    // Propagate container-level Log/HDR transfer characteristic flag if present
    let (meta_is_log, ref meta_curve_label) = video_info.classify_transfer_curve();
    if meta_is_log {
        for take in &mut takes {
            if !take.concerns.iter().any(|c| c.code == "LOG_ENCODED_SIGNAL") {
                take.concerns.push(DiagnosticFlag {
                    code: "LOG_ENCODED_SIGNAL".to_string(),
                    title: format!("Container Transfer: {}", meta_curve_label),
                    description: format!(
                        "Stream metadata specifies '{}' transfer characteristic; ΔE2000 & Rec.709 contrast assume display-referred transform",
                        meta_curve_label
                    ),
                    severity: aesthetic_models::forensics::DiagnosticSeverity::Info,
                    timestamp_sec: take.hero_timestamp_sec,
                    affected_region: None,
                });
            }
        }
    }

    // Apply Maximal Marginal Relevance (MMR) reel diversity ranking so recurring setups
    // do not crowd out distinct camera angles and shot scales in the Top-N selects.
    apply_reel_diversity_ranking(&mut takes);

    if let Some(n) = options.top_n {
        if n > 0 && n < takes.len() {
            takes.truncate(n);
        }
    }

    let sequence_metrics = compute_reel_sequence_metrics(&takes, &video_info);

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
        if let Some(parent) = edl_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        std::fs::write(edl_path, &edl_content)
            .map_err(|e| format!("Failed to write EDL: {}", e))?;
    }

    if let Some(ref csv_path) = options.export_csv_path {
        if let Some(parent) = csv_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        std::fs::write(csv_path, &csv_content)
            .map_err(|e| format!("Failed to write CSV: {}", e))?;
    }

    let mut fcpxml_content = None;
    if let Some(ref fcpxml_path) = options.export_fcpxml_path {
        if let Some(parent) = fcpxml_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
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
        if let Some(parent) = cs_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
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
        sequence_metrics,
        edl_content,
        csv_content,
        fcpxml_content,
        contact_sheet_html,
        sidecars_count,
        extracted_clips_count,
    })
}

/// Greedily orders photographic candidate takes by Maximal Marginal Relevance (MMR),
/// gently penalizing near-duplicate recurring camera setups so the Top-N hero selects
/// represent a diverse spread of shot scales, lighting keys, and visual compositions.
pub fn apply_reel_diversity_ranking(takes: &mut Vec<ShotTake>) {
    if takes.len() <= 2 {
        takes.sort_by(|a, b| {
            b.scores
                .overall
                .partial_cmp(&a.scores.overall)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        return;
    }

    // Separate photographic takes from black/credits leaders
    let mut photo_pool: Vec<ShotTake> = Vec::new();
    let mut leader_pool: Vec<ShotTake> = Vec::new();
    for t in takes.drain(..) {
        if t.concerns
            .iter()
            .any(|c| c.code == "NON_PHOTOGRAPHIC_OR_CREDITS")
        {
            leader_pool.push(t);
        } else {
            photo_pool.push(t);
        }
    }

    photo_pool.sort_by(|a, b| {
        b.scores
            .overall
            .partial_cmp(&a.scores.overall)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    leader_pool.sort_by(|a, b| {
        b.scores
            .overall
            .partial_cmp(&a.scores.overall)
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let mut selected: Vec<ShotTake> = Vec::with_capacity(photo_pool.len());
    if !photo_pool.is_empty() {
        selected.push(photo_pool.remove(0));
    }

    while !photo_pool.is_empty() {
        let mut best_idx = 0usize;
        let mut best_mmr = f32::NEG_INFINITY;

        for (idx, cand) in photo_pool.iter().enumerate() {
            let mut max_redundancy = 0.0f32;
            for sel in &selected {
                let dr_diff = (cand.measured.exposure.dynamic_range_stops
                    - sel.measured.exposure.dynamic_range_stops)
                    .abs();
                let luma_diff =
                    (cand.measured.exposure.histogram_mean - sel.measured.exposure.histogram_mean)
                        .abs();
                let cct_diff = (cand.measured.color.estimated_kelvin
                    - sel.measured.color.estimated_kelvin)
                    .abs();
                let same_key = cand.style.lighting_key == sel.style.lighting_key;
                let same_scale = cand.style.shot_scale == sel.style.shot_scale;
                let same_ref = cand.style.cinematographer_match == sel.style.cinematographer_match;

                // Measure setup similarity (0.0 = completely distinct, 1.0 = near-identical setup)
                let mut sim = (-0.35 * dr_diff - 0.04 * luma_diff - 0.001 * cct_diff).exp();
                if same_key {
                    sim += 0.12;
                }
                if same_scale {
                    sim += 0.12;
                }
                if same_ref {
                    sim += 0.15;
                }
                max_redundancy = max_redundancy.max(sim.clamp(0.0, 1.0));
            }

            // Up to 7.5-point MMR penalty for redundant recurring setups + learned feedback preference boost (M19)
            let pref_boost = compute_feedback_preference_boost(cand);
            let mmr_score = cand.scores.overall + pref_boost - 7.5 * max_redundancy;
            if mmr_score > best_mmr {
                best_mmr = mmr_score;
                best_idx = idx;
            }
        }

        selected.push(photo_pool.remove(best_idx));
    }

    selected.extend(leader_pool);
    *takes = selected;
}

/// Computes cross-shot sequence continuity, grading uniformity, visual fatigue across cuts,
/// and reel diversity across the selected photographic takes (M14).
pub fn compute_reel_sequence_metrics(
    takes: &[ShotTake],
    video_info: &VideoSourceInfo,
) -> ReelSequenceMetrics {
    let (meta_log, curve_label) = video_info.classify_transfer_curve();
    let photo_takes: Vec<&ShotTake> = takes
        .iter()
        .filter(|t| {
            !t.concerns
                .iter()
                .any(|c| c.code == "NON_PHOTOGRAPHIC_OR_CREDITS")
        })
        .collect();

    let any_pixel_log = photo_takes
        .iter()
        .any(|t| t.concerns.iter().any(|c| c.code == "LOG_ENCODED_SIGNAL"));
    let is_log_or_hdr = meta_log || any_pixel_log;
    let transfer_curve_label = if !meta_log && any_pixel_log {
        "Camera Log / Flat Transfer (Pixel-Inferred)".to_string()
    } else {
        curve_label
    };

    if photo_takes.is_empty() {
        return ReelSequenceMetrics {
            is_log_or_hdr,
            transfer_curve_label,
            ..Default::default()
        };
    }

    let n = photo_takes.len() as f32;
    let std_dev = |vals: &[f32]| -> f32 {
        if vals.len() <= 1 {
            return 0.0;
        }
        let mean = vals.iter().sum::<f32>() / (vals.len() as f32);
        let var = vals.iter().map(|v| (v - mean).powi(2)).sum::<f32>() / (vals.len() as f32);
        var.sqrt()
    };

    let wb_vals: Vec<f32> = photo_takes
        .iter()
        .map(|t| t.measured.color.wb_deviation)
        .collect();
    let cct_vals: Vec<f32> = photo_takes
        .iter()
        .map(|t| t.measured.color.estimated_kelvin)
        .collect();
    let luma_vals: Vec<f32> = photo_takes
        .iter()
        .map(|t| t.measured.exposure.histogram_mean)
        .collect();
    let dr_vals: Vec<f32> = photo_takes
        .iter()
        .map(|t| t.measured.exposure.dynamic_range_stops)
        .collect();
    let kf_vals: Vec<f32> = photo_takes
        .iter()
        .map(|t| {
            t.craft
                .as_ref()
                .map(|c| c.lighting.key_to_fill_ratio)
                .unwrap_or(2.5)
        })
        .collect();

    let wb_cross_scene_std = std_dev(&wb_vals);
    let color_temp_cross_scene_std = std_dev(&cct_vals);
    let exposure_consistency_std = std_dev(&luma_vals);
    let dr_std = std_dev(&dr_vals);
    let kf_std = std_dev(&kf_vals);

    let coverage_consistency_score =
        (100.0 - dr_std * 11.0 - kf_std * 6.5 - exposure_consistency_std * 0.45).clamp(0.0, 100.0);
    let grading_uniformity_score = (100.0
        - wb_cross_scene_std * 3.2
        - (color_temp_cross_scene_std / 35.0)
        - exposure_consistency_std * 0.55)
        .clamp(0.0, 100.0);

    // Visual Fatigue Index across consecutive timeline cuts (ordered chronologically)
    let mut chrono = photo_takes.clone();
    chrono.sort_by(|a, b| {
        a.start_sec
            .partial_cmp(&b.start_sec)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    let mut cut_jump_sum = 0.0f32;
    if chrono.len() > 1 {
        for pair in chrono.windows(2) {
            let a = pair[0];
            let b = pair[1];
            let luma_jump =
                (a.measured.exposure.histogram_mean - b.measured.exposure.histogram_mean).abs()
                    / 255.0;
            let com_jump = match (&a.craft, &b.craft) {
                (Some(ca), Some(cb)) => {
                    let dx = (ca.staging.gaze_vector_x.unwrap_or(0.0)
                        - cb.staging.gaze_vector_x.unwrap_or(0.0))
                        * 0.5;
                    let dy = (ca.staging.gaze_vector_y.unwrap_or(0.0)
                        - cb.staging.gaze_vector_y.unwrap_or(0.0))
                        * 0.5;
                    (dx * dx + dy * dy).sqrt()
                }
                _ => 0.15,
            };
            cut_jump_sum += (luma_jump * 55.0 + com_jump * 45.0).clamp(0.0, 100.0);
        }
    }
    let visual_fatigue_index = if chrono.len() > 1 {
        (cut_jump_sum / ((chrono.len() - 1) as f32)).clamp(0.0, 100.0)
    } else {
        12.0
    };

    // Reel Diversity Score: rewards variety of shot scales, lighting keys, and reference matches
    let mut unique_scales: Vec<&str> = photo_takes
        .iter()
        .map(|t| t.style.shot_scale.as_str())
        .collect();
    unique_scales.sort_unstable();
    unique_scales.dedup();

    let mut unique_keys: Vec<&str> = photo_takes
        .iter()
        .map(|t| t.style.lighting_key.as_str())
        .collect();
    unique_keys.sort_unstable();
    unique_keys.dedup();

    let mut unique_refs: Vec<&str> = photo_takes
        .iter()
        .filter_map(|t| t.style.cinematographer_match.as_deref())
        .collect();
    unique_refs.sort_unstable();
    unique_refs.dedup();

    let scale_factor = (unique_scales.len() as f32 / 3.0).min(1.0) * 35.0;
    let key_factor = (unique_keys.len() as f32 / 2.0).min(1.0) * 25.0;
    let ref_factor = (unique_refs.len() as f32 / n.max(1.0)).min(1.0) * 40.0;
    let reel_diversity_score = (scale_factor + key_factor + ref_factor).clamp(0.0, 100.0);

    ReelSequenceMetrics {
        wb_cross_scene_std,
        color_temp_cross_scene_std,
        exposure_consistency_std,
        coverage_consistency_score,
        grading_uniformity_score,
        visual_fatigue_index,
        reel_diversity_score,
        is_log_or_hdr,
        transfer_curve_label,
    }
}

/// Detects alternating luminance oscillation across a 3-frame burst within the same camera setup.
pub fn detect_burst_light_flicker(f0: &RgbImage, f1: &RgbImage, f2: &RgbImage) -> bool {
    let d01 = crate::scene::compute_frame_difference(f0, f1);
    let d12 = crate::scene::compute_frame_difference(f1, f2);
    if d01 > 18.0 || d12 > 18.0 {
        return false; // Cut or heavy camera move
    }

    let mean_luma = |img: &RgbImage| -> f32 {
        let (w, h) = img.dimensions();
        if w == 0 || h == 0 {
            return 0.0;
        }
        let mut sum = 0.0f64;
        let mut count = 0usize;
        for y in (0..h).step_by(8) {
            for x in (0..w).step_by(8) {
                let p = img.get_pixel(x, y);
                sum += (0.2126 * p[0] as f32 + 0.7152 * p[1] as f32 + 0.0722 * p[2] as f32) as f64;
                count += 1;
            }
        }
        if count > 0 {
            (sum / count as f64) as f32
        } else {
            0.0
        }
    };

    let m0 = mean_luma(f0);
    let m1 = mean_luma(f1);
    let m2 = mean_luma(f2);
    let delta01 = m1 - m0;
    let delta12 = m2 - m1;

    // Opposite-sign luminance swing of > 3.5 luma units in both steps
    delta01.abs() > 3.5 && delta12.abs() > 3.5 && (delta01 * delta12) < -12.0
}

/// Appends a user select curation feedback event (`promote_hero`, `pin_select`, `reject_take`, `trim_handles`)
/// to `assets/feedback/events.jsonl` so subsequent reranking adapts to the creator's preferences (M19).
pub fn log_select_feedback_event(
    event: &aesthetic_models::window::SelectFeedbackEvent,
) -> Result<usize, String> {
    use std::io::Write;
    let feedback_dir = Path::new("assets/feedback");
    std::fs::create_dir_all(feedback_dir)
        .map_err(|e| format!("Failed to create feedback directory: {}", e))?;
    let file_path = feedback_dir.join("events.jsonl");
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&file_path)
        .map_err(|e| format!("Failed to open feedback log: {}", e))?;
    let line = serde_json::to_string(event)
        .map_err(|e| format!("Failed to serialize feedback event: {}", e))?;
    writeln!(file, "{}", line).map_err(|e| format!("Failed to write feedback event: {}", e))?;

    let content = std::fs::read_to_string(&file_path).unwrap_or_default();
    Ok(content.lines().filter(|l| !l.trim().is_empty()).count())
}

/// Objective focus for smart showreel assembly optimization (M26).
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum ShowreelObjective {
    /// Maximizes dynamic range latitude, contrast diversity, and exposure craftsmanship
    CommercialLighting,
    /// Maximizes close-up eyeline poise, depth plane separation, and narrative storytelling
    DramaticNarrative,
    /// Maximizes optical flow coherence, camera motion retention, and kinetic energy
    ActionKinetic,
    /// Maximizes overall score and style-family cluster diversity
    BalancedHero,
}

/// Assembles a curated, pacing-optimized sequence of takes to meet a target duration (e.g. 60s, 90s, 120s),
/// enforcing shot-scale alternating rhythm (Wide -> Medium -> Close-Up) and color temperature continuity (M26).
pub fn compose_smart_showreel(
    candidate_takes: &[ShotTake],
    target_duration_sec: f64,
    objective: ShowreelObjective,
) -> Vec<ShotTake> {
    if candidate_takes.is_empty() || target_duration_sec <= 0.0 {
        return Vec::new();
    }

    // Filter out non-photographic leader and sort candidate pool by objective suitability
    let mut pool: Vec<ShotTake> = candidate_takes
        .iter()
        .filter(|t| !t.concerns.iter().any(|c| c.code == "NON_PHOTOGRAPHIC_OR_CREDITS"))
        .cloned()
        .collect();

    pool.sort_by(|a, b| {
        let score_a = match objective {
            ShowreelObjective::CommercialLighting => {
                a.measured.exposure.dynamic_range_stops * 3.0
                    + a.scores.cinematic_technique_score
                    + a.scores.technical
            }
            ShowreelObjective::DramaticNarrative => {
                a.scores.storytelling_score * 1.5
                    + a.scores.hero_potency_score
                    + if a.style.shot_scale.contains("Close-Up") { 15.0 } else { 0.0 }
            }
            ShowreelObjective::ActionKinetic => {
                a.scores.temporal * 1.5
                    + if a.style.motion_type.contains("Move") || a.style.motion_type.contains("Track") { 20.0 } else { 0.0 }
                    + a.scores.three_second_impact_score
            }
            ShowreelObjective::BalancedHero => a.scores.overall,
        };
        let score_b = match objective {
            ShowreelObjective::CommercialLighting => {
                b.measured.exposure.dynamic_range_stops * 3.0
                    + b.scores.cinematic_technique_score
                    + b.scores.technical
            }
            ShowreelObjective::DramaticNarrative => {
                b.scores.storytelling_score * 1.5
                    + b.scores.hero_potency_score
                    + if b.style.shot_scale.contains("Close-Up") { 15.0 } else { 0.0 }
            }
            ShowreelObjective::ActionKinetic => {
                b.scores.temporal * 1.5
                    + if b.style.motion_type.contains("Move") || b.style.motion_type.contains("Track") { 20.0 } else { 0.0 }
                    + b.scores.three_second_impact_score
            }
            ShowreelObjective::BalancedHero => b.scores.overall,
        };
        score_b.partial_cmp(&score_a).unwrap_or(std::cmp::Ordering::Equal)
    });

    let mut selected: Vec<ShotTake> = Vec::new();
    let mut current_duration = 0.0f64;

    while current_duration < target_duration_sec && !pool.is_empty() {
        // Find best next shot balancing objective score, shot scale alternation, and color temp delta
        let best_idx = pool.iter().enumerate().max_by(|(_, a), (_, b)| {
            let prev_scale = selected.last().map(|s| s.style.shot_scale.as_str()).unwrap_or("");
            let prev_cct = selected.last().map(|s| s.measured.color.estimated_kelvin).unwrap_or(5600.0);

            let scale_bonus_a = if a.style.shot_scale != prev_scale { 12.0 } else { -8.0 };
            let scale_bonus_b = if b.style.shot_scale != prev_scale { 12.0 } else { -8.0 };

            let cct_delta_a = (a.measured.color.estimated_kelvin - prev_cct).abs();
            let cct_delta_b = (b.measured.color.estimated_kelvin - prev_cct).abs();
            let cct_penalty_a = (cct_delta_a / 400.0).min(15.0);
            let cct_penalty_b = (cct_delta_b / 400.0).min(15.0);

            let val_a = a.scores.overall + scale_bonus_a - cct_penalty_a;
            let val_b = b.scores.overall + scale_bonus_b - cct_penalty_b;

            val_a.partial_cmp(&val_b).unwrap_or(std::cmp::Ordering::Equal)
        }).map(|(idx, _)| idx).unwrap_or(0);

        let take = pool.remove(best_idx);
        current_duration += take.duration_sec;
        selected.push(take);

        if current_duration >= target_duration_sec {
            break;
        }
    }

    selected
}
/// a bounded preference boost (`[-3.5, +3.5]` points) matching preferred style families and shot scales.
pub fn compute_feedback_preference_boost(take: &ShotTake) -> f32 {
    let file_path = Path::new("assets/feedback/events.jsonl");
    let Ok(content) = std::fs::read_to_string(file_path) else {
        return 0.0;
    };
    let mut boost = 0.0f32;
    let mut count = 0usize;
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if let Ok(ev) =
            serde_json::from_str::<aesthetic_models::window::SelectFeedbackEvent>(trimmed)
        {
            count += 1;
            let sign = match ev.action.as_str() {
                "promote_hero" => 1.2,
                "pin_select" => 0.8,
                "reject_take" => -1.2,
                _ => 0.3,
            };
            if !ev.style_family.is_empty() && ev.style_family == take.style.style_family {
                boost += sign * 0.8;
            }
            if !ev.shot_scale.is_empty() && ev.shot_scale == take.style.shot_scale {
                boost += sign * 0.5;
            }
        }
    }
    if count == 0 {
        0.0
    } else {
        (boost / (count as f32).sqrt()).clamp(-3.5, 3.5)
    }
}

/// Personalized DP & Aesthetic Profile calibrated dynamically from user curation feedback events (M27).
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PersonalTasteProfile {
    pub total_feedback_events: usize,
    pub promoted_heroes_count: usize,
    pub pinned_selects_count: usize,
    pub rejected_takes_count: usize,
    pub preferred_style_families: Vec<(String, f32)>,
    pub preferred_shot_scales: Vec<(String, f32)>,
    pub calibrated_reranker_weights: CalibratedRerankerWeights,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CalibratedRerankerWeights {
    pub hero_potency_weight: f32,
    pub three_second_impact_weight: f32,
    pub authorship_weight: f32,
    pub storytelling_weight: f32,
    pub cinematic_technique_weight: f32,
    pub memorability_weight: f32,
}

impl Default for CalibratedRerankerWeights {
    fn default() -> Self {
        Self {
            hero_potency_weight: 0.20,
            three_second_impact_weight: 0.20,
            authorship_weight: 0.15,
            storytelling_weight: 0.15,
            cinematic_technique_weight: 0.15,
            memorability_weight: 0.15,
        }
    }
}

/// Computes the personalized taste profile by fitting frequency and action deltas over logged events (M27).
pub fn compute_personal_taste_profile() -> PersonalTasteProfile {
    let file_path = Path::new("assets/feedback/events.jsonl");
    let Ok(content) = std::fs::read_to_string(file_path) else {
        return PersonalTasteProfile {
            total_feedback_events: 0,
            promoted_heroes_count: 0,
            pinned_selects_count: 0,
            rejected_takes_count: 0,
            preferred_style_families: Vec::new(),
            preferred_shot_scales: Vec::new(),
            calibrated_reranker_weights: CalibratedRerankerWeights::default(),
        };
    };

    let mut style_map = std::collections::HashMap::<String, f32>::new();
    let mut scale_map = std::collections::HashMap::<String, f32>::new();
    let mut promoted = 0usize;
    let mut pinned = 0usize;
    let mut rejected = 0usize;
    let mut total = 0usize;

    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if let Ok(ev) =
            serde_json::from_str::<aesthetic_models::window::SelectFeedbackEvent>(trimmed)
        {
            total += 1;
            let weight = match ev.action.as_str() {
                "promote_hero" => {
                    promoted += 1;
                    2.0f32
                }
                "pin_select" => {
                    pinned += 1;
                    1.0f32
                }
                "reject_take" => {
                    rejected += 1;
                    -1.5f32
                }
                _ => 0.5f32,
            };

            if !ev.style_family.is_empty() {
                *style_map.entry(ev.style_family).or_insert(0.0) += weight;
            }
            if !ev.shot_scale.is_empty() {
                *scale_map.entry(ev.shot_scale).or_insert(0.0) += weight;
            }
        }
    }

    let mut preferred_style_families: Vec<(String, f32)> = style_map.into_iter().collect();
    preferred_style_families.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    let mut preferred_shot_scales: Vec<(String, f32)> = scale_map.into_iter().collect();
    preferred_shot_scales.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    // Adapt reranker weights according to promotion vs rejection tendencies
    let mut weights = CalibratedRerankerWeights::default();
    if total > 0 {
        let hero_ratio = (promoted as f32 / total as f32).clamp(0.1, 0.6);
        weights.hero_potency_weight = 0.15 + hero_ratio * 0.25;
        weights.three_second_impact_weight = 0.15 + (1.0 - hero_ratio) * 0.10;
        let sum = weights.hero_potency_weight
            + weights.three_second_impact_weight
            + weights.authorship_weight
            + weights.storytelling_weight
            + weights.cinematic_technique_weight
            + weights.memorability_weight;
        weights.hero_potency_weight /= sum;
        weights.three_second_impact_weight /= sum;
        weights.authorship_weight /= sum;
        weights.storytelling_weight /= sum;
        weights.cinematic_technique_weight /= sum;
        weights.memorability_weight /= sum;
    }

    PersonalTasteProfile {
        total_feedback_events: total,
        promoted_heroes_count: promoted,
        pinned_selects_count: pinned,
        rejected_takes_count: rejected,
        preferred_style_families,
        preferred_shot_scales,
        calibrated_reranker_weights: weights,
    }
}
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct FolderBatchSummary {
    pub folder_path: String,
    pub total_files_discovered: usize,
    pub total_files_processed: usize,
    pub total_takes_extracted: usize,
    pub output_sidecars_dir: String,
    pub elapsed_sec: f64,
    pub per_file_takes: Vec<(String, usize)>,
}

/// Discovers and sequentially analyzes all video files in `folder_path`, saving individual
/// JSON+PNG sidecars into `<out_sidecars_dir>/<file_stem>/` and returning a consolidated summary (M25).
pub fn analyze_folder_queue(
    folder_path: &Path,
    out_sidecars_dir: &Path,
    sample_step_sec: f64,
    top_per_video: Option<usize>,
) -> Result<FolderBatchSummary, String> {
    if !folder_path.is_dir() {
        return Err(format!("Path '{}' is not a directory.", folder_path.display()));
    }

    let mut video_files: Vec<PathBuf> = Vec::new();
    let entries = std::fs::read_dir(folder_path)
        .map_err(|e| format!("Failed to read directory {}: {}", folder_path.display(), e))?;

    for entry in entries.flatten() {
        let p = entry.path();
        if p.is_file() {
            if let Some(ext) = p.extension().and_then(|s| s.to_str()) {
                let ext_lower = ext.to_lowercase();
                if matches!(
                    ext_lower.as_str(),
                    "mp4" | "mov" | "mkv" | "m4v" | "avi" | "webm"
                ) {
                    video_files.push(p);
                }
            }
        }
    }

    video_files.sort();

    if video_files.is_empty() {
        return Err(format!(
            "No supported video files found in '{}'.",
            folder_path.display()
        ));
    }

    let start_time = std::time::Instant::now();
    let mut total_takes = 0;
    let mut per_file_takes = Vec::new();
    let mut all_batch_takes = Vec::new();

    for vpath in &video_files {
        let file_stem = vpath
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("video");
        let sub_sidecars = out_sidecars_dir.join(file_stem);
        let contact_sheet = out_sidecars_dir.join(format!("{}_contact_sheet.html", file_stem));
        let edl_file = out_sidecars_dir.join(format!("{}_selects.edl", file_stem));
        let xml_file = out_sidecars_dir.join(format!("{}_selects.xml", file_stem));
        let csv_file = out_sidecars_dir.join(format!("{}_selects.csv", file_stem));

        let options = BatchOptions {
            sample_step_sec,
            top_n: top_per_video,
            export_sidecars_dir: Some(sub_sidecars.clone()),
            export_contact_sheet_path: Some(contact_sheet),
            export_edl_path: Some(edl_file),
            export_fcpxml_path: Some(xml_file),
            export_csv_path: Some(csv_file),
            ..Default::default()
        };

        if let Ok(res) = analyze_video_file(vpath, &options) {
            let n_takes = res.ranked_takes.len();
            total_takes += n_takes;
            all_batch_takes.extend(res.ranked_takes);
            per_file_takes.push((file_stem.to_string(), n_takes));
        } else {
            per_file_takes.push((file_stem.to_string(), 0));
        }
    }

    // Export unified season batch deliverables (EDL, FCPXML, CSV, Resolve Script)
    if !all_batch_takes.is_empty() {
        all_batch_takes.sort_by(|a, b| {
            b.scores
                .overall
                .partial_cmp(&a.scores.overall)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        let season_edl = crate::export::generate_cmx3600_edl(
            "SEASON_HERO_SELECTS",
            "SEASON_BATCH",
            &all_batch_takes,
            24.0,
        );
        let _ = std::fs::write(out_sidecars_dir.join("season_all_hero_selects.edl"), season_edl);

        let season_xml = crate::export::generate_fcpxml(
            "SEASON_HERO_SELECTS",
            "SEASON_BATCH",
            &all_batch_takes,
            24.0,
        );
        let _ = std::fs::write(out_sidecars_dir.join("season_all_hero_selects.xml"), season_xml);

        let season_csv = crate::export::generate_csv_selects("SEASON_BATCH", &all_batch_takes, 24.0);
        let _ = std::fs::write(out_sidecars_dir.join("season_all_hero_selects.csv"), season_csv);

        let season_py = crate::export::generate_resolve_timeline_script(
            "SEASON_HERO_SELECTS",
            &folder_path.to_string_lossy(),
            &all_batch_takes,
            24.0,
        );
        let _ = std::fs::write(out_sidecars_dir.join("season_all_hero_selects.py"), season_py);
    }

    let elapsed_sec = start_time.elapsed().as_secs_f64();

    Ok(FolderBatchSummary {
        folder_path: folder_path.display().to_string(),
        total_files_discovered: video_files.len(),
        total_files_processed: per_file_takes.len(),
        total_takes_extracted: total_takes,
        output_sidecars_dir: out_sidecars_dir.display().to_string(),
        elapsed_sec,
        per_file_takes,
    })
}
