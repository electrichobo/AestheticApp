//! Optical, Sharpness, and Lens Physics
//!
//! Evaluates high-frequency sharpness via discrete Laplacian convolution,
//! edge density via Sobel gradients, MTF proxy, vignetting stops, and
//! chromatic aberration fringing.

use crate::exposure::rgb_to_luma;
use aesthetic_models::physics::OpticalPhysics;
use image::RgbImage;

/// Analyze optical physics on an RGB image.
pub fn analyze_optics(img: &RgbImage) -> OpticalPhysics {
    let (width, height) = img.dimensions();
    if width < 4 || height < 4 {
        return OpticalPhysics::default();
    }

    let w = width as usize;
    let h = height as usize;

    // Convert image to a 2D luma grid for spatial filtering
    let mut luma_grid = vec![0.0f32; w * h];
    for y in 0..h {
        for x in 0..w {
            let pixel = img.get_pixel(x as u32, y as u32);
            luma_grid[y * w + x] = rgb_to_luma(pixel[0], pixel[1], pixel[2]);
        }
    }

    // 1. Laplacian Variance (high frequency focus/sharpness metric)
    // 3x3 discrete Laplace kernel:
    //  0  1  0
    //  1 -4  1
    //  0  1  0
    let mut laplacian_sum = 0.0f64;
    let mut laplacian_sq_sum = 0.0f64;
    let mut count = 0usize;

    // 2. Sobel Edge Density (horizontal + vertical gradient)
    let mut edge_count = 0usize;
    let edge_threshold = 45.0f32; // Gradient magnitude threshold

    for y in 1..(h - 1) {
        let row_curr = y * w;
        let row_prev = (y - 1) * w;
        let row_next = (y + 1) * w;

        for x in 1..(w - 1) {
            // Laplacian
            let center = luma_grid[row_curr + x];
            let top = luma_grid[row_prev + x];
            let bottom = luma_grid[row_next + x];
            let left = luma_grid[row_curr + (x - 1)];
            let right = luma_grid[row_curr + (x + 1)];

            let lap = (top + bottom + left + right - 4.0 * center) as f64;
            laplacian_sum += lap;
            laplacian_sq_sum += lap * lap;
            count += 1;

            // Sobel gradients
            let tl = luma_grid[row_prev + (x - 1)];
            let tr = luma_grid[row_prev + (x + 1)];
            let bl = luma_grid[row_next + (x - 1)];
            let br = luma_grid[row_next + (x + 1)];

            let gx = (-tl + tr - 2.0 * left + 2.0 * right - bl + br).abs();
            let gy = (-tl - 2.0 * top - tr + bl + 2.0 * bottom + br).abs();
            let grad_mag = (gx * gx + gy * gy).sqrt();

            if grad_mag > edge_threshold {
                edge_count += 1;
            }
        }
    }

    let laplacian_variance = if count > 0 {
        let mean = laplacian_sum / (count as f64);
        ((laplacian_sq_sum / (count as f64)) - (mean * mean)).max(0.0) as f32
    } else {
        0.0
    };

    let edge_density = if count > 0 {
        (edge_count as f32 / count as f32) * 100.0
    } else {
        0.0
    };

    // MTF Proxy: Normalized estimate based on high-frequency edge transition steepness
    let mtf_proxy = (laplacian_variance.sqrt() * 1.5).min(100.0);

    // 3. Center-to-Corner Vignetting Falloff (in stops)
    let center_x = w / 2;
    let center_y = h / 2;
    let center_rad = (w.min(h) / 8).max(1);

    let mut center_luma_sum = 0.0f32;
    let mut center_pixels = 0usize;

    for dy in (center_y.saturating_sub(center_rad))..=(center_y + center_rad).min(h - 1) {
        for dx in (center_x.saturating_sub(center_rad))..=(center_x + center_rad).min(w - 1) {
            center_luma_sum += luma_grid[dy * w + dx];
            center_pixels += 1;
        }
    }
    let center_mean = if center_pixels > 0 {
        center_luma_sum / center_pixels as f32
    } else {
        1.0
    };

    // Average the four corner patches
    let corner_size = (w.min(h) / 12).max(1);
    let mut corner_luma_sum = 0.0f32;
    let mut corner_pixels = 0usize;

    let corners = [
        (0, 0),
        (w - corner_size, 0),
        (0, h - corner_size),
        (w - corner_size, h - corner_size),
    ];

    for &(cx, cy) in &corners {
        for dy in cy..(cy + corner_size).min(h) {
            for dx in cx..(cx + corner_size).min(w) {
                corner_luma_sum += luma_grid[dy * w + dx];
                corner_pixels += 1;
            }
        }
    }
    let corner_mean = if corner_pixels > 0 {
        corner_luma_sum / corner_pixels as f32
    } else {
        1.0
    };

    // Vignetting falloff in optical stops: log2(center / corner)
    let vignetting_stops = if corner_mean > 0.1 && center_mean > corner_mean {
        (center_mean / corner_mean).log2().max(0.0)
    } else {
        0.0
    };

    // 4. Chromatic Aberration Fringe Width (proxy)
    // Measures color fringe separation on high-contrast edges
    let ca_width_px = compute_chromatic_aberration(img, w, h);

    OpticalPhysics {
        sharpness_laplacian: laplacian_variance,
        edge_density,
        mtf_proxy,
        vignetting_stops,
        chromatic_aberration_px: ca_width_px,
    }
}

/// Estimates chromatic aberration fringe width in pixels by comparing R vs B edge shifts.
fn compute_chromatic_aberration(img: &RgbImage, w: usize, h: usize) -> f32 {
    let mut shift_sum = 0.0f32;
    let mut samples = 0usize;

    // Sample high-contrast radial edges near perimeter
    let step = 8;
    for y in (step..(h - step)).step_by(step) {
        for x in (step..(w - step)).step_by(step) {
            let p_prev = img.get_pixel((x - 1) as u32, y as u32);
            let p_curr = img.get_pixel(x as u32, y as u32);
            let p_next = img.get_pixel((x + 1) as u32, y as u32);

            let r_diff = (p_next[0] as f32 - p_prev[0] as f32).abs();
            let b_diff = (p_next[2] as f32 - p_prev[2] as f32).abs();

            if r_diff > 60.0 && b_diff > 60.0 {
                let r_grad = p_curr[0] as f32 - p_prev[0] as f32;
                let b_grad = p_curr[2] as f32 - p_prev[2] as f32;
                let fringe = (r_grad - b_grad).abs() / 255.0;
                shift_sum += fringe;
                samples += 1;
            }
        }
    }

    if samples > 0 {
        (shift_sum / samples as f32) * 5.0 // normalized pixel width proxy
    } else {
        0.0
    }
}
