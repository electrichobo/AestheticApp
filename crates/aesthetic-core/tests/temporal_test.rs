use aesthetic_core::{
    classify_transition, compute_frame_difference, evaluate_candidate_frame,
    find_best_usable_window, FrameEvaluationSample, TransitionType,
};
use aesthetic_models::baseline::MetricQuantiles;
use image::{Rgb, RgbImage};

#[test]
fn test_window_optimizer_clamps_handles() {
    let samples = vec![
        FrameEvaluationSample {
            timestamp_sec: 1.0,
            quality_score: 80.0,
            stability_score: 85.0,
            is_settled: true,
        },
        FrameEvaluationSample {
            timestamp_sec: 2.0,
            quality_score: 90.0,
            stability_score: 95.0,
            is_settled: true,
        },
        FrameEvaluationSample {
            timestamp_sec: 3.5,
            quality_score: 92.0,
            stability_score: 90.0,
            is_settled: true,
        },
        FrameEvaluationSample {
            timestamp_sec: 5.0,
            quality_score: 70.0,
            stability_score: 60.0,
            is_settled: false,
        },
    ];

    let cut_start = 0.5;
    let cut_end = 4.0;
    let window = find_best_usable_window(&samples, 1.5, 3.0, 1.0, cut_start, cut_end);

    assert!(window.is_some());
    let win = window.unwrap();
    assert_eq!(win.start_sec, 1.0);
    assert_eq!(win.end_sec, 3.5);
    // Handle should clamp to cut_start (0.5) and cut_end (4.0)
    assert!(win.recommended_in_sec >= cut_start);
    assert!(win.recommended_out_sec <= cut_end);
}

#[test]
fn test_transition_detection() {
    let img_a = RgbImage::from_pixel(32, 32, Rgb([0, 0, 0]));
    let img_b = RgbImage::from_pixel(32, 32, Rgb([255, 255, 255]));

    let mad = compute_frame_difference(&img_a, &img_b);
    assert_eq!(mad, 100.0);

    let transition = classify_transition(mad, 255.0, false, 0.0);
    assert_eq!(transition, TransitionType::FadeToWhite);

    let match_cut = classify_transition(mad, 128.0, false, 80.0);
    assert_eq!(match_cut, TransitionType::MatchCut);

    let wipe = classify_transition(mad, 128.0, true, 0.0);
    assert_eq!(wipe, TransitionType::Wipe);
}

#[test]
fn test_evaluate_candidate_frame_4_outputs() {
    let mut img = RgbImage::new(128, 128);
    // Add black letterbox bars (top 16 rows, bottom 16 rows)
    for y in 0..128 {
        for x in 0..128 {
            if !(16..112).contains(&y) {
                img.put_pixel(x, y, Rgb([0, 0, 0]));
            } else {
                img.put_pixel(x, y, Rgb([160, 140, 120])); // warm midtone
            }
        }
    }

    let dr_q = MetricQuantiles {
        min: 6.0,
        p10: 9.0,
        p25: 11.0,
        p50: 12.5,
        p75: 14.0,
        p90: 15.0,
        max: 16.5,
    };
    let rolloff_q = MetricQuantiles {
        min: 10.0,
        p10: 50.0,
        p25: 70.0,
        p50: 85.0,
        p75: 92.0,
        p90: 96.0,
        max: 100.0,
    };
    let sharp_q = MetricQuantiles {
        min: 1.0,
        p10: 20.0,
        p25: 50.0,
        p50: 100.0,
        p75: 150.0,
        p90: 200.0,
        max: 300.0,
    };

    let shot = evaluate_candidate_frame(&img, "take_001", 1, 14.5, &dr_q, &rolloff_q, &sharp_q);

    assert_eq!(shot.take_id, "take_001");
    // Scores are tangible 0 - 100 numbers
    assert!(shot.scores.overall >= 0.0 && shot.scores.overall <= 100.0);
    assert!(shot.scores.technical >= 0.0 && shot.scores.technical <= 100.0);
    // Discovered style without PEBKAC
    assert!(!shot.style.lighting_key.is_empty());
}

#[test]
fn test_baseline_store_search_and_master_match() {
    use aesthetic_core::{cosine_similarity, BaselineStore};
    use aesthetic_models::baseline::{CinematographerSignature, ReferenceShot};

    let mut store = BaselineStore::new();

    // Register a reference shot from Skyfall
    store.add_reference_shot(ReferenceShot {
        shot_id: "skyfall_01".to_string(),
        film_title: "Skyfall".to_string(),
        cinematographer: "Roger Deakins".to_string(),
        timestamp_sec: 120.0,
        embedding: vec![0.5, 0.5, 0.5, 0.5],
        dynamic_range_stops: 13.5,
        highlight_rolloff: 92.0,
        sharpness_laplacian: 180.0,
        key_fill_ratio: 4.0,
        style_label: "Prestige Naturalism".to_string(),
    });

    // Register Roger Deakins signature
    store.register_signature(CinematographerSignature {
        dp_name: "Roger Deakins".to_string(),
        representative_films: vec!["Skyfall".to_string(), "Blade Runner 2049".to_string()],
        centroid_embedding: vec![0.5, 0.5, 0.5, 0.5],
        average_key_fill: 4.0,
        preferred_lighting_key: "Motivated Naturalistic".to_string(),
        preferred_motion_style: "Disciplined Dolly".to_string(),
    });

    // Test cosine similarity of identical vectors is 100.0
    let sim = cosine_similarity(&[1.0, 0.0], &[1.0, 0.0]);
    assert!((sim - 100.0).abs() < 1e-4);

    // Search nearest shots
    let candidate = vec![0.49, 0.51, 0.50, 0.48];
    let results = store.search_nearest(&candidate, 5);
    assert_eq!(results.len(), 1);
    assert!(results[0].1 > 95.0); // Very high similarity

    // Match master cinematographer
    let master_match = store.match_master_cinematographer(&candidate, 4.1);
    assert!(master_match.is_some());
    let mm = master_match.unwrap();
    assert_eq!(mm.dp_name, "Roger Deakins");
    assert!(mm.visual_similarity > 95.0);
    assert!(mm.craft_explanation.contains("Roger Deakins"));
}
