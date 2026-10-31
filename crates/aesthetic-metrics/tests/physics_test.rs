use aesthetic_metrics::compute_objective_physics;
use image::{Rgb, RgbImage};

#[test]
fn test_exposure_pure_black() {
    let img = RgbImage::from_pixel(64, 64, Rgb([0, 0, 0]));
    let physics = compute_objective_physics(&img);

    assert_eq!(physics.exposure.histogram_mean, 0.0);
    assert_eq!(physics.exposure.shadow_clip_pct, 100.0);
    assert_eq!(physics.exposure.highlight_clip_pct, 0.0);
    assert_eq!(physics.exposure.false_color_zones.black_clip_pct, 100.0);
}

#[test]
fn test_exposure_pure_white() {
    let img = RgbImage::from_pixel(64, 64, Rgb([255, 255, 255]));
    let physics = compute_objective_physics(&img);

    assert_eq!(physics.exposure.histogram_mean, 255.0);
    assert_eq!(physics.exposure.highlight_clip_pct, 100.0);
    assert_eq!(physics.exposure.shadow_clip_pct, 0.0);
    assert_eq!(physics.exposure.false_color_zones.specular_clip_pct, 100.0);
}

#[test]
fn test_optics_sharpness_gradient() {
    // High-contrast alternating vertical stripes produce strong edge gradients
    let mut img = RgbImage::new(64, 64);
    for y in 0..64 {
        for x in 0..64 {
            let val = if (x / 4) % 2 == 0 { 255 } else { 0 };
            img.put_pixel(x, y, Rgb([val, val, val]));
        }
    }

    let physics = compute_objective_physics(&img);
    assert!(physics.optics.sharpness_laplacian > 10.0);
    assert!(physics.optics.edge_density > 20.0);
}

#[test]
fn test_color_gamut_coverage() {
    // Pure green in sRGB
    let img = RgbImage::from_pixel(32, 32, Rgb([0, 255, 0]));
    let physics = compute_objective_physics(&img);

    assert!(physics.color.gamut_coverage_srgb > 99.0);
    assert!(physics.color.gamut_coverage_p3 > 99.0);
    assert!(physics.color.gamut_coverage_rec2020 > 99.0);
}

#[test]
fn test_native_aspect_ratio_no_crop() {
    // Native frame with content filling all borders
    let img = RgbImage::from_pixel(120, 50, Rgb([100, 150, 200]));
    let bounds = aesthetic_metrics::detect_active_picture(&img);

    assert_eq!(bounds.x, 0);
    assert_eq!(bounds.y, 0);
    assert_eq!(bounds.width, 120);
    assert_eq!(bounds.height, 50);
}
