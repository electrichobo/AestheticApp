//! Scene & Cut Detection Engine
//!
//! Multi-signal transition classifier detecting hard cuts, dissolves,
//! fades, wipes, match cuts, and continuous takes using temporal difference metrics.

use image::RgbImage;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TransitionType {
    HardCut,
    Dissolve,
    FadeToBlack,
    FadeToWhite,
    Wipe,
    MatchCut,
    None,
}

#[derive(Debug, Clone)]
pub struct SceneBoundary {
    pub frame_index: u64,
    pub timestamp_sec: f64,
    pub transition: TransitionType,
    pub confidence: f32,
}

/// Compute Mean Absolute Difference (MAD) between two RGB images.
pub fn compute_frame_difference(img_a: &RgbImage, img_b: &RgbImage) -> f32 {
    let (wa, ha) = img_a.dimensions();
    let (wb, hb) = img_b.dimensions();

    if wa != wb || ha != hb || wa == 0 || ha == 0 {
        return 100.0;
    }

    let pixels_a = img_a.as_raw();
    let pixels_b = img_b.as_raw();

    let mut diff_sum = 0u64;
    for (a, b) in pixels_a.iter().zip(pixels_b.iter()) {
        diff_sum += (*a as i32 - *b as i32).unsigned_abs() as u64;
    }

    let total_elements = (wa * ha * 3) as f64;
    ((diff_sum as f64 / total_elements) / 255.0 * 100.0) as f32
}

/// Detects if frame delta exhibits progressive directional wipe characteristics.
pub fn detect_directional_wipe(img_a: &RgbImage, img_b: &RgbImage) -> bool {
    let (w, h) = img_a.dimensions();
    if w < 16 || h < 16 {
        return false;
    }

    // Split horizontally into left and right halves
    let half_w = w / 2;
    let mut left_diff = 0u64;
    let mut right_diff = 0u64;

    for y in 0..h {
        for x in 0..half_w {
            let pa = img_a.get_pixel(x, y);
            let pb = img_b.get_pixel(x, y);
            left_diff += (pa[0] as i32 - pb[0] as i32).unsigned_abs() as u64;
        }
        for x in half_w..w {
            let pa = img_a.get_pixel(x, y);
            let pb = img_b.get_pixel(x, y);
            right_diff += (pa[0] as i32 - pb[0] as i32).unsigned_abs() as u64;
        }
    }

    let left_norm = left_diff as f32 / (half_w * h) as f32;
    let right_norm = right_diff as f32 / ((w - half_w) * h) as f32;

    // A wipe exhibits massive asymmetric difference between left and right halves during transit
    (left_norm - right_norm).abs() > 35.0
}

/// Classify a boundary between consecutive frames.
pub fn classify_transition(
    delta_mad: f32,
    luma_b: f32,
    is_wipe_candidate: bool,
    compositional_match_score: f32,
) -> TransitionType {
    if is_wipe_candidate {
        return TransitionType::Wipe;
    }

    if delta_mad > 28.0 {
        if compositional_match_score > 75.0 {
            TransitionType::MatchCut
        } else if luma_b < 5.0 {
            TransitionType::FadeToBlack
        } else if luma_b > 245.0 {
            TransitionType::FadeToWhite
        } else {
            TransitionType::HardCut
        }
    } else if delta_mad > 12.0 {
        TransitionType::Dissolve
    } else {
        TransitionType::None
    }
}

/// A single continuous shot segment discovered during full-timeline streaming scan.
#[derive(Debug, Clone)]
pub struct ShotCandidateWindow {
    pub start_sec: f64,
    pub end_sec: f64,
    /// Up to 3 best interior timestamps ordered best-first for full-resolution evaluation.
    pub best_timestamps: Vec<f64>,
    pub proxy_quality: f32,
    pub avg_luma: f32,
    pub color_hist: [f32; 24],
    pub is_non_photographic: bool,
}

/// A coherent narrative/lighting scene grouping visually related photographic shots.
#[derive(Debug, Clone)]
pub struct DetectedScene {
    pub scene_index: usize,
    pub start_sec: f64,
    pub end_sec: f64,
    pub shots: Vec<ShotCandidateWindow>,
    pub is_non_photographic: bool,
}

/// Computes a normalized 24-bin RGB color histogram (8 bins/channel) and mean luma.
pub fn compute_compact_color_hist(img: &RgbImage) -> ([f32; 24], f32) {
    let (w, h) = img.dimensions();
    let total = (w * h) as usize;
    if total == 0 {
        return ([0.0; 24], 0.0);
    }

    let mut counts = [0u32; 24];
    let mut luma_sum = 0.0f64;

    for px in img.as_raw().as_chunks::<3>().0 {
        let r = px[0];
        let g = px[1];
        let b = px[2];
        counts[(r >> 5) as usize] += 1;
        counts[8 + (g >> 5) as usize] += 1;
        counts[16 + (b >> 5) as usize] += 1;
        luma_sum += (0.2126 * r as f32 + 0.7152 * g as f32 + 0.0722 * b as f32) as f64;
    }

    let inv = 1.0 / (total as f32 * 3.0);
    let mut hist = [0.0f32; 24];
    for (i, &c) in counts.iter().enumerate() {
        hist[i] = (c as f32) * inv;
    }

    (hist, (luma_sum / total as f64) as f32)
}

/// Computes L1 histogram distance in [0.0, 2.0] between two compact color histograms.
pub fn histogram_l1_distance(a: &[f32; 24], b: &[f32; 24]) -> f32 {
    a.iter().zip(b.iter()).map(|(x, y)| (x - y).abs()).sum()
}

/// Groups contiguous shot windows into photographic scenes while stripping non-photographic
/// title cards, credits, and black leaders (which act as hard scene separators).
///
/// Returns `(photographic_scenes, non_photographic_shot_count)`.
pub fn group_shots_into_scenes(shots: Vec<ShotCandidateWindow>) -> (Vec<DetectedScene>, usize) {
    let mut scenes: Vec<DetectedScene> = Vec::new();
    let mut non_photo_count = 0usize;
    let mut active_hist = [0.0f32; 24];
    let mut active_luma = 0.0f32;
    let mut had_non_photo_break = false;

    for shot in shots {
        if shot.is_non_photographic {
            non_photo_count += 1;
            had_non_photo_break = true;
            continue;
        }

        let start_new_scene = if let Some(curr) = scenes.last() {
            let last_shot_end = curr.shots.last().map(|s| s.end_sec).unwrap_or(curr.end_sec);
            let time_gap = shot.start_sec - last_shot_end;
            let hist_dist = histogram_l1_distance(&active_hist, &shot.color_hist);
            let luma_jump = (active_luma - shot.avg_luma).abs();
            let scene_dur = shot.end_sec - curr.start_sec;

            had_non_photo_break
                || time_gap > 2.5
                || hist_dist > 0.48
                || (luma_jump > 42.0 && hist_dist > 0.32)
                || scene_dur > 90.0
        } else {
            true
        };

        had_non_photo_break = false;

        if start_new_scene {
            let idx = scenes.len() + 1;
            active_hist = shot.color_hist;
            active_luma = shot.avg_luma;
            scenes.push(DetectedScene {
                scene_index: idx,
                start_sec: shot.start_sec,
                end_sec: shot.end_sec,
                shots: vec![shot],
                is_non_photographic: false,
            });
        } else if let Some(curr) = scenes.last_mut() {
            curr.end_sec = curr.end_sec.max(shot.end_sec);
            for (h, s) in active_hist.iter_mut().zip(shot.color_hist.iter()) {
                *h = 0.75 * *h + 0.25 * *s;
            }
            active_luma = 0.75 * active_luma + 0.25 * shot.avg_luma;
            curr.shots.push(shot);
        }
    }

    (scenes, non_photo_count)
}
