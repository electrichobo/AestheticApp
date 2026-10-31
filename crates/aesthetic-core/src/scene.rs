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
