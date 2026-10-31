//! Exposure and Tonal Objective Physics
//!
//! Evaluates distribution across false color zones, highlight roll-off shoulder,
//! true dynamic range in stops, and signal-to-noise ratio.

use aesthetic_models::physics::{ExposurePhysics, FalseColorZones};
use image::RgbImage;
use rayon::prelude::*;

const LUMA_R: f32 = 0.2126;
const LUMA_G: f32 = 0.7152;
const LUMA_B: f32 = 0.0722;

/// Compute ITU-R BT.709 perceived luminance for an RGB pixel.
#[inline(always)]
pub fn rgb_to_luma(r: u8, g: u8, b: u8) -> f32 {
    LUMA_R * (r as f32) + LUMA_G * (g as f32) + LUMA_B * (b as f32)
}

/// Analyze exposure physics for an RGB image.
pub fn analyze_exposure(img: &RgbImage) -> ExposurePhysics {
    let (width, height) = img.dimensions();
    let total_pixels = (width * height) as usize;
    if total_pixels == 0 {
        return ExposurePhysics::default();
    }

    // Parallel histogram aggregation across pixel chunks
    let raw_pixels = img.as_raw();
    let num_threads = rayon::current_num_threads().max(1);
    let chunk_size = (total_pixels / num_threads).max(1024);

    let hist = raw_pixels
        .par_chunks(chunk_size * 3)
        .fold(
            || [0u32; 256],
            |mut local_hist, chunk| {
                for rgb in chunk.as_chunks::<3>().0 {
                    let luma = rgb_to_luma(rgb[0], rgb[1], rgb[2]);
                    let bin = (luma.round() as usize).clamp(0, 255);
                    local_hist[bin] += 1;
                }
                local_hist
            },
        )
        .reduce(
            || [0u32; 256],
            |mut a, b| {
                for i in 0..256 {
                    a[i] += b[i];
                }
                a
            },
        );

    // Compute basic statistics
    let n = total_pixels as f64;
    let mut sum = 0.0f64;
    for (bin, &count) in hist.iter().enumerate() {
        sum += (bin as f64) * (count as f64);
    }
    let mean = sum / n;

    let mut variance_sum = 0.0f64;
    let mut m3_sum = 0.0f64;
    let mut m4_sum = 0.0f64;

    for (bin, &count) in hist.iter().enumerate() {
        let diff = (bin as f64) - mean;
        let count_f = count as f64;
        variance_sum += diff * diff * count_f;
        m3_sum += diff * diff * diff * count_f;
        m4_sum += diff * diff * diff * diff * count_f;
    }

    let variance = variance_sum / n;
    let std_dev = variance.sqrt();

    let skewness = if std_dev > 1e-4 {
        (m3_sum / n) / (std_dev * std_dev * std_dev)
    } else {
        0.0
    };

    let kurtosis = if std_dev > 1e-4 {
        ((m4_sum / n) / (variance * variance)) - 3.0 // Excess kurtosis
    } else {
        0.0
    };

    // Find median, p02, and p98
    let mut cum_sum = 0usize;
    let median_thresh = total_pixels / 2;
    let p02_thresh = (total_pixels as f64 * 0.02) as usize;
    let p98_thresh = (total_pixels as f64 * 0.98) as usize;

    let mut median = 0usize;
    let mut p02 = 0usize;
    let mut p98 = 255usize;

    for (bin, &count) in hist.iter().enumerate() {
        let prev = cum_sum;
        cum_sum += count as usize;
        if prev <= p02_thresh && cum_sum > p02_thresh {
            p02 = bin;
        }
        if prev <= median_thresh && cum_sum > median_thresh {
            median = bin;
        }
        if prev <= p98_thresh && cum_sum > p98_thresh {
            p98 = bin;
        }
    }

    // Clipping percentages
    let shadow_clipped_pixels: u32 = hist[..=5].iter().sum();
    let highlight_clipped_pixels: u32 = hist[250..].iter().sum();

    let shadow_clip_pct = (shadow_clipped_pixels as f32 / total_pixels as f32) * 100.0;
    let highlight_clip_pct = (highlight_clipped_pixels as f32 / total_pixels as f32) * 100.0;

    // False color zone occupancy
    let black_clip_count: u32 = hist[..5].iter().sum();
    let shadow_count: u32 = hist[5..=51].iter().sum();
    let middle_gray_count: u32 = hist[89..=115].iter().sum();
    let skin_count: u32 = hist[128..=166].iter().sum();
    let highlight_count: u32 = hist[179..=230].iter().sum();
    let specular_count: u32 = hist[250..].iter().sum();

    let false_color_zones = FalseColorZones {
        black_clip_pct: (black_clip_count as f32 / total_pixels as f32) * 100.0,
        shadow_zone_pct: (shadow_count as f32 / total_pixels as f32) * 100.0,
        middle_gray_pct: (middle_gray_count as f32 / total_pixels as f32) * 100.0,
        skin_zone_pct: (skin_count as f32 / total_pixels as f32) * 100.0,
        highlight_zone_pct: (highlight_count as f32 / total_pixels as f32) * 100.0,
        specular_clip_pct: (specular_count as f32 / total_pixels as f32) * 100.0,
    };

    // Highlight roll-off gradient calculation:
    // Measures the transition smoothly from 217 (85% IRE) through 255.
    // If pixels bunch up at 254-255 with zero slope, it's a harsh clip (low score).
    // If the curve tapers down smoothly with low derivative jump, roll-off is film-like.
    let highlight_rolloff = compute_highlight_rolloff(&hist, highlight_clip_pct);

    // Dynamic range stops (log2 ratio between p98 and p02)
    let p02_eff = (p02 as f32).max(1.0);
    let p98_eff = (p98 as f32).max(p02_eff + 1.0);
    let dynamic_range_stops = (p98_eff / p02_eff).log2();

    // Signal-to-noise ratio estimate (mean / std dev in dB)
    let snr_luma = if std_dev > 1e-3 {
        20.0 * (mean / std_dev).log10() as f32
    } else {
        60.0
    };

    ExposurePhysics {
        histogram_mean: mean as f32,
        histogram_median: median as f32,
        histogram_std: std_dev as f32,
        histogram_skew: skewness as f32,
        histogram_kurtosis: kurtosis as f32,
        highlight_clip_pct,
        shadow_clip_pct,
        highlight_rolloff,
        dynamic_range_stops,
        snr_luma,
        snr_chroma: snr_luma * 0.9, // baseline proxy until full chroma patch analysis
        false_color_zones,
    }
}

/// Evaluates highlight roll-off quality (0.0 = hard digital ceiling, 100.0 = smooth Alexa-like shoulder).
fn compute_highlight_rolloff(hist: &[u32; 256], clip_pct: f32) -> f32 {
    let top_zone: u32 = hist[217..254].iter().sum();
    let ceiling: u32 = hist[254..=255].iter().sum();

    if top_zone == 0 && ceiling == 0 {
        return 100.0; // No highlight stress in frame
    }

    // Harshness penalty based on ceiling spikes vs shoulder gradation
    let ceiling_ratio = ceiling as f32 / (top_zone + ceiling) as f32;
    let base_score = (1.0 - ceiling_ratio) * 100.0;

    // Heavily penalize abrupt digital hard-stops if clipping occurs
    (base_score - (clip_pct * 3.0)).clamp(0.0, 100.0)
}
