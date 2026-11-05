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
fn test_scopes_computation() {
    use aesthetic_metrics::{
        compute_cie_chromaticity_map, compute_histograms, compute_parade, compute_vectorscope,
        compute_waveform,
    };

    let img = RgbImage::from_pixel(64, 64, Rgb([128, 64, 200]));

    // 1. Luma Waveform
    let wf = compute_waveform(&img, 32);
    assert_eq!(wf.columns, 32);
    assert_eq!(wf.ire_levels, 100);
    assert_eq!(wf.density.len(), 32 * 100);

    // 2. RGB Parade
    let parade = compute_parade(&img, 32);
    assert_eq!(parade.columns, 32);
    assert_eq!(parade.r_density.len(), 32 * 100);
    assert_eq!(parade.g_density.len(), 32 * 100);
    assert_eq!(parade.b_density.len(), 32 * 100);

    // 3. Vectorscope
    let vec_scope = compute_vectorscope(&img, 64);
    assert_eq!(vec_scope.resolution, 64);
    assert_eq!(vec_scope.density.len(), 64 * 64);
    assert_eq!(vec_scope.skin_tone_angle_deg, 57.0);

    // 4. Channel Histograms
    let hist = compute_histograms(&img);
    assert_eq!(hist.luma.iter().sum::<u32>(), 64 * 64);
    assert_eq!(hist.r[128], 64 * 64);
    assert_eq!(hist.g[64], 64 * 64);
    assert_eq!(hist.b[200], 64 * 64);

    // 5. CIE 1931 Chromaticity Map
    let cie = compute_cie_chromaticity_map(&img, 32);
    assert_eq!(cie.grid_size, 32);
    assert_eq!(cie.density.len(), 32 * 32);
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

#[test]
fn test_split_toning_harmony() {
    let mut img = RgbImage::new(64, 64);
    // Upper half: warm golden highlights
    for y in 0..32 {
        for x in 0..64 {
            img.put_pixel(x, y, Rgb([240, 200, 110]));
        }
    }
    // Lower half: cool teal/blue shadows
    for y in 32..64 {
        for x in 0..64 {
            img.put_pixel(x, y, Rgb([15, 45, 95]));
        }
    }

    let physics = compute_objective_physics(&img);
    assert!(
        physics.color.split_toning_separation_deg > 110.0,
        "Separation angle should reflect complementary split-toning: {}",
        physics.color.split_toning_separation_deg
    );
    assert!(
        physics.color.harmonic_palette_score > 50.0,
        "Harmonic palette score should be high: {}",
        physics.color.harmonic_palette_score
    );
}

#[test]
fn test_el_zone_system() {
    use aesthetic_metrics::{compute_el_zone_map, el_zone_color_for_stops, luma_to_el_zone_stops};
    use image::{Rgb, RgbImage};

    // 18% middle gray test (approx luma 124 in 8-bit gamma 2.4)
    let ev_18 = luma_to_el_zone_stops(124.5);
    assert!(
        ev_18.abs() < 0.2,
        "18% gray should correspond to ~0 EV (Zone V): {}",
        ev_18
    );
    let color_18 = el_zone_color_for_stops(ev_18);
    assert_eq!(color_18, [128, 128, 128], "Zone V must be neutral gray");

    // Specular highlight test (+5 stops)
    let ev_high = luma_to_el_zone_stops(255.0);
    assert!(
        ev_high >= 2.4,
        "Full white is high stop offset: {}",
        ev_high
    );
    let color_high = el_zone_color_for_stops(5.5);
    assert_eq!(color_high, [255, 0, 255], "Zone X must be magenta");

    // Black floor test (Zone 0)
    let color_low = el_zone_color_for_stops(-6.0);
    assert_eq!(color_low, [0, 0, 0], "Zone 0 must be black");

    // Generate EL Zone false-color raster
    let mut img = RgbImage::new(10, 10);
    for p in img.pixels_mut() {
        *p = Rgb([125, 125, 125]);
    }
    let el_map = compute_el_zone_map(&img);
    assert_eq!(el_map.dimensions(), (10, 10));
    assert_eq!(el_map.get_pixel(5, 5), &Rgb([128, 128, 128]));
}

#[test]
fn test_dynamic_range_and_spatial_snr() {
    // 1. Multi-zone continuous photographic gradient (shadows through highlights)
    let mut cinema_img = RgbImage::new(128, 64);
    for y in 0..64 {
        for x in 0..128 {
            let v = ((x as f32 / 127.0) * 230.0 + 12.0).round() as u8;
            cinema_img.put_pixel(x, y, Rgb([v, v.saturating_sub(4), v.saturating_add(4)]));
        }
    }
    let cinema_phys = compute_objective_physics(&cinema_img);
    assert!(
        cinema_phys.exposure.dynamic_range_stops > 10.0,
        "Continuous multi-zone scene should measure >10 stops DR, got {}",
        cinema_phys.exposure.dynamic_range_stops
    );
    assert!(
        cinema_phys.exposure.snr_luma > 30.0,
        "Clean continuous gradient should have positive high SNR (>30 dB), got {}",
        cinema_phys.exposure.snr_luma
    );

    // 2. End-credits bimodal graphic (96% black floor + 4% white text)
    let mut credits_img = RgbImage::from_pixel(128, 64, Rgb([0, 0, 0]));
    for y in 28..32 {
        for x in 40..88 {
            credits_img.put_pixel(x, y, Rgb([235, 235, 235]));
        }
    }
    let credits_phys = compute_objective_physics(&credits_img);
    assert!(
        credits_phys.exposure.dynamic_range_stops < 4.0,
        "Bimodal white-on-black credits should not fake high photographic DR, got {}",
        credits_phys.exposure.dynamic_range_stops
    );
}
