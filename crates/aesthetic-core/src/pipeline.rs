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
    /// Full un-truncated list of ranked takes across all detected scenes for instant Top-N re-slicing.
    pub all_ranked_takes: Vec<ShotTake>,
    pub total_scenes_detected: usize,
    pub filtered_title_cards_count: usize,
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

    // 3. Multi-signal non-photographic title card / credits / leader detection
    // Also check uncropped frame when matte crop trimmed wide margins on both axes (centered title box on black).
    let mut title_card_det = detect_title_card_or_graphic(&active_img, &physics);
    if title_card_det.is_none()
        && crop.x > img.width() / 10
        && crop.y > img.height() / 10
    {
        title_card_det = detect_title_card_or_graphic(img, &physics);
    }
    let is_black_or_credits = title_card_det.is_some();

    let zones = &physics.exposure.false_color_zones;
    let lighting_key = if is_black_or_credits {
        "Title Card / Non-Photographic".to_string()
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
        technical_score = (technical_score * 0.15).min(12.0);
    }
    // Creative (craft) and temporal pillars are filled in by `enrich_take` when measured.
    // Until then the overall score reflects only what was actually measured.
    let creative_score = 0.0;
    let temporal_score = 0.0;
    let overall_score = technical_score;

    let mut concerns = Vec::new();
    if let Some(ref det) = title_card_det {
        concerns.push(DiagnosticFlag {
            code: "NON_PHOTOGRAPHIC_OR_CREDITS".to_string(),
            title: "Title Card, Credits, or Non-Photographic Graphic".to_string(),
            description: format!(
                "{} (border match {:.0}%, bg match {:.0}%, flat {:.0}%, mid-grad {:.1}%, text bands {}) — filtered from hero selects",
                det.reason,
                det.border_bg_pct * 100.0,
                det.bg_match_pct * 100.0,
                det.flat_pixel_pct * 100.0,
                det.mid_grad_pct * 100.0,
                det.text_band_rows
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

/// Diagnostic breakdown explaining why a frame was classified as a non-photographic title card,
/// slate, credits roll, or blank leader.
#[derive(Debug, Clone)]
pub struct TitleCardDetection {
    pub reason: String,
    pub bg_match_pct: f32,
    pub border_bg_pct: f32,
    pub flat_pixel_pct: f32,
    pub mid_grad_pct: f32,
    pub text_band_rows: usize,
}

#[derive(Debug, Clone)]
struct GraphicCardFeatures {
    bg_match_pct: f32,
    border_bg_pct: f32,
    border_grad_mean: f32,
    border_mean_luma: f32,
    border_luma_std: f32,
    flat_pixel_pct: f32,
    mid_grad_pct: f32,
    sharp_edge_pct: f32,
    text_band_rows: usize,
    dense_credit_rows: usize,
}

fn channel_median(vals: &mut [u8]) -> f32 {
    if vals.is_empty() {
        return 0.0;
    }
    vals.sort_unstable();
    let mid = vals.len() / 2;
    if vals.len() % 2 == 1 {
        vals[mid] as f32
    } else {
        (vals[mid - 1] as f32 + vals[mid] as f32) * 0.5
    }
}

fn corner_median_rgb(img: &RgbImage, x0: u32, y0: u32, x1: u32, y1: u32) -> [f32; 3] {
    let cap = ((x1 - x0) * (y1 - y0)) as usize;
    let mut rs = Vec::with_capacity(cap);
    let mut gs = Vec::with_capacity(cap);
    let mut bs = Vec::with_capacity(cap);
    for y in y0..y1 {
        for x in x0..x1 {
            let p = img.get_pixel(x, y);
            rs.push(p[0]);
            gs.push(p[1]);
            bs.push(p[2]);
        }
    }
    [
        channel_median(&mut rs),
        channel_median(&mut gs),
        channel_median(&mut bs),
    ]
}

fn analyze_graphic_card_features(img: &RgbImage) -> GraphicCardFeatures {
    let (w0, h0) = img.dimensions();
    let resized;
    let proxy: &RgbImage = if w0 > 320 {
        let nh = ((h0 as f32) * 320.0 / (w0 as f32)).round().max(16.0) as u32;
        resized = image::imageops::resize(img, 320, nh, image::imageops::FilterType::Triangle);
        &resized
    } else {
        img
    };

    let (w, h) = proxy.dimensions();
    if w < 16 || h < 16 {
        return GraphicCardFeatures {
            bg_match_pct: 1.0,
            border_bg_pct: 1.0,
            border_grad_mean: 0.0,
            border_mean_luma: 0.0,
            border_luma_std: 0.0,
            flat_pixel_pct: 1.0,
            mid_grad_pct: 0.0,
            sharp_edge_pct: 0.0,
            text_band_rows: 0,
            dense_credit_rows: 0,
        };
    }

    // Fit 4-corner bilinear background model (10% x 10% corner patches, min 4x4)
    let pw = ((w as f32 * 0.10).round() as u32).max(4).min(w / 2);
    let ph = ((h as f32 * 0.10).round() as u32).max(4).min(h / 2);
    let c_tl = corner_median_rgb(proxy, 0, 0, pw, ph);
    let c_tr = corner_median_rgb(proxy, w - pw, 0, w, ph);
    let c_bl = corner_median_rgb(proxy, 0, h - ph, pw, h);
    let c_br = corner_median_rgb(proxy, w - pw, h - ph, w, h);

    let bg_at = |x: u32, y: u32| -> [f32; 3] {
        let fx = x as f32 / (w - 1) as f32;
        let fy = y as f32 / (h - 1) as f32;
        let mut out = [0.0f32; 3];
        for ch in 0..3 {
            let top = c_tl[ch] * (1.0 - fx) + c_tr[ch] * fx;
            let bot = c_bl[ch] * (1.0 - fx) + c_br[ch] * fx;
            out[ch] = top * (1.0 - fy) + bot * fy;
        }
        out
    };

    let luma_of = |rgb: [f32; 3]| -> f32 { 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] };

    // Outer 8% border metrics
    let bx_margin = ((w as f32 * 0.08).round() as u32).max(2);
    let by_margin = ((h as f32 * 0.08).round() as u32).max(2);
    let mut border_match_count = 0usize;
    let mut border_count = 0usize;
    let mut border_grad_sum = 0.0f64;
    let mut border_luma_sum = 0.0f64;
    let mut border_luma_sq_sum = 0.0f64;

    // Interior metrics
    let mut bg_match_count = 0usize;
    let mut flat_count = 0usize;
    let mut mid_grad_count = 0usize;
    let mut sharp_edge_count = 0usize;
    let total_pixels = (w * h) as usize;

    let raw = proxy.as_raw();
    let stride = (w as usize) * 3;

    for y in 0..h {
        let in_border_y = y < by_margin || y >= h - by_margin;
        for x in 0..w {
            let idx = (y as usize) * stride + (x as usize) * 3;
            let r = raw[idx] as f32;
            let g = raw[idx + 1] as f32;
            let b = raw[idx + 2] as f32;
            let l = 0.2126 * r + 0.7152 * g + 0.0722 * b;

            let bg = bg_at(x, y);
            let max_bg_diff = (r - bg[0])
                .abs()
                .max((g - bg[1]).abs())
                .max((b - bg[2]).abs());

            if max_bg_diff <= 24.0 {
                bg_match_count += 1;
            }

            let mut grad_luma = 0.0f32;
            let mut max_nb_diff = 0.0f32;
            if x + 1 < w && y + 1 < h {
                let r_idx = idx + 3;
                let d_idx = idx + stride;
                let lr = 0.2126 * raw[r_idx] as f32
                    + 0.7152 * raw[r_idx + 1] as f32
                    + 0.0722 * raw[r_idx + 2] as f32;
                let ld = 0.2126 * raw[d_idx] as f32
                    + 0.7152 * raw[d_idx + 1] as f32
                    + 0.0722 * raw[d_idx + 2] as f32;
                grad_luma = (l - lr).abs() + (l - ld).abs();

                let dr = (r - raw[r_idx] as f32)
                    .abs()
                    .max((g - raw[r_idx + 1] as f32).abs())
                    .max((b - raw[r_idx + 2] as f32).abs());
                let dd = (r - raw[d_idx] as f32)
                    .abs()
                    .max((g - raw[d_idx + 1] as f32).abs())
                    .max((b - raw[d_idx + 2] as f32).abs());
                max_nb_diff = dr.max(dd);
            }

            if max_nb_diff <= 6.0 {
                flat_count += 1;
            }
            if (6.0..=28.0).contains(&grad_luma) {
                mid_grad_count += 1;
            }
            if grad_luma >= 45.0 {
                sharp_edge_count += 1;
            }

            if in_border_y || x < bx_margin || x >= w - bx_margin {
                border_count += 1;
                if max_bg_diff <= 22.0 {
                    border_match_count += 1;
                }
                border_grad_sum += grad_luma as f64;
                border_luma_sum += l as f64;
                border_luma_sq_sum += (l as f64) * (l as f64);
            }
        }
    }

    let b_cnt_f = (border_count.max(1)) as f64;
    let border_mean_luma = (border_luma_sum / b_cnt_f) as f32;
    let border_var = ((border_luma_sq_sum / b_cnt_f) - (border_mean_luma as f64).powi(2)).max(0.0);
    let border_luma_std = border_var.sqrt() as f32;

    // Horizontal typography / text-band row scan across interior rows
    let y_start = ((h as f32 * 0.08).round() as u32).max(1);
    let y_end = ((h as f32 * 0.92).round() as u32).min(h.saturating_sub(1));
    let x_margin_5pct = ((w as f32 * 0.05).round() as u32).max(2);
    let max_glyph_run = (((w as f32 / 320.0) * 14.0).round() as u32).clamp(4, 14);

    let mut text_band_rows = 0usize;
    let mut dense_credit_rows = 0usize;

    for y in y_start..y_end {
        let mut transitions = 0usize;
        let mut short_fg_runs = 0usize;
        let mut row_bg_pixels = 0usize;
        let mut outer_margin_fg = 0usize;
        let mut prev_fg = false;
        let mut curr_run_len = 0u32;

        for x in 0..w {
            let idx = (y as usize) * stride + (x as usize) * 3;
            let r = raw[idx] as f32;
            let g = raw[idx + 1] as f32;
            let b = raw[idx + 2] as f32;
            let l = 0.2126 * r + 0.7152 * g + 0.0722 * b;

            let bg = bg_at(x, y);
            let bg_luma = luma_of(bg);
            let linf = (r - bg[0]).abs().max((g - bg[1]).abs()).max((b - bg[2]).abs());

            if linf <= 24.0 {
                row_bg_pixels += 1;
            }
            let is_fg = linf > 30.0 || (l - bg_luma).abs() > 28.0;

            if is_fg && (x < x_margin_5pct || x >= w - x_margin_5pct) {
                outer_margin_fg += 1;
            }

            if x > 0 && is_fg != prev_fg {
                transitions += 1;
                if prev_fg && (1..=max_glyph_run).contains(&curr_run_len) {
                    short_fg_runs += 1;
                }
                curr_run_len = if is_fg { 1 } else { 0 };
            } else if is_fg {
                curr_run_len += 1;
            }
            prev_fg = is_fg;
        }
        if prev_fg && (1..=max_glyph_run).contains(&curr_run_len) {
            short_fg_runs += 1;
        }

        let row_bg_pct = row_bg_pixels as f32 / (w as f32);
        let margins_clean = outer_margin_fg <= ((w as usize) / 40).max(1);

        if transitions >= 8 && short_fg_runs >= 3 && row_bg_pct >= 0.45 && margins_clean {
            text_band_rows += 1;
        }
        if transitions >= 12 && short_fg_runs >= 5 && row_bg_pct >= 0.40 {
            dense_credit_rows += 1;
        }
    }

    let tot_f = (total_pixels.max(1)) as f32;
    GraphicCardFeatures {
        bg_match_pct: bg_match_count as f32 / tot_f,
        border_bg_pct: border_match_count as f32 / (b_cnt_f as f32),
        border_grad_mean: (border_grad_sum / b_cnt_f) as f32,
        border_mean_luma,
        border_luma_std,
        flat_pixel_pct: flat_count as f32 / tot_f,
        mid_grad_pct: mid_grad_count as f32 / tot_f,
        sharp_edge_pct: sharp_edge_count as f32 / tot_f,
        text_band_rows,
        dense_credit_rows,
    }
}

/// Multi-signal detector for non-photographic frames: title cards (on black, white, color,
/// or gradient backdrops), opening/end credits rolls, color slates, and blank leaders.
pub fn detect_title_card_or_graphic(
    active_img: &RgbImage,
    physics: &aesthetic_models::physics::ObjectivePhysics,
) -> Option<TitleCardDetection> {
    let exp = &physics.exposure;
    let col = &physics.color;

    // 1. Fast exposure/entropy leader check
    if exp.histogram_mean < 14.0
        || exp.histogram_mean > 242.0
        || exp.shadow_clip_pct > 78.0
        || exp.highlight_clip_pct > 75.0
        || exp.el_zones.zone_0_black_pct > 82.0
        || exp.histogram_std < 6.0
        || col.palette_entropy < 1.0
    {
        return Some(TitleCardDetection {
            reason: format!(
                "Blank leader or near-uniform frame (mean luma {:.1}, std {:.1}, entropy {:.2} bits)",
                exp.histogram_mean, exp.histogram_std, col.palette_entropy
            ),
            bg_match_pct: 1.0 - (exp.histogram_std / 128.0).clamp(0.0, 1.0),
            border_bg_pct: 1.0,
            flat_pixel_pct: 0.95,
            mid_grad_pct: 0.0,
            text_band_rows: 0,
        });
    }

    let f = analyze_graphic_card_features(active_img);

    let reason = if f.border_bg_pct >= 0.85
        && f.bg_match_pct >= 0.55
        && f.text_band_rows >= 3
        && f.mid_grad_pct < 0.12
    {
        Some("Typography title card on uniform/gradient backdrop".to_string())
    } else if f.border_bg_pct >= 0.90
        && f.border_grad_mean < 3.0
        && f.bg_match_pct >= 0.72
        && f.flat_pixel_pct >= 0.76
        && f.mid_grad_pct < 0.065
        && f.text_band_rows >= 2
    {
        Some("Minimalist centered title or intertitle graphic".to_string())
    } else if f.border_mean_luma < 42.0
        && f.border_luma_std < 14.0
        && f.border_bg_pct >= 0.84
        && f.bg_match_pct >= 0.62
        && f.text_band_rows >= 2
    {
        Some("Dark-backdrop title card or credits frame".to_string())
    } else if f.border_mean_luma > 200.0
        && f.border_luma_std < 15.0
        && f.border_bg_pct >= 0.84
        && f.bg_match_pct >= 0.62
        && f.text_band_rows >= 2
    {
        Some("Light/white-backdrop title card or intertitle frame".to_string())
    } else if f.border_bg_pct >= 0.80
        && f.dense_credit_rows >= 5
        && f.mid_grad_pct < 0.14
        && col.palette_entropy < 2.8
    {
        Some("Full-screen credits roll or multi-line text wall".to_string())
    } else if (col.palette_entropy < 1.35 && f.flat_pixel_pct >= 0.84 && f.mid_grad_pct < 0.05)
        || (col.palette_entropy < 1.65
            && f.border_bg_pct >= 0.92
            && f.bg_match_pct >= 0.80
            && f.sharp_edge_pct >= 0.003
            && f.mid_grad_pct < 0.03)
    {
        Some("Flat solid slate, vector logo card, or non-photographic graphic".to_string())
    } else {
        None
    };

    reason.map(|r| TitleCardDetection {
        reason: r,
        bg_match_pct: f.bg_match_pct,
        border_bg_pct: f.border_bg_pct,
        flat_pixel_pct: f.flat_pixel_pct,
        mid_grad_pct: f.mid_grad_pct,
        text_band_rows: f.text_band_rows,
    })
}

/// Lightweight Pass-1 detector run on 160x90 streaming proxy frames to tag non-photographic
/// title cards, blank leaders, and credits rolls without computing the full 79-metric vector.
pub fn is_proxy_title_card_or_blank(proxy: &RgbImage) -> bool {
    let (pw, ph) = proxy.dimensions();
    if pw < 16 || ph < 16 {
        return true;
    }

    // Crop top/bottom letterbox bars or left/right pillarbox bars, while keeping centered title cards intact
    let crop = detect_active_picture(proxy);
    let cropped_img;
    let active: &RgbImage = if (crop.x <= 4 || crop.y <= 4)
        && (crop.width < pw || crop.height < ph)
    {
        cropped_img = image::imageops::crop_imm(proxy, crop.x, crop.y, crop.width, crop.height)
            .to_image();
        &cropped_img
    } else {
        proxy
    };

    let raw = active.as_raw();
    let total = raw.len() / 3;
    if total == 0 {
        return true;
    }

    let mut sum = 0.0f64;
    let mut sq_sum = 0.0f64;
    for px in raw.as_chunks::<3>().0 {
        let l = (0.2126 * px[0] as f32 + 0.7152 * px[1] as f32 + 0.0722 * px[2] as f32) as f64;
        sum += l;
        sq_sum += l * l;
    }
    let mean = (sum / total as f64) as f32;
    let var = ((sq_sum / total as f64) - (mean as f64).powi(2)).max(0.0);
    let std = var.sqrt() as f32;

    if mean < 14.0 || mean > 242.0 || std < 6.0 {
        return true;
    }

    let f = analyze_graphic_card_features(active);
    (f.border_bg_pct >= 0.85
        && f.bg_match_pct >= 0.55
        && f.text_band_rows >= 3
        && f.mid_grad_pct < 0.12)
        || (f.border_bg_pct >= 0.90
            && f.border_grad_mean < 3.0
            && f.bg_match_pct >= 0.72
            && f.flat_pixel_pct >= 0.76
            && f.mid_grad_pct < 0.065
            && f.text_band_rows >= 2)
        || (f.border_mean_luma < 42.0
            && f.border_luma_std < 14.0
            && f.border_bg_pct >= 0.84
            && f.bg_match_pct >= 0.62
            && f.text_band_rows >= 2)
        || (f.border_mean_luma > 200.0
            && f.border_luma_std < 15.0
            && f.border_bg_pct >= 0.84
            && f.bg_match_pct >= 0.62
            && f.text_band_rows >= 2)
        || (f.border_bg_pct >= 0.80 && f.dense_credit_rows >= 5 && f.mid_grad_pct < 0.14)
}

/// Selects candidate shots across EVERY photographic scene detected in Pass 1:
/// 1. Unconditionally includes the top-quality shot from every scene (ensuring full timeline coverage).
/// 2. Distributes remaining evaluation budget round-robin across visually distinct shots in each scene.
fn select_pass2_shots(
    scenes: &[crate::scene::DetectedScene],
    top_n: Option<usize>,
) -> Vec<(usize, crate::scene::ShotCandidateWindow)> {
    use std::collections::HashSet;

    if scenes.is_empty() {
        return Vec::new();
    }

    let mut per_scene_sorted: Vec<(usize, Vec<crate::scene::ShotCandidateWindow>)> = scenes
        .iter()
        .filter_map(|s| {
            let mut shots: Vec<_> = s
                .shots
                .iter()
                .filter(|sh| !sh.is_non_photographic)
                .cloned()
                .collect();
            if shots.is_empty() {
                return None;
            }
            shots.sort_by(|a, b| {
                b.proxy_quality
                    .partial_cmp(&a.proxy_quality)
                    .unwrap_or(std::cmp::Ordering::Equal)
            });
            Some((s.scene_index, shots))
        })
        .collect();

    if per_scene_sorted.is_empty() {
        return Vec::new();
    }

    let mut picked: Vec<(usize, crate::scene::ShotCandidateWindow)> = Vec::new();
    let mut picked_hists: Vec<Vec<[f32; 24]>> = vec![Vec::new(); per_scene_sorted.len()];
    let mut used_indices: Vec<HashSet<usize>> = vec![HashSet::new(); per_scene_sorted.len()];

    // Pass A: Guarantee the single best shot from EVERY photographic scene
    for (s_pos, (scene_idx, shots)) in per_scene_sorted.iter().enumerate() {
        picked_hists[s_pos].push(shots[0].color_hist);
        used_indices[s_pos].insert(0);
        picked.push((*scene_idx, shots[0].clone()));
    }

    // Pass B: Round-robin budget for additional visually distinct shots per scene
    let eval_budget = if let Some(n) = top_n {
        scenes.len().max(n.saturating_mul(2)).clamp(40, 240)
    } else {
        scenes.len().clamp(80, 240)
    };

    while picked.len() < eval_budget {
        let mut added_any = false;
        for (s_pos, (scene_idx, shots)) in per_scene_sorted.iter_mut().enumerate() {
            if picked.len() >= eval_budget {
                break;
            }
            if let Some((best_k, sh)) = shots.iter().enumerate().find(|(k, cand)| {
                !used_indices[s_pos].contains(k)
                    && picked_hists[s_pos]
                        .iter()
                        .all(|h| crate::scene::histogram_l1_distance(h, &cand.color_hist) > 0.22)
            }) {
                picked_hists[s_pos].push(sh.color_hist);
                used_indices[s_pos].insert(best_k);
                picked.push((*scene_idx, sh.clone()));
                added_any = true;
            }
        }
        if !added_any {
            break;
        }
    }

    picked
}

struct Pass2Context<'a> {
    video_path: &'a Path,
    options: &'a BatchOptions,
    dr_q: &'a MetricQuantiles,
    rolloff_q: &'a MetricQuantiles,
    sharp_q: &'a MetricQuantiles,
    store: &'a BaselineStore,
    inference: &'a ModelInferenceEngine,
}

struct Pass2ShotResult {
    clean: Option<(ShotTake, RgbImage)>,
    fallback: Option<(ShotTake, RgbImage)>,
    filtered_cards: usize,
}

fn evaluate_pass2_shot(
    ctx: &Pass2Context<'_>,
    scene_index: usize,
    shot: &crate::scene::ShotCandidateWindow,
) -> Pass2ShotResult {
    let mut filtered_cards = 0usize;
    let mut fallback_non_photo: Option<(ShotTake, RgbImage)> = None;

    for &ts in &shot.best_timestamps {
        let frames_opt = extract_frames_burst(ctx.video_path, ts, 3, 4.0, None)
            .ok()
            .or_else(|| extract_frame_rgb(ctx.video_path, ts).ok().map(|f| vec![f]));

        let Some(frames) = frames_opt else {
            continue;
        };
        if frames.is_empty() {
            continue;
        }

        // Cut-aware pair selection within the 3-frame burst (0.25s spacing)
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

        let mut candidate = evaluate_candidate_frame(
            frame,
            "pending",
            scene_index,
            eff_ts,
            ctx.dr_q,
            ctx.rolloff_q,
            ctx.sharp_q,
        );
        enrich_take(&mut candidate, frame, next_ref, ctx.store, ctx.inference);

        // Clamp take window inside this shot's boundaries
        let shot_dur = (shot.end_sec - shot.start_sec).max(ctx.options.min_take_duration_sec);
        let win_dur = shot_dur.clamp(
            ctx.options.min_take_duration_sec,
            ctx.options.max_take_duration_sec,
        );
        let max_start = (shot.end_sec - win_dur).max(shot.start_sec);
        let win_start = (eff_ts - win_dur * 0.35)
            .max(shot.start_sec)
            .min(max_start);
        candidate.start_sec = win_start;
        candidate.end_sec = (win_start + win_dur).max(win_start + ctx.options.min_take_duration_sec);
        candidate.duration_sec = candidate.end_sec - candidate.start_sec;
        candidate.hero_timestamp_sec = eff_ts;

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

        if candidate
            .concerns
            .iter()
            .any(|c| c.code == "NON_PHOTOGRAPHIC_OR_CREDITS")
        {
            filtered_cards += 1;
            if fallback_non_photo.is_none() {
                fallback_non_photo = Some((candidate, frame.clone()));
            }
            continue;
        }

        return Pass2ShotResult {
            clean: Some((candidate, frame.clone())),
            fallback: None,
            filtered_cards,
        };
    }

    Pass2ShotResult {
        clean: None,
        fallback: fallback_non_photo,
        filtered_cards,
    }
}

/// Executes full end-to-end two-pass scene-by-scene analysis on a video file.
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

    // Pass 1: Fast single-pass streaming proxy scan across 100% of the timeline
    let scan_fps = if (options.sample_step_sec - 1.0).abs() >= 1e-4 {
        (1.0 / options.sample_step_sec.max(0.25)).clamp(0.25, 4.0)
    } else if video_info.duration_sec <= 180.0 {
        2.0
    } else if video_info.duration_sec <= 2700.0 {
        1.0
    } else {
        0.5
    };

    let (detected_scenes, mut filtered_title_cards_count) =
        match crate::video::scan_video_scenes(video_path, video_info.duration_sec, scan_fps) {
            Ok((scenes, non_photo)) if !scenes.is_empty() => (scenes, non_photo),
            Ok((_, non_photo)) => {
                // Entire timeline flagged as non-photographic or single very short shot: synthesize 1 fallback scene
                let mid = (video_info.duration_sec * 0.5).max(0.0);
                let fallback_scene = crate::scene::DetectedScene {
                    scene_index: 1,
                    start_sec: 0.0,
                    end_sec: video_info.duration_sec,
                    shots: vec![crate::scene::ShotCandidateWindow {
                        start_sec: 0.0,
                        end_sec: video_info.duration_sec,
                        best_timestamps: vec![mid],
                        proxy_quality: 50.0,
                        avg_luma: 128.0,
                        color_hist: [0.0; 24],
                        is_non_photographic: false,
                    }],
                    is_non_photographic: false,
                };
                (vec![fallback_scene], non_photo)
            }
            Err(_) => {
                // Safe fallback for exotic codecs/short synthetic clips if rawvideo pipe fails
                let mid = (video_info.duration_sec * 0.5).max(0.0);
                let fallback_scene = crate::scene::DetectedScene {
                    scene_index: 1,
                    start_sec: 0.0,
                    end_sec: video_info.duration_sec,
                    shots: vec![crate::scene::ShotCandidateWindow {
                        start_sec: 0.0,
                        end_sec: video_info.duration_sec,
                        best_timestamps: vec![mid],
                        proxy_quality: 50.0,
                        avg_luma: 128.0,
                        color_hist: [0.0; 24],
                        is_non_photographic: false,
                    }],
                    is_non_photographic: false,
                };
                (vec![fallback_scene], 0)
            }
        };

    let total_scenes_detected = detected_scenes.len();
    let pass2_shots = select_pass2_shots(&detected_scenes, options.top_n);

    // Pass 2: Concurrent full-resolution evaluation across every detected scene (bounded 4 workers)
    let pass2_ctx = Pass2Context {
        video_path,
        options,
        dr_q: &dr_q,
        rolloff_q: &rolloff_q,
        sharp_q: &sharp_q,
        store: &store,
        inference: &inference,
    };
    let next_idx = std::sync::atomic::AtomicUsize::new(0);
    let total_jobs = pass2_shots.len();
    let worker_count = total_jobs.clamp(1, 4);
    let results_mutex = std::sync::Mutex::new(Vec::with_capacity(total_jobs));
    let fallback_mutex = std::sync::Mutex::new(Vec::new());
    let extra_filtered = std::sync::atomic::AtomicUsize::new(0);

    std::thread::scope(|s| {
        for _ in 0..worker_count {
            s.spawn(|| loop {
                let job_i = next_idx.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                if job_i >= total_jobs {
                    break;
                }
                let (scene_idx, ref shot) = pass2_shots[job_i];
                let res = evaluate_pass2_shot(&pass2_ctx, scene_idx, shot);
                if res.filtered_cards > 0 {
                    extra_filtered.fetch_add(res.filtered_cards, std::sync::atomic::Ordering::Relaxed);
                }
                if let Some(clean) = res.clean {
                    if let Ok(mut guard) = results_mutex.lock() {
                        guard.push(clean);
                    }
                } else if let Some(fb) = res.fallback {
                    if let Ok(mut guard) = fallback_mutex.lock() {
                        guard.push(fb);
                    }
                }
            });
        }
    });

    filtered_title_cards_count += extra_filtered.load(std::sync::atomic::Ordering::Relaxed);

    let mut clean_results = results_mutex.into_inner().unwrap_or_default();
    if clean_results.is_empty() {
        clean_results = fallback_mutex.into_inner().unwrap_or_default();
    }

    // Deterministic order: scene_index ascending, then hero_timestamp_sec ascending
    clean_results.sort_by(|(a, _), (b, _)| {
        a.scene_index.cmp(&b.scene_index).then_with(|| {
            a.hero_timestamp_sec
                .partial_cmp(&b.hero_timestamp_sec)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
    });

    // Deduplicate near-identical camera setups within the SAME scene (keeping higher score)
    let mut deduped: Vec<(ShotTake, RgbImage)> = Vec::with_capacity(clean_results.len());
    for (cand, frame) in clean_results {
        if let Some((prev, prev_frame)) = deduped.last_mut() {
            if prev.scene_index == cand.scene_index
                && crate::scene::compute_frame_difference(prev_frame, &frame) < 10.5
            {
                if cand.scores.overall > prev.scores.overall {
                    *prev = cand;
                    *prev_frame = frame;
                }
                continue;
            }
        }
        deduped.push((cand, frame));
    }

    let mut takes: Vec<ShotTake> = Vec::with_capacity(deduped.len());
    let mut hero_frames: std::collections::HashMap<String, RgbImage> =
        std::collections::HashMap::new();
    for (idx, (mut take, frame)) in deduped.into_iter().enumerate() {
        let take_id = format!("take_{:03}", idx + 1);
        take.take_id = take_id.clone();
        hero_frames.insert(take_id, frame);
        takes.push(take);
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

    // Apply scene-aware Maximal Marginal Relevance (MMR) reel diversity ranking
    // so every strong scene surfaces before duplicate angles and title cards are stripped.
    apply_reel_diversity_ranking(&mut takes);

    let all_ranked_takes = takes.clone();
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
        all_ranked_takes,
        total_scenes_detected,
        filtered_title_cards_count,
        sequence_metrics,
        edl_content,
        csv_content,
        fcpxml_content,
        contact_sheet_html,
        sidecars_count,
        extracted_clips_count,
    })
}

/// Greedily orders photographic candidate takes by scene-aware Maximal Marginal Relevance (MMR),
/// stripping non-photographic title cards/leaders when photographic takes exist and ensuring every
/// scene gets representation before picking duplicate angles from the same scene.
pub fn apply_reel_diversity_ranking(takes: &mut Vec<ShotTake>) {
    // Separate photographic takes from non-photographic title cards / black leaders first
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

    if photo_pool.is_empty() {
        *takes = leader_pool;
        return;
    }

    if photo_pool.len() <= 2 {
        *takes = photo_pool;
        return;
    }

    let mut represented_scenes: std::collections::HashSet<usize> = std::collections::HashSet::new();
    let mut selected: Vec<ShotTake> = Vec::with_capacity(photo_pool.len());
    let first = photo_pool.remove(0);
    represented_scenes.insert(first.scene_index);
    selected.push(first);

    while !photo_pool.is_empty() {
        let has_unrepresented_scene = photo_pool
            .iter()
            .any(|c| !represented_scenes.contains(&c.scene_index));

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

            // Scene coverage priority: penalize duplicate angles in already-represented scenes
            // while other distinct scenes remain unrepresented in the ranked selects.
            let scene_penalty = if has_unrepresented_scene
                && represented_scenes.contains(&cand.scene_index)
            {
                10.0f32
            } else {
                0.0f32
            };

            // Up to 7.5-point MMR penalty for redundant recurring setups + learned feedback preference boost (M19)
            let pref_boost = compute_feedback_preference_boost(cand);
            let mmr_score =
                cand.scores.overall + pref_boost - 7.5 * max_redundancy - scene_penalty;
            if mmr_score > best_mmr {
                best_mmr = mmr_score;
                best_idx = idx;
            }
        }

        let chosen = photo_pool.remove(best_idx);
        represented_scenes.insert(chosen.scene_index);
        selected.push(chosen);
    }

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
