//! Active Picture Area & Matte Detection
//!
//! Automatically detects and crops out letterbox (top/bottom) and pillarbox (left/right)
//! black bars from finished film containers (e.g. 2.39:1 scope inside 16:9).
//! Correctly handles native aspect ratios (e.g. native 3840x1608) with zero cropping.

use crate::exposure::rgb_to_luma;
use image::RgbImage;

/// Bounding rectangle for the active cinematic picture area.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ActiveCropBounds {
    pub x: u32,
    pub y: u32,
    pub width: u32,
    pub height: u32,
}

/// Detects the active picture area, excluding black letterbox/pillarbox matting bars.
/// If footage is natively rendered without blanking, returns the full raster untouched.
pub fn detect_active_picture(img: &RgbImage) -> ActiveCropBounds {
    let (width, height) = img.dimensions();
    let full_bounds = ActiveCropBounds {
        x: 0,
        y: 0,
        width,
        height,
    };

    if width < 8 || height < 8 {
        return full_bounds;
    }

    let luma_threshold = 12.0f32; // Black bar threshold in 8-bit luma

    // Helper: average luma of a horizontal line
    let row_mean_luma = |y: u32| -> f32 {
        let step = (width / 32).max(1);
        let mut sum = 0.0f32;
        let mut count = 0;
        for x in (0..width).step_by(step as usize) {
            let p = img.get_pixel(x, y);
            sum += rgb_to_luma(p[0], p[1], p[2]);
            count += 1;
        }
        if count > 0 {
            sum / count as f32
        } else {
            0.0
        }
    };

    // Helper: average luma of a vertical line
    let col_mean_luma = |x: u32, y_start: u32, y_end: u32| -> f32 {
        let step = ((y_end - y_start) / 32).max(1);
        let mut sum = 0.0f32;
        let mut count = 0;
        for y in (y_start..=y_end).step_by(step as usize) {
            let p = img.get_pixel(x, y);
            sum += rgb_to_luma(p[0], p[1], p[2]);
            count += 1;
        }
        if count > 0 {
            sum / count as f32
        } else {
            0.0
        }
    };

    // Fast-path: Check outermost border (row 0, row H-1, col 0, col W-1)
    // If the image already fills the frame natively, bypass all scans immediately.
    let top_row_luma = row_mean_luma(0);
    let bottom_row_luma = row_mean_luma(height - 1);
    let left_col_luma = col_mean_luma(0, 0, height - 1);
    let right_col_luma = col_mean_luma(width - 1, 0, height - 1);

    if top_row_luma > luma_threshold
        && bottom_row_luma > luma_threshold
        && left_col_luma > luma_threshold
        && right_col_luma > luma_threshold
    {
        return full_bounds;
    }

    // 1. Scan from top down to find active picture top
    let mut top_y = 0u32;
    for y in 0..(height / 3) {
        if row_mean_luma(y) > luma_threshold {
            top_y = y;
            break;
        }
    }

    // 2. Scan from bottom up to find active picture bottom
    let mut bottom_y = height - 1;
    for y in ((height * 2 / 3)..height).rev() {
        if row_mean_luma(y) > luma_threshold {
            bottom_y = y;
            break;
        }
    }

    // 3. Scan from left to find active picture left
    let mut left_x = 0u32;
    for x in 0..(width / 4) {
        if col_mean_luma(x, top_y, bottom_y) > luma_threshold {
            left_x = x;
            break;
        }
    }

    // 4. Scan from right to find active picture right
    let mut right_x = width - 1;
    for x in ((width * 3 / 4)..width).rev() {
        if col_mean_luma(x, top_y, bottom_y) > luma_threshold {
            right_x = x;
            break;
        }
    }

    let active_w = right_x.saturating_sub(left_x) + 1;
    let active_h = bottom_y.saturating_sub(top_y) + 1;

    // Safety fallback: if detected crop is negligible (< 3px on all sides) or unreasonably tiny (< 50%)
    if (left_x <= 2 && top_y <= 2 && active_w >= width - 4 && active_h >= height - 4)
        || active_w < width / 2
        || active_h < height / 2
    {
        full_bounds
    } else {
        ActiveCropBounds {
            x: left_x,
            y: top_y,
            width: active_w,
            height: active_h,
        }
    }
}
