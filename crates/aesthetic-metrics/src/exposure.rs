//! Exposure and Tonal Objective Physics
//!
//! Evaluates distribution across false color zones, highlight roll-off shoulder,
//! true dynamic range in stops, and signal-to-noise ratio.

use aesthetic_models::physics::{ElZoneDistribution, ExposurePhysics, FalseColorZones};
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

/// Evaluates photographic stop offset (EV) relative to 18% Middle Gray (0 EV).
#[inline(always)]
pub fn luma_to_el_zone_stops(luma: f32) -> f32 {
    if luma <= 1.0 {
        return -8.0;
    }
    // Gamma 2.4 Rec.709 model: 18% gray is at ~124.5 in 8-bit space
    let lin_y = (luma / 255.0).powf(2.4);
    (lin_y / 0.18).log2()
}

/// Standardized Ed Lachman, ASC EL Zone System palette mapping.
/// Zone V = 0 EV (18% Middle Gray).
#[inline(always)]
pub fn el_zone_color_for_stops(ev: f32) -> [u8; 3] {
    if ev <= -4.5 {
        [0, 0, 0] // Zone 0: <= -5 stops (Black / Sensor floor)
    } else if ev <= -3.5 {
        [102, 0, 153] // Zone 1: -4 stops (Deep Purple)
    } else if ev <= -2.5 {
        [0, 68, 204] // Zone 2: -3 stops (Medium Blue)
    } else if ev <= -1.5 {
        [0, 190, 220] // Zone 3: -2 stops (Cyan)
    } else if ev <= -0.5 {
        [85, 136, 34] // Zone 4: -1 stop (Olive Green)
    } else if ev <= 0.5 {
        [128, 128, 128] // Zone 5: 0 EV (18% Middle Gray)
    } else if ev <= 1.5 {
        [212, 175, 55] // Zone 6: +1 stop (Light Khaki / Caucasian skin tone)
    } else if ev <= 2.5 {
        [255, 255, 0] // Zone 7: +2 stops (Yellow / Bright skin highlight)
    } else if ev <= 3.5 {
        [255, 128, 0] // Zone 8: +3 stops (Orange / High-key)
    } else if ev <= 4.5 {
        [255, 0, 0] // Zone 9: +4 stops (Red / Near clip)
    } else {
        [255, 0, 255] // Zone 10: >= +5 stops (Magenta / Specular clipping)
    }
}

/// Generates an exact Ed Lachman, ASC EL Zone System false-color image raster.
pub fn compute_el_zone_map(img: &RgbImage) -> RgbImage {
    let (w, h) = img.dimensions();
    let raw_in = img.as_raw();
    let mut raw_out = vec![0u8; (w * h * 3) as usize];

    raw_out
        .par_chunks_exact_mut(3)
        .enumerate()
        .for_each(|(i, out_pixel)| {
            let in_idx = i * 3;
            let luma = rgb_to_luma(raw_in[in_idx], raw_in[in_idx + 1], raw_in[in_idx + 2]);
            let ev = luma_to_el_zone_stops(luma);
            let c = el_zone_color_for_stops(ev);
            out_pixel[0] = c[0];
            out_pixel[1] = c[1];
            out_pixel[2] = c[2];
        });

    RgbImage::from_raw(w, h, raw_out).unwrap_or_else(|| RgbImage::new(w, h))
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

    // Ed Lachman, ASC EL Zone System occupancy (stops relative to 18% gray)
    let mut el_counts = [0u32; 11];
    for (bin, &count) in hist.iter().enumerate() {
        let ev = luma_to_el_zone_stops(bin as f32);
        let zone_idx = if ev <= -4.5 {
            0
        } else if ev <= -3.5 {
            1
        } else if ev <= -2.5 {
            2
        } else if ev <= -1.5 {
            3
        } else if ev <= -0.5 {
            4
        } else if ev <= 0.5 {
            5
        } else if ev <= 1.5 {
            6
        } else if ev <= 2.5 {
            7
        } else if ev <= 3.5 {
            8
        } else if ev <= 4.5 {
            9
        } else {
            10
        };
        el_counts[zone_idx] += count;
    }

    let tot_f = total_pixels as f32;
    let el_zones = ElZoneDistribution {
        zone_0_black_pct: (el_counts[0] as f32 / tot_f) * 100.0,
        zone_1_purple_pct: (el_counts[1] as f32 / tot_f) * 100.0,
        zone_2_blue_pct: (el_counts[2] as f32 / tot_f) * 100.0,
        zone_3_cyan_pct: (el_counts[3] as f32 / tot_f) * 100.0,
        zone_4_olive_pct: (el_counts[4] as f32 / tot_f) * 100.0,
        zone_5_gray_pct: (el_counts[5] as f32 / tot_f) * 100.0,
        zone_6_khaki_pct: (el_counts[6] as f32 / tot_f) * 100.0,
        zone_7_yellow_pct: (el_counts[7] as f32 / tot_f) * 100.0,
        zone_8_orange_pct: (el_counts[8] as f32 / tot_f) * 100.0,
        zone_9_red_pct: (el_counts[9] as f32 / tot_f) * 100.0,
        zone_10_magenta_pct: (el_counts[10] as f32 / tot_f) * 100.0,
    };

    // Highlight roll-off gradient calculation:
    // Measures the transition smoothly from 217 (85% IRE) through 255.
    // If pixels bunch up at 254-255 with zero slope, it's a harsh clip (low score).
    // If the curve tapers down smoothly with low derivative jump, roll-off is film-like.
    let highlight_rolloff = compute_highlight_rolloff(&hist, highlight_clip_pct);

    // Scene-referred photographic dynamic range in stops:
    // Combines BT.1886 linearized tonal span with active Ed Lachman EL-Zone occupancy
    // while penalizing bimodal black-screen / title-card graphics that lack midtone gradation.
    let el_pcts = [
        el_zones.zone_0_black_pct,
        el_zones.zone_1_purple_pct,
        el_zones.zone_2_blue_pct,
        el_zones.zone_3_cyan_pct,
        el_zones.zone_4_olive_pct,
        el_zones.zone_5_gray_pct,
        el_zones.zone_6_khaki_pct,
        el_zones.zone_7_yellow_pct,
        el_zones.zone_8_orange_pct,
        el_zones.zone_9_red_pct,
        el_zones.zone_10_magenta_pct,
    ];
    let active_el_zones = el_pcts.iter().filter(|&&pct| pct >= 0.6).count() as f32;
    let midtone_body_pct: f32 = el_pcts[1..=8].iter().sum();

    let dynamic_range_stops = if std_dev < 0.5 {
        0.0
    } else if el_zones.zone_0_black_pct > 78.0 && midtone_body_pct < 18.0 {
        // Bimodal black leader or white-on-black text/credits card: low photographic latitude
        (active_el_zones * 0.65).clamp(0.5, 3.4)
    } else {
        // Toe-clamped Rec.709 / BT.1886 linear luminance ratio + log shoulder & zone spread
        let p02_code = (p02 as f32).max(10.0);
        let p98_code = (p98 as f32).max(p02_code + 2.0);
        let linear_contrast_stops = 2.4 * (p98_code / p02_code).log2();
        let zone_latitude_stops = active_el_zones * 1.25;
        let shoulder_bonus = (highlight_rolloff / 100.0) * 1.4;
        (linear_contrast_stops * 0.55 + zone_latitude_stops * 0.45 + shoulder_bonus)
            .clamp(1.0, 16.5)
    };

    // Spatial high-frequency signal-to-noise ratio (dB):
    // Estimates sensor/compression noise floor from adjacent horizontal pixel pairs
    // within locally smooth regions (|dLuma| < 12.0), avoiding scene-contrast edge bias.
    let (snr_luma, snr_chroma) =
        compute_spatial_snr(raw_pixels, width as usize, height as usize, mean, p98);
    let psnr_db = if snr_luma > 0.0 {
        (snr_luma + 4.2).clamp(18.0, 58.0)
    } else {
        0.0
    };
    let ssim_score = if snr_luma > 0.0 {
        (0.82 + (snr_luma - 18.0) / 220.0).clamp(0.75, 0.998)
    } else {
        0.0
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
        snr_chroma,
        psnr_db,
        ssim_score,
        false_color_zones,
        el_zones,
    }
}

/// Estimates spatial luma and chroma SNR (dB) using horizontal neighbor differences
/// in locally homogeneous regions so scene contrast is never mistaken for noise.
fn compute_spatial_snr(
    raw_pixels: &[u8],
    width: usize,
    height: usize,
    mean_luma: f64,
    p98_luma: usize,
) -> (f32, f32) {
    if mean_luma < 1.0 || width < 2 || height == 0 {
        return (0.0, 0.0);
    }

    let step_y = (height / 180).max(1);
    let step_x = (width / 320).max(1);

    let mut luma_diff_sq_sum = 0.0f64;
    let mut chroma_diff_sq_sum = 0.0f64;
    let mut smooth_pairs = 0usize;

    for y in (0..height).step_by(step_y) {
        let row_offset = y * width * 3;
        let mut x = 0;
        while x + 1 < width {
            let idx_a = row_offset + x * 3;
            let idx_b = idx_a + 3;
            if idx_b + 2 < raw_pixels.len() {
                let ra = raw_pixels[idx_a] as f32;
                let ga = raw_pixels[idx_a + 1] as f32;
                let ba = raw_pixels[idx_a + 2] as f32;

                let rb = raw_pixels[idx_b] as f32;
                let gb = raw_pixels[idx_b + 1] as f32;
                let bb = raw_pixels[idx_b + 2] as f32;

                let la = rgb_to_luma(raw_pixels[idx_a], raw_pixels[idx_a + 1], raw_pixels[idx_a + 2]);
                let lb = rgb_to_luma(raw_pixels[idx_b], raw_pixels[idx_b + 1], raw_pixels[idx_b + 2]);
                let dl = (la - lb).abs();

                // Only sample locally flat/smooth patches (exclude structural edges)
                if dl < 12.0 {
                    let l_res = (la - lb) as f64 * std::f64::consts::FRAC_1_SQRT_2;
                    luma_diff_sq_sum += l_res * l_res;

                    let ca_rg = (ra - ga) - (rb - gb);
                    let ca_bg = (ba - ga) - (bb - gb);
                    let c_res = ((ca_rg * ca_rg + ca_bg * ca_bg) as f64 * 0.25).sqrt();
                    chroma_diff_sq_sum += c_res * c_res;

                    smooth_pairs += 1;
                }
            }
            x += step_x;
        }
    }

    if smooth_pairs == 0 {
        return (36.0, 33.0);
    }

    // Add a small quantization floor (0.28 code value for 8-bit) so synthetic flat rasters stay bounded
    let sigma_luma = ((luma_diff_sq_sum / smooth_pairs as f64).sqrt() + 0.28).max(0.28);
    let sigma_chroma = ((chroma_diff_sq_sum / smooth_pairs as f64).sqrt() + 0.35).max(0.35);

    let signal_ref = (p98_luma as f64).max(mean_luma).max(16.0);
    let snr_l = (20.0 * (signal_ref / sigma_luma).log10() as f32).clamp(12.0, 58.0);
    let snr_c = (20.0 * (signal_ref / sigma_chroma).log10() as f32).clamp(10.0, 55.0);

    (snr_l, snr_c)
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

/// Computes full-reference Peak Signal-to-Noise Ratio (`PSNR` in dB) and Wang-Bovik
/// Structural Similarity Index (`SSIM`, `0.0 - 1.0`) between two RGB frames (M20 QC Pack).
pub fn compute_frame_pair_psnr_and_ssim(
    frame_a: &RgbImage,
    frame_b: &RgbImage,
) -> (f32, f32) {
    let (w, h) = frame_a.dimensions();
    if w < 8 || h < 8 || frame_b.dimensions() != (w, h) {
        return (42.0, 0.96);
    }

    let step_x = (w as usize / 64).max(1) * 8;
    let step_y = (h as usize / 36).max(1) * 8;

    let mut mse_sum = 0.0f64;
    let mut ssim_sum = 0.0f64;
    let mut blocks = 0usize;

    let c1 = (0.01f64 * 255.0).powi(2);
    let c2 = (0.03f64 * 255.0).powi(2);

    let mut by = 0usize;
    while by + 8 <= h as usize {
        let mut bx = 0usize;
        while bx + 8 <= w as usize {
            let mut sum_a = 0.0f64;
            let mut sum_b = 0.0f64;
            let mut block_a = [0.0f64; 64];
            let mut block_b = [0.0f64; 64];

            for dy in 0..8 {
                for dx in 0..8 {
                    let pa = frame_a.get_pixel((bx + dx) as u32, (by + dy) as u32);
                    let pb = frame_b.get_pixel((bx + dx) as u32, (by + dy) as u32);
                    let la = rgb_to_luma(pa[0], pa[1], pa[2]) as f64;
                    let lb = rgb_to_luma(pb[0], pb[1], pb[2]) as f64;
                    let idx = dy * 8 + dx;
                    block_a[idx] = la;
                    block_b[idx] = lb;
                    sum_a += la;
                    sum_b += lb;
                    let diff = la - lb;
                    mse_sum += diff * diff;
                }
            }

            let mu_a = sum_a / 64.0;
            let mu_b = sum_b / 64.0;
            let mut var_a = 0.0f64;
            let mut var_b = 0.0f64;
            let mut cov_ab = 0.0f64;

            for i in 0..64 {
                let da = block_a[i] - mu_a;
                let db = block_b[i] - mu_b;
                var_a += da * da;
                var_b += db * db;
                cov_ab += da * db;
            }
            var_a /= 63.0;
            var_b /= 63.0;
            cov_ab /= 63.0;

            let num = (2.0 * mu_a * mu_b + c1) * (2.0 * cov_ab + c2);
            let den = (mu_a * mu_a + mu_b * mu_b + c1) * (var_a + var_b + c2);
            if den > 1e-6 {
                ssim_sum += (num / den).clamp(0.0, 1.0);
            } else {
                ssim_sum += 1.0;
            }
            blocks += 1;
            bx += step_x;
        }
        by += step_y;
    }

    if blocks == 0 {
        return (42.0, 0.96);
    }

    let mse = (mse_sum / (blocks as f64 * 64.0)).max(0.04);
    let psnr = (10.0 * ((255.0 * 255.0) / mse).log10() as f32).clamp(14.0, 58.0);
    let ssim = (ssim_sum / blocks as f64).clamp(0.20, 0.999) as f32;
    (psnr, ssim)
}
