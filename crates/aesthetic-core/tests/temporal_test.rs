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

    let mut store = BaselineStore::default();

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
        motion_optical_flow: Some(1.8),
        camera_motion_ratio: Some(0.80),
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
    assert_eq!(mm.style_family, "Prestige Naturalism");
    assert!(mm.craft_explanation.contains("Roger Deakins"));
}

#[test]
fn test_reel_continuity_and_sidecar_rescore() {
    use aesthetic_core::{
        compute_reel_sequence_metrics, detect_burst_light_flicker, enrich_take,
        export_shot_sidecars_with_frames, rescore_from_sidecars, BaselineStore,
        ModelInferenceEngine,
    };
    use aesthetic_models::manifest::VideoSourceInfo;

    let store = BaselineStore::new();
    let inference = ModelInferenceEngine::new();
    let (dr_q, rolloff_q, sharp_q, _) = store.scoring_quantiles();

    let mut img_a = RgbImage::new(160, 90);
    for (x, y, p) in img_a.enumerate_pixels_mut() {
        let r = ((x * 255) / 160).min(255) as u8;
        let g = ((y * 200) / 90).min(255) as u8;
        *p = Rgb([r, g, 90]);
    }
    let mut take_a = evaluate_candidate_frame(&img_a, "take_001", 1, 2.0, &dr_q, &rolloff_q, &sharp_q);
    enrich_take(&mut take_a, &img_a, None, &store, &inference);
    assert!(!take_a.style.shot_scale.is_empty());
    assert!(take_a.golden_baseline.len() >= 4);

    let video_info = VideoSourceInfo {
        file_path: "test.mov".to_string(),
        duration_sec: 30.0,
        frame_rate: 24.0,
        width: 1920,
        height: 1080,
        codec: "h264".to_string(),
        color_primaries: Some("bt709".to_string()),
        transfer_characteristic: Some("arib-std-b67".to_string()),
    };
    let seq = compute_reel_sequence_metrics(std::slice::from_ref(&take_a), &video_info);
    assert!(seq.is_log_or_hdr);
    assert!(seq.transfer_curve_label.contains("HLG"));
    assert!(seq.grading_uniformity_score >= 0.0 && seq.grading_uniformity_score <= 100.0);

    // Flicker detector test on oscillating burst
    let f0 = RgbImage::from_pixel(64, 64, Rgb([100, 100, 100]));
    let f1 = RgbImage::from_pixel(64, 64, Rgb([112, 112, 112]));
    let f2 = RgbImage::from_pixel(64, 64, Rgb([99, 99, 99]));
    assert!(detect_burst_light_flicker(&f0, &f1, &f2));

    // Sidecar export & cached rescore round-trip
    let tmp_dir = std::env::temp_dir().join("aesthetic_rescore_test");
    let _ = std::fs::remove_dir_all(&tmp_dir);
    let mut frames = std::collections::HashMap::new();
    frames.insert("take_001".to_string(), img_a);
    let count = export_shot_sidecars_with_frames(
        &tmp_dir,
        "test.mov",
        std::slice::from_ref(&take_a),
        &frames,
    )
    .unwrap();
    assert_eq!(count, 1);

    let (rescored, loaded_frames) = rescore_from_sidecars(&tmp_dir).unwrap();
    assert_eq!(rescored.len(), 1);
    assert!(loaded_frames.contains_key("take_001"));
    assert!(rescored[0].scores.overall > 0.0);
    assert!(!rescored[0].rationale_summary.is_empty());
    assert!(rescored[0].measured.exposure.psnr_db > 15.0);
    assert!(rescored[0].measured.exposure.ssim_score > 0.5);
    assert!(rescored[0].scores.storytelling_score > 0.0);
    assert!(rescored[0].scores.cinematic_technique_score > 0.0);
    assert!(rescored[0].scores.memorability_score > 0.0);

    let py = aesthetic_core::generate_resolve_timeline_script(
        "AESTHETIC_TEST",
        "test.mov",
        &rescored,
        24.0,
    );
    assert!(py.contains("DaVinciResolveScript"));
    assert!(py.contains("timeline.AddMarker"));
    let _ = std::fs::remove_dir_all(&tmp_dir);

    // Smart showreel composer test (M26)
    let reel = aesthetic_core::compose_smart_showreel(&rescored, 2.0, aesthetic_core::ShowreelObjective::DramaticNarrative);
    assert_eq!(reel.len(), 1);
}

fn draw_synthetic_text_band(img: &mut RgbImage, y0: u32, y1: u32, x0: u32, x1: u32, fg: Rgb<u8>) {
    for y in y0..y1.min(img.height()) {
        for x in x0..x1.min(img.width()) {
            // Alternating glyph vertical strokes with letter spaces (every 6 px)
            let dx = x - x0;
            if (dx % 6) < 3 && ((y - y0) != (y1 - y0) / 2 || (dx % 12) < 6) {
                img.put_pixel(x, y, fg);
            }
        }
    }
}

#[test]
fn test_title_card_detection_and_filtering() {
    use aesthetic_core::{
        apply_reel_diversity_ranking, detect_title_card_or_graphic, is_proxy_title_card_or_blank,
    };
    use aesthetic_models::ShotTake;
    use aesthetic_metrics::compute_objective_physics;
    use aesthetic_models::baseline::MetricQuantiles;

    let (w, h) = (320u32, 180u32);

    // 1. White-on-black title card
    let mut black_card = RgbImage::from_pixel(w, h, Rgb([10, 10, 12]));
    for row_y in [58u32, 74, 90, 106, 122] {
        draw_synthetic_text_band(&mut black_card, row_y, row_y + 8, 70, 250, Rgb([240, 240, 242]));
    }
    let phys_black = compute_objective_physics(&black_card);
    assert!(
        detect_title_card_or_graphic(&black_card, &phys_black).is_some(),
        "White-on-black title card must be flagged"
    );
    let black_proxy = image::imageops::resize(&black_card, 160, 90, image::imageops::FilterType::Triangle);
    assert!(
        is_proxy_title_card_or_blank(&black_proxy),
        "Proxy white-on-black title card must be flagged"
    );

    // 2. Black-on-white title card
    let mut white_card = RgbImage::from_pixel(w, h, Rgb([244, 244, 246]));
    for row_y in [60u32, 78, 96, 114] {
        draw_synthetic_text_band(&mut white_card, row_y, row_y + 8, 80, 240, Rgb([16, 16, 20]));
    }
    let phys_white = compute_objective_physics(&white_card);
    assert!(
        detect_title_card_or_graphic(&white_card, &phys_white).is_some(),
        "Black-on-white title card must be flagged"
    );
    let white_proxy = image::imageops::resize(&white_card, 160, 90, image::imageops::FilterType::Triangle);
    assert!(
        is_proxy_title_card_or_blank(&white_proxy),
        "Proxy black-on-white title card must be flagged"
    );

    // 3. Gold-on-navy-gradient title card
    let mut grad_card = RgbImage::new(w, h);
    for y in 0..h {
        let fy = y as f32 / (h - 1) as f32;
        for x in 0..w {
            let r = (14.0 + fy * 16.0) as u8;
            let g = (24.0 + fy * 22.0) as u8;
            let b = (52.0 + fy * 34.0) as u8;
            grad_card.put_pixel(x, y, Rgb([r, g, b]));
        }
    }
    for row_y in [64u32, 82, 100, 118] {
        draw_synthetic_text_band(&mut grad_card, row_y, row_y + 8, 72, 248, Rgb([235, 190, 68]));
    }
    let phys_grad = compute_objective_physics(&grad_card);
    assert!(
        detect_title_card_or_graphic(&grad_card, &phys_grad).is_some(),
        "Gold-on-navy-gradient title card must be flagged"
    );
    let grad_proxy = image::imageops::resize(&grad_card, 160, 90, image::imageops::FilterType::Triangle);
    assert!(
        is_proxy_title_card_or_blank(&grad_proxy),
        "Proxy gradient title card must be flagged"
    );

    // 4. Multi-row rolling credits card
    let mut credits_card = RgbImage::from_pixel(w, h, Rgb([12, 12, 14]));
    for i in 0..10u32 {
        let y0 = 20 + i * 14;
        draw_synthetic_text_band(&mut credits_card, y0, y0 + 6, 48, 272, Rgb([232, 232, 235]));
    }
    let phys_cred = compute_objective_physics(&credits_card);
    assert!(
        detect_title_card_or_graphic(&credits_card, &phys_cred).is_some(),
        "Multi-row credits roll must be flagged"
    );

    // 5. Rich photographic scene must NOT be flagged
    let mut photo = RgbImage::new(w, h);
    for y in 0..h {
        for x in 0..w {
            let nx = x as f32 / w as f32;
            let ny = y as f32 / h as f32;
            let wave = (nx * 9.0 + ny * 4.5).sin() * 28.0 + (nx * 19.0 - ny * 11.0).cos() * 14.0;
            let r = (70.0 + nx * 130.0 + wave).clamp(0.0, 255.0) as u8;
            let g = (55.0 + ny * 110.0 + wave * 0.7).clamp(0.0, 255.0) as u8;
            let b = (90.0 + (1.0 - nx) * 85.0 - wave * 0.5).clamp(0.0, 255.0) as u8;
            photo.put_pixel(x, y, Rgb([r, g, b]));
        }
    }
    let phys_photo = compute_objective_physics(&photo);
    assert!(
        detect_title_card_or_graphic(&photo, &phys_photo).is_none(),
        "Rich photographic scene must NOT be flagged as a title card"
    );
    let photo_proxy = image::imageops::resize(&photo, 160, 90, image::imageops::FilterType::Triangle);
    assert!(
        !is_proxy_title_card_or_blank(&photo_proxy),
        "Proxy rich photographic scene must NOT be flagged"
    );

    // 6. Low-key chiaroscuro portrait with smooth spherical shading on dark ambient wall
    let mut portrait = RgbImage::new(w, h);
    for y in 0..h {
        for x in 0..w {
            let nx = x as f32 / w as f32;
            let ny = y as f32 / h as f32;
            let sx = (nx - 0.42) / 0.14;
            let sy = (ny - 0.44) / 0.24;
            let r2 = sx * sx + sy * sy;
            if r2 < 1.0 {
                let nz = (1.0 - r2).sqrt();
                let key = (-0.6 * sx - 0.35 * sy + 0.7 * nz).max(0.0);
                let luma = 35.0 + 165.0 * key;
                portrait.put_pixel(
                    x,
                    y,
                    Rgb([
                        (luma * 1.1).clamp(0.0, 255.0) as u8,
                        (luma * 0.85).clamp(0.0, 255.0) as u8,
                        (luma * 0.65).clamp(0.0, 255.0) as u8,
                    ]),
                );
            } else {
                // Soft ambient practical glow on dark studio background (smooth mid gradients)
                let wall = 22.0 + 26.0 * (nx * 4.5).sin().abs() + 18.0 * (1.0 - ny);
                portrait.put_pixel(
                    x,
                    y,
                    Rgb([
                        wall as u8,
                        (wall * 1.05) as u8,
                        (wall * 1.25) as u8,
                    ]),
                );
            }
        }
    }
    let phys_port = compute_objective_physics(&portrait);
    assert!(
        detect_title_card_or_graphic(&portrait, &phys_port).is_none(),
        "Low-key chiaroscuro portrait must NOT be flagged"
    );

    // 7. Ranking removes title card completely when photographic takes exist
    let q = MetricQuantiles {
        min: 1.0,
        p10: 5.0,
        p25: 8.0,
        p50: 10.0,
        p75: 12.0,
        p90: 14.0,
        max: 16.5,
    };
    let mut t_photo = evaluate_candidate_frame(&photo, "take_001", 1, 10.0, &q, &q, &q);
    t_photo.scores.overall = 82.0;
    let t_card = evaluate_candidate_frame(&black_card, "take_002", 2, 1.0, &q, &q, &q);
    assert!(t_card
        .concerns
        .iter()
        .any(|c| c.code == "NON_PHOTOGRAPHIC_OR_CREDITS"));

    let mut mixed: Vec<ShotTake> = vec![t_card, t_photo];
    apply_reel_diversity_ranking(&mut mixed);
    assert_eq!(mixed.len(), 1, "Title card must be excluded from ranked takes");
    assert_eq!(mixed[0].take_id, "take_001");
}

#[test]
fn test_scene_grouping_and_scene_coverage_ranking() {
    use aesthetic_core::{
        apply_reel_diversity_ranking, group_shots_into_scenes, ShotCandidateWindow,
    };
    use aesthetic_models::ShotTake;

    let make_hist = |r_bin: usize, g_bin: usize, b_bin: usize| -> [f32; 24] {
        let mut h = [0.0f32; 24];
        h[r_bin] = 0.33;
        h[8 + g_bin] = 0.33;
        h[16 + b_bin] = 0.34;
        h
    };

    let raw_shots = vec![
        // Scene 1: 2 similar shots
        ShotCandidateWindow {
            start_sec: 0.0,
            end_sec: 3.0,
            best_timestamps: vec![1.5],
            proxy_quality: 75.0,
            avg_luma: 95.0,
            color_hist: make_hist(4, 3, 2),
            is_non_photographic: false,
        },
        ShotCandidateWindow {
            start_sec: 3.0,
            end_sec: 6.0,
            best_timestamps: vec![4.5],
            proxy_quality: 82.0,
            avg_luma: 98.0,
            color_hist: make_hist(4, 3, 2),
            is_non_photographic: false,
        },
        // Intertitle / title card separator
        ShotCandidateWindow {
            start_sec: 6.0,
            end_sec: 9.0,
            best_timestamps: vec![7.5],
            proxy_quality: 0.0,
            avg_luma: 12.0,
            color_hist: make_hist(0, 0, 0),
            is_non_photographic: true,
        },
        // Scene 2: separated by non-photographic title card
        ShotCandidateWindow {
            start_sec: 9.0,
            end_sec: 13.0,
            best_timestamps: vec![11.0],
            proxy_quality: 80.0,
            avg_luma: 100.0,
            color_hist: make_hist(4, 3, 2),
            is_non_photographic: false,
        },
        // Scene 3: large palette shift
        ShotCandidateWindow {
            start_sec: 13.0,
            end_sec: 17.0,
            best_timestamps: vec![15.0],
            proxy_quality: 85.0,
            avg_luma: 185.0,
            color_hist: make_hist(7, 7, 5),
            is_non_photographic: false,
        },
        // Scene 4: large palette shift to night exterior
        ShotCandidateWindow {
            start_sec: 17.0,
            end_sec: 21.0,
            best_timestamps: vec![19.0],
            proxy_quality: 78.0,
            avg_luma: 38.0,
            color_hist: make_hist(0, 1, 5),
            is_non_photographic: false,
        },
    ];

    let (scenes, non_photo_count) = group_shots_into_scenes(raw_shots);
    assert_eq!(non_photo_count, 1, "Must count filtered title card separator");
    assert_eq!(scenes.len(), 4, "Must discover all 4 distinct photographic scenes");
    assert_eq!(scenes[0].shots.len(), 2, "Similar consecutive shots merge into Scene 1");

    // Verify scene-coverage diversity in apply_reel_diversity_ranking:
    // Give Scene 1 three slightly higher scores than Scenes 2, 3, 4 and check Top 4 covers all 4 scenes.
    let make_take = |id: &str, scene_idx: usize, score: f32, dr: f32, luma: f32, cct: f32| -> ShotTake {
        let mut t = ShotTake {
            take_id: id.to_string(),
            scene_index: scene_idx,
            start_sec: scene_idx as f64 * 10.0,
            end_sec: scene_idx as f64 * 10.0 + 3.0,
            duration_sec: 3.0,
            hero_frame_index: Some(0),
            hero_timestamp_sec: scene_idx as f64 * 10.0 + 1.5,
            scores: Default::default(),
            style: Default::default(),
            measured: Default::default(),
            concerns: Vec::new(),
            craft: None,
            golden_baseline: Vec::new(),
            rationale_summary: String::new(),
        };
        t.scores.overall = score;
        t.measured.exposure.dynamic_range_stops = dr;
        t.measured.exposure.histogram_mean = luma;
        t.measured.color.estimated_kelvin = cct;
        t
    };

    let mut takes = vec![
        make_take("s1_a", 1, 92.0, 10.5, 110.0, 5200.0),
        make_take("s1_b", 1, 91.5, 10.6, 112.0, 5220.0),
        make_take("s1_c", 1, 91.0, 10.4, 108.0, 5180.0),
        make_take("s2_a", 2, 89.0, 9.8, 125.0, 6200.0),
        make_take("s3_a", 3, 88.0, 11.2, 160.0, 4000.0),
        make_take("s4_a", 4, 87.0, 8.9, 65.0, 3200.0),
    ];

    apply_reel_diversity_ranking(&mut takes);
    let top4_scenes: std::collections::HashSet<usize> =
        takes.iter().take(4).map(|t| t.scene_index).collect();
    assert_eq!(
        top4_scenes.len(),
        4,
        "Top 4 selects must represent all 4 distinct scenes before duplicating Scene 1"
    );
}
