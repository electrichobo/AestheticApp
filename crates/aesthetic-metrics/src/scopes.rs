//! Broadcast Scopes Engine
//!
//! Generates real-time broadcast-grade scopes:
//! 1. Luma Waveform (100 IRE with phosphor glow)
//! 2. RGB Parade (R, G, B channels separated)
//! 3. Vectorscope (Cb/Cr circular plane with skin tone line & color targets)
//! 4. RGB & Luma Histograms (256 bins with clipping)
//! 5. CIE 1931 Chromaticity Map (xy locus with sRGB, P3, Rec.2020 overlays)

use crate::exposure::rgb_to_luma;
use image::RgbImage;
use serde::{Deserialize, Serialize};

/// Luma Waveform density representation (IRE 0 to 100 across frame columns).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LumaWaveform {
    pub columns: usize,
    pub ire_levels: usize, // typically 100 (0 to 100 IRE)
    pub density: Vec<f32>,
}

/// RGB Parade density representation (Red, Green, Blue columns separated).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RgbParade {
    pub columns: usize,
    pub ire_levels: usize,
    pub r_density: Vec<f32>,
    pub g_density: Vec<f32>,
    pub b_density: Vec<f32>,
}

/// Circular Vectorscope density representation (Cb horizontal, Cr vertical).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Vectorscope {
    pub resolution: usize, // e.g. 128 or 256
    pub density: Vec<f32>,
    pub skin_tone_angle_deg: f32, // standard central I-line (~57.0 degrees)
    #[serde(default = "default_skin_min")]
    pub skin_tone_cone_min_deg: f32, // inclusive multi-ethnic cone start (~48.0 degrees)
    #[serde(default = "default_skin_max")]
    pub skin_tone_cone_max_deg: f32, // inclusive multi-ethnic cone end (~66.0 degrees)
}

fn default_skin_min() -> f32 {
    48.0
}

fn default_skin_max() -> f32 {
    66.0
}

/// 256-bucket Histogram for Luma and individual RGB channels.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChannelHistogram {
    #[serde(with = "serde_arrays")]
    pub luma: [u32; 256],
    #[serde(with = "serde_arrays")]
    pub r: [u32; 256],
    #[serde(with = "serde_arrays")]
    pub g: [u32; 256],
    #[serde(with = "serde_arrays")]
    pub b: [u32; 256],
}

mod serde_arrays {
    use serde::{Deserializer, Serializer};
    pub fn serialize<S>(arr: &[u32; 256], serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        use serde::ser::SerializeSeq;
        let mut seq = serializer.serialize_seq(Some(256))?;
        for elem in arr {
            seq.serialize_element(elem)?;
        }
        seq.end()
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<[u32; 256], D::Error>
    where
        D: Deserializer<'de>,
    {
        use serde::Deserialize;
        let v = Vec::<u32>::deserialize(deserializer)?;
        let mut arr = [0u32; 256];
        if v.len() == 256 {
            arr.copy_from_slice(&v);
        }
        Ok(arr)
    }
}

/// CIE 1931 Chromaticity Map density in normalized xy coordinates.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CieChromaticityMap {
    pub grid_size: usize, // e.g. 128x128
    pub density: Vec<f32>,
}

/// Compute a 100-IRE Luma Waveform from an RGB image.
pub fn compute_waveform(img: &RgbImage, num_cols: usize) -> LumaWaveform {
    let (w, h) = img.dimensions();
    let ire_levels = 100;
    if w == 0 || h == 0 || num_cols == 0 {
        return LumaWaveform {
            columns: num_cols,
            ire_levels,
            density: vec![0.0; num_cols * ire_levels],
        };
    }

    let mut raw_counts = vec![0u32; num_cols * ire_levels];
    let col_step = (w as f32) / (num_cols as f32);

    for x in 0..w {
        let col_idx = ((x as f32 / col_step) as usize).min(num_cols - 1);
        for y in 0..h {
            let p = img.get_pixel(x, y);
            let luma = rgb_to_luma(p[0], p[1], p[2]);
            let ire = ((luma / 255.0) * (ire_levels as f32 - 1.0)).round() as usize;
            raw_counts[col_idx * ire_levels + ire.min(ire_levels - 1)] += 1;
        }
    }

    let max_count = raw_counts.iter().copied().max().unwrap_or(1).max(1) as f32;
    let density: Vec<f32> = raw_counts
        .iter()
        .map(|&c| {
            if c > 0 {
                ((c as f32) / max_count).sqrt().min(1.0)
            } else {
                0.0
            }
        })
        .collect();

    LumaWaveform {
        columns: num_cols,
        ire_levels,
        density,
    }
}

/// Compute an RGB Parade scope from an RGB image.
pub fn compute_parade(img: &RgbImage, num_cols: usize) -> RgbParade {
    let (w, h) = img.dimensions();
    let ire_levels = 100;

    let mut r_counts = vec![0u32; num_cols * ire_levels];
    let mut g_counts = vec![0u32; num_cols * ire_levels];
    let mut b_counts = vec![0u32; num_cols * ire_levels];

    let col_step = (w as f32) / (num_cols as f32);

    for x in 0..w {
        let col_idx = ((x as f32 / col_step) as usize).min(num_cols - 1);
        for y in 0..h {
            let p = img.get_pixel(x, y);

            let r_ire = ((p[0] as f32 / 255.0) * (ire_levels as f32 - 1.0)).round() as usize;
            let g_ire = ((p[1] as f32 / 255.0) * (ire_levels as f32 - 1.0)).round() as usize;
            let b_ire = ((p[2] as f32 / 255.0) * (ire_levels as f32 - 1.0)).round() as usize;

            r_counts[col_idx * ire_levels + r_ire.min(ire_levels - 1)] += 1;
            g_counts[col_idx * ire_levels + g_ire.min(ire_levels - 1)] += 1;
            b_counts[col_idx * ire_levels + b_ire.min(ire_levels - 1)] += 1;
        }
    }

    let to_density = |counts: &[u32]| -> Vec<f32> {
        let max_c = counts.iter().copied().max().unwrap_or(1).max(1) as f32;
        counts
            .iter()
            .map(|&c| {
                if c > 0 {
                    ((c as f32) / max_c).sqrt().min(1.0)
                } else {
                    0.0
                }
            })
            .collect()
    };

    RgbParade {
        columns: num_cols,
        ire_levels,
        r_density: to_density(&r_counts),
        g_density: to_density(&g_counts),
        b_density: to_density(&b_counts),
    }
}

/// Compute a circular Vectorscope (Cb vs Cr) from an RGB image with broadcast chroma gain.
pub fn compute_vectorscope(img: &RgbImage, res: usize) -> Vectorscope {
    let mut counts = vec![0u32; res * res];
    let center = (res as f32) / 2.0;
    let radius = center * 0.90;
    let zoom = 2.5f32; // 2.5x broadcast chroma gain so natural cinematic tones extend legibly outward

    for p in img.pixels() {
        let r = p[0] as f32;
        let g = p[1] as f32;
        let b = p[2] as f32;

        // ITU-R BT.709 YCbCr conversion:
        // Cb = -0.1146 * R - 0.3854 * G + 0.5000 * B
        // Cr =  0.5000 * R - 0.4542 * G - 0.0458 * B
        let cb = -0.1146 * r - 0.3854 * g + 0.5000 * b; // range ~ [-128, 128]
        let cr = 0.5000 * r - 0.4542 * g - 0.0458 * b;

        let grid_x = (center + ((cb * zoom) / 128.0) * radius).round() as isize;
        let grid_y = (center - ((cr * zoom) / 128.0) * radius).round() as isize; // Invert Y for Cartesian plot

        if grid_x >= 0 && grid_x < res as isize && grid_y >= 0 && grid_y < res as isize {
            counts[(grid_y as usize) * res + (grid_x as usize)] += 1;
        }
    }

    let max_c = counts.iter().copied().max().unwrap_or(1).max(1) as f32;
    let density: Vec<f32> = counts
        .iter()
        .map(|&c| {
            if c > 0 {
                ((c as f32) / max_c).sqrt().min(1.0)
            } else {
                0.0
            }
        })
        .collect();

    Vectorscope {
        resolution: res,
        density,
        skin_tone_angle_deg: 57.0, // Standard central I-bar angle
        skin_tone_cone_min_deg: 48.0, // Inclusive melanin/hemoglobin spectrum start
        skin_tone_cone_max_deg: 66.0, // Inclusive spectrum end
    }
}

/// Compute full 256-bucket histograms for Luma, Red, Green, and Blue.
pub fn compute_histograms(img: &RgbImage) -> ChannelHistogram {
    let mut hist = ChannelHistogram {
        luma: [0; 256],
        r: [0; 256],
        g: [0; 256],
        b: [0; 256],
    };

    for p in img.pixels() {
        hist.r[p[0] as usize] += 1;
        hist.g[p[1] as usize] += 1;
        hist.b[p[2] as usize] += 1;

        let y = (rgb_to_luma(p[0], p[1], p[2]).round() as usize).clamp(0, 255);
        hist.luma[y] += 1;
    }

    hist
}

/// Compute CIE 1931 Chromaticity xy density map.
pub fn compute_cie_chromaticity_map(img: &RgbImage, grid_size: usize) -> CieChromaticityMap {
    let mut counts = vec![0u32; grid_size * grid_size];

    let to_linear = |val: u8| -> f32 {
        let v = val as f32 / 255.0;
        if v <= 0.04045 {
            v / 12.92
        } else {
            ((v + 0.055) / 1.055).powf(2.4)
        }
    };

    for p in img.pixels() {
        let lr = to_linear(p[0]);
        let lg = to_linear(p[1]);
        let lb = to_linear(p[2]);

        let x_xyz = 0.4124564 * lr + 0.3575761 * lg + 0.1804375 * lb;
        let y_xyz = 0.2126729 * lr + 0.7151522 * lg + 0.0721750 * lb;
        let z_xyz = 0.0193339 * lr + 0.119_192 * lg + 0.9503041 * lb;

        let sum = x_xyz + y_xyz + z_xyz;
        if sum > 1e-4 {
            let cx = x_xyz / sum; // 0.0 - 0.8
            let cy = y_xyz / sum; // 0.0 - 0.9

            let gx = ((cx / 0.8) * (grid_size as f32 - 1.0)).round() as isize;
            let gy = (((0.9 - cy) / 0.9) * (grid_size as f32 - 1.0)).round() as isize; // Invert Y

            if gx >= 0 && gx < grid_size as isize && gy >= 0 && gy < grid_size as isize {
                counts[(gy as usize) * grid_size + (gx as usize)] += 1;
            }
        }
    }

    let max_c = counts.iter().copied().max().unwrap_or(1).max(1) as f32;
    let density: Vec<f32> = counts
        .iter()
        .map(|&c| {
            if c > 0 {
                ((c as f32) / max_c).sqrt().min(1.0)
            } else {
                0.0
            }
        })
        .collect();

    CieChromaticityMap { grid_size, density }
}
