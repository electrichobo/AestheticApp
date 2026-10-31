//! Color Physics and Gamut Analysis
//!
//! Color temperature estimation (Kelvin), ΔE2000 / CIE distance,
//! saturation distribution, palette entropy, and CIE 1931 gamut coverage.

use aesthetic_models::physics::ColorPhysics;
use image::RgbImage;

// CIE 1931 Primaries in (x, y) coordinates
const SRGB_TRIANGLE: [(f32, f32); 3] = [(0.640, 0.330), (0.300, 0.600), (0.150, 0.060)];
const P3_TRIANGLE: [(f32, f32); 3] = [(0.680, 0.320), (0.265, 0.690), (0.150, 0.060)];
const REC2020_TRIANGLE: [(f32, f32); 3] = [(0.708, 0.292), (0.170, 0.797), (0.131, 0.046)];

/// Analyze color physics for an RGB image.
pub fn analyze_color(img: &RgbImage) -> ColorPhysics {
    let (width, height) = img.dimensions();
    let total = (width * height) as usize;
    if total == 0 {
        return ColorPhysics::default();
    }

    let mut sum_r = 0.0f64;
    let mut sum_g = 0.0f64;
    let mut sum_b = 0.0f64;
    let mut sum_sat = 0.0f32;

    // Palette 3D histogram (8x8x8 bins = 512 bins) for Shannon entropy
    let mut color_bins = [0u32; 512];

    let mut srgb_inside = 0usize;
    let mut p3_inside = 0usize;
    let mut rec2020_inside = 0usize;

    // Split-toning chromatic accumulation (Cb, Cr vectors for highlights vs shadows)
    let mut hi_cr_sum = 0.0f64;
    let mut hi_cb_sum = 0.0f64;
    let mut hi_count = 0usize;

    let mut sh_cr_sum = 0.0f64;
    let mut sh_cb_sum = 0.0f64;
    let mut sh_count = 0usize;

    for pixel in img.pixels() {
        let r = pixel[0] as f32;
        let g = pixel[1] as f32;
        let b = pixel[2] as f32;

        sum_r += r as f64;
        sum_g += g as f64;
        sum_b += b as f64;

        let luma = 0.2126 * r + 0.7152 * g + 0.0722 * b;
        let cb = (b - luma) as f64;
        let cr = (r - luma) as f64;

        if luma > 170.0 {
            hi_cr_sum += cr;
            hi_cb_sum += cb;
            hi_count += 1;
        } else if luma < 70.0 {
            sh_cr_sum += cr;
            sh_cb_sum += cb;
            sh_count += 1;
        }

        // Saturation in HSV space: (max - min) / max
        let max_c = r.max(g).max(b);
        let min_c = r.min(g).min(b);
        let sat = if max_c > 1e-3 {
            (max_c - min_c) / max_c
        } else {
            0.0
        };
        sum_sat += sat;

        // Quantize to 8 bins per channel (0..8)
        let r_bin = (pixel[0] >> 5) as usize;
        let g_bin = (pixel[1] >> 5) as usize;
        let b_bin = (pixel[2] >> 5) as usize;
        let bin_idx = (r_bin << 6) | (g_bin << 3) | b_bin;
        color_bins[bin_idx] += 1;

        // CIE 1931 xy coordinates
        let (x, y) = srgb_to_cie_xy(pixel[0], pixel[1], pixel[2]);
        if is_inside_triangle(x, y, &SRGB_TRIANGLE) {
            srgb_inside += 1;
        }
        if is_inside_triangle(x, y, &P3_TRIANGLE) {
            p3_inside += 1;
        }
        if is_inside_triangle(x, y, &REC2020_TRIANGLE) {
            rec2020_inside += 1;
        }
    }

    let n = total as f64;
    let mean_r = (sum_r / n) as f32;
    let mean_g = (sum_g / n) as f32;
    let mean_b = (sum_b / n) as f32;
    let saturation_mean = (sum_sat / total as f32) * 100.0;

    // Palette Shannon entropy
    let mut entropy = 0.0f32;
    for &count in &color_bins {
        if count > 0 {
            let p = count as f32 / total as f32;
            entropy -= p * p.log2();
        }
    }

    // Color temperature estimation:
    // McCamy formula proxy from mean B/R ratio
    let b_r_ratio = if mean_r > 1.0 { mean_b / mean_r } else { 1.0 };
    let estimated_kelvin = (b_r_ratio * 4500.0 + 1000.0).clamp(2000.0, 12000.0);

    // WB deviation from standard daylight (5600K)
    let wb_deviation = (estimated_kelvin - 5600.0).abs() / 56.0;

    // Delta E proxy from D65 white point in normalized RGB space
    let d65_r = 255.0 * 0.9504;
    let d65_g = 255.0 * 1.0000;
    let d65_b = 255.0 * 1.0888;
    let delta_e_d65 =
        (((mean_r - d65_r).powi(2) + (mean_g - d65_g).powi(2) + (mean_b - d65_b).powi(2)) / 3.0)
            .sqrt()
            / 2.55;

    let gamut_coverage_srgb = (srgb_inside as f32 / total as f32) * 100.0;
    let gamut_coverage_p3 = (p3_inside as f32 / total as f32) * 100.0;
    let gamut_coverage_rec2020 = (rec2020_inside as f32 / total as f32) * 100.0;

    // Harmonic Split-Toning Angle
    let (split_toning_deg, harmonic_score) = if hi_count > 10 && sh_count > 10 {
        let hi_cr = hi_cr_sum / hi_count as f64;
        let hi_cb = hi_cb_sum / hi_count as f64;
        let sh_cr = sh_cr_sum / sh_count as f64;
        let sh_cb = sh_cb_sum / sh_count as f64;

        let norm_hi = (hi_cr * hi_cr + hi_cb * hi_cb).sqrt();
        let norm_sh = (sh_cr * sh_cr + sh_cb * sh_cb).sqrt();

        if norm_hi > 1.5 && norm_sh > 1.5 {
            let dot = (hi_cr * sh_cr + hi_cb * sh_cb) / (norm_hi * norm_sh);
            let angle = dot.clamp(-1.0, 1.0).acos() * 180.0 / std::f64::consts::PI;
            // Reward complementary split-toning angles (140 - 180 deg)
            let harmony =
                ((angle as f32 / 180.0) * 60.0 + (entropy.min(5.0) * 8.0)).clamp(0.0, 100.0);
            (angle as f32, harmony)
        } else {
            (0.0, (entropy.min(5.0) * 12.0).clamp(0.0, 100.0))
        }
    } else {
        (0.0, 50.0)
    };

    ColorPhysics {
        estimated_kelvin,
        wb_deviation,
        saturation_mean,
        palette_entropy: entropy,
        delta_e_d65,
        skin_tone_delta_e: None,
        gamut_coverage_srgb,
        gamut_coverage_p3,
        gamut_coverage_rec2020,
        split_toning_separation_deg: split_toning_deg,
        harmonic_palette_score: harmonic_score,
    }
}

/// Convert sRGB 8-bit to CIE 1931 xy coordinates.
fn srgb_to_cie_xy(r: u8, g: u8, b: u8) -> (f32, f32) {
    let to_linear = |val: u8| -> f32 {
        let v = val as f32 / 255.0;
        if v <= 0.04045 {
            v / 12.92
        } else {
            ((v + 0.055) / 1.055).powf(2.4)
        }
    };

    let lr = to_linear(r);
    let lg = to_linear(g);
    let lb = to_linear(b);

    // sRGB to XYZ matrix
    let x = 0.4124564 * lr + 0.3575761 * lg + 0.1804375 * lb;
    let y = 0.2126729 * lr + 0.7151522 * lg + 0.0721750 * lb;
    let z = 0.0193339 * lr + 0.119_192 * lg + 0.9503041 * lb;

    let sum = x + y + z;
    if sum > 1e-4 {
        (x / sum, y / sum)
    } else {
        (0.3127, 0.3290) // D65 white point fallback
    }
}

/// Test if point (px, py) lies inside triangle defined by 3 vertices.
fn is_inside_triangle(px: f32, py: f32, tri: &[(f32, f32); 3]) -> bool {
    let sign = |p1: (f32, f32), p2: (f32, f32), p3: (f32, f32)| -> f32 {
        (p1.0 - p3.0) * (p2.1 - p3.1) - (p2.0 - p3.0) * (p1.1 - p3.1)
    };

    let p = (px, py);
    let d1 = sign(p, tri[0], tri[1]);
    let d2 = sign(p, tri[1], tri[2]);
    let d3 = sign(p, tri[2], tri[0]);

    let has_neg = (d1 < 0.0) || (d2 < 0.0) || (d3 < 0.0);
    let has_pos = (d1 > 0.0) || (d2 > 0.0) || (d3 > 0.0);

    !(has_neg && has_pos)
}
