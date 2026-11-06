//! AESTHETIC CLI Driver
//!
//! Headless CLI driver for video analysis, Golden Baseline inspection,
//! performance benchmarking, and automated selects packaging.

use aesthetic_core::baseline_store::BaselineStore;
use aesthetic_core::export::seconds_to_smpte_timecode;
use aesthetic_core::pipeline::{analyze_video_file, evaluate_candidate_frame, BatchOptions};
use aesthetic_models::baseline::{MetricQuantiles, ReferenceShot};
use image::{Rgb, RgbImage};
use std::env;
use std::path::{Path, PathBuf};
use std::time::Instant;

fn main() {
    let args: Vec<String> = env::args().collect();

    println!("============================================================");
    println!("  AESTHETIC Core Engine (Rust v0.1.0)");
    println!("  High-Performance Video Intelligence & Showreel Selection");
    println!("============================================================");

    if args.len() < 2 {
        print_usage();
        return;
    }

    match args[1].as_str() {
        "benchmark" => run_benchmark(),
        "baseline-info" => print_baseline_info(),
        "awards-list" => print_awards_list(),
        "demo" => run_demo_analysis(),
        "analyze" => {
            if args.len() < 3 {
                println!("Error: Missing video file path.");
                println!("Usage: aesthetic-cli analyze <path_to_video> [options]");
                return;
            }
            let video_path = PathBuf::from(&args[2]);
            run_video_analysis(&video_path, &args[3..]);
        }
        "ingest-baseline" => {
            if args.len() < 3 {
                println!("Error: Missing video file path.");
                println!("Usage: aesthetic-cli ingest-baseline <path_to_video> --title <title> --dp <cinematographer> [--year <year>] [--step <seconds>]");
                return;
            }
            let video_path = PathBuf::from(&args[2]);
            run_baseline_ingest(&video_path, &args[3..]);
        }
        "ingest-server" => {
            if args.len() < 3 {
                println!("Error: Missing media server movies directory.");
                println!("Usage: aesthetic-cli ingest-server <server_movies_dir> [--limit <N>] [--shots <N>] [--dry-run]");
                return;
            }
            let server_dir = PathBuf::from(&args[2]);
            run_server_ingest(&server_dir, &args[3..]);
        }
        "rescore" => {
            if args.len() < 3 {
                println!("Error: Missing sidecars directory.");
                println!("Usage: aesthetic-cli rescore <sidecars_dir> [--contact-sheet <file.html>]");
                return;
            }
            let sidecars_dir = PathBuf::from(&args[2]);
            run_sidecars_rescore(&sidecars_dir, &args[3..]);
        }
        "feedback" => {
            if args.len() < 4 {
                println!("Error: Missing take_id or action.");
                println!("Usage: aesthetic-cli feedback <take_id> <promote_hero|pin_select|reject_take> [--style <family>] [--scale <scale>]");
                return;
            }
            run_feedback_log(&args[2], &args[3], &args[4..]);
        }
        _ => {
            println!("Unknown command: {}", args[1]);
            print_usage();
        }
    }
}

fn print_usage() {
    println!("\nCommands:");
    println!("  analyze <video_file>   Analyze video and generate 4-output candidate selects");
    println!("    Options:");
    println!("      --top <N>              Limit candidate selects to top N hero shots");
    println!("      --edl <file.edl>       Export CMX 3600 standard EDL");
    println!("      --csv <file.csv>       Export CSV selects manifest");
    println!("      --xml <file.xml>       Export FCPXML timeline for DaVinci Resolve / FCP");
    println!("      --contact-sheet <file> Export visual HTML contact sheet");
    println!("      --sidecars <dir>       Export JSON shot sidecars to <dir>/metrics/*.json");
    println!("      --clips <dir>          Export trimmed select clips with handles");
    println!("      --step <seconds>       Sampling interval in seconds (default: 1.0)");
    println!("  ingest-baseline <file_or_dir> --title <title> --dp <cinematographer>");
    println!("                         Ingest reference film, still image, or directory into Golden Baseline");
    println!("  ingest-server <dir>    Scan media server, match Oscar/ASC/BSC award titles, & ingest shots");
    println!("    Options:");
    println!("      --limit <N>            Limit to first N matched award films");
    println!(
        "      --shots <N>            Extract N clean continuous shots per film (default: 10)"
    );
    println!("      --force                Re-ingest films even if already present in baseline");
    println!("      --dry-run              Catalog matched award titles without extracting shots");
    println!("  rescore <sidecars_dir> Instantaneously re-score cached JSON+PNG sidecars against current baseline");
    println!("  feedback <id> <action> Log user select preference event (promote_hero | pin_select | reject_take)");
    println!("  awards-list            Display all 80+ Oscar, ASC, and BSC titles in the registry");
    println!("  baseline-info          Display current Golden Baseline statistics and films");
    println!("  benchmark              Run multi-threaded SIMD physics & vector search benchmarks");
    println!("  demo                   Run synthetic benchmark on high-resolution frame raster");
}

fn run_feedback_log(take_id: &str, action: &str, flags: &[String]) {
    let mut style_family = "Prestige Naturalism".to_string();
    let mut shot_scale = "Medium Close-Up".to_string();
    let mut i = 0;
    while i < flags.len() {
        match flags[i].as_str() {
            "--style" if i + 1 < flags.len() => {
                style_family = flags[i + 1].clone();
                i += 1;
            }
            "--scale" if i + 1 < flags.len() => {
                shot_scale = flags[i + 1].clone();
                i += 1;
            }
            _ => {}
        }
        i += 1;
    }

    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let ev = aesthetic_models::window::SelectFeedbackEvent {
        timestamp_unix: ts,
        take_id: take_id.to_string(),
        action: action.to_string(),
        style_family: style_family.clone(),
        shot_scale: shot_scale.clone(),
        overall_score: 85.0,
        hero_potency_score: 85.0,
        storytelling_score: 85.0,
        memorability_score: 85.0,
    };
    match aesthetic_core::log_select_feedback_event(&ev) {
        Ok(total) => println!(
            "[✓] Logged feedback event '{}' for {} (Style: {}, Scale: {}). Total stored events: {}",
            action, take_id, style_family, shot_scale, total
        ),
        Err(e) => eprintln!("Failed to log feedback event: {}", e),
    }
}

fn run_sidecars_rescore(sidecars_dir: &Path, flags: &[String]) {
    let mut contact_sheet_path: Option<PathBuf> = None;
    let mut resolve_script_path: Option<PathBuf> = None;
    let mut i = 0;
    while i < flags.len() {
        if (flags[i] == "--contact-sheet" || flags[i] == "--html") && i + 1 < flags.len() {
            contact_sheet_path = Some(PathBuf::from(&flags[i + 1]));
            i += 1;
        } else if (flags[i] == "--resolve" || flags[i] == "--resolve-script") && i + 1 < flags.len()
        {
            resolve_script_path = Some(PathBuf::from(&flags[i + 1]));
            i += 1;
        }
        i += 1;
    }

    let t0 = Instant::now();
    match aesthetic_core::export::rescore_from_sidecars(sidecars_dir) {
        Ok((takes, hero_frames)) => {
            let elapsed = t0.elapsed().as_secs_f64() * 1000.0;
            println!(
                "\nRe-scored {} cached takes in {:.1}ms against Golden Baseline",
                takes.len(),
                elapsed
            );
            println!(
                "{:<6} {:<12} {:<12} {:<8} {:<18} {:<15} {:<24}",
                "Rank", "Take ID", "Start(s)", "Score", "Lighting Key", "Scale", "Nearest Award Ref"
            );
            println!("{}", "-".repeat(98));
            for (idx, t) in takes.iter().enumerate() {
                println!(
                    "#{:<5} {:<12} {:<12.2} {:<8.1} {:<18} {:<15} {:<24}",
                    idx + 1,
                    t.take_id,
                    t.start_sec,
                    t.scores.overall,
                    t.style.lighting_key,
                    t.style.shot_scale,
                    t.style
                        .cinematographer_match
                        .as_deref()
                        .unwrap_or("Baseline Cinema")
                );
            }
            if let Some(ref cs_path) = contact_sheet_path {
                let html = aesthetic_core::export::generate_contact_sheet_html_with_frames(
                    "RESCORED_SELECTS",
                    &sidecars_dir.to_string_lossy(),
                    &takes,
                    0,
                    &hero_frames,
                );
                if let Some(parent) = cs_path.parent() {
                    let _ = std::fs::create_dir_all(parent);
                }
                if std::fs::write(cs_path, html).is_ok() {
                    println!("\n[✓] Updated Contact Sheet exported to: {}", cs_path.display());
                }
            }
            if let Some(ref py_path) = resolve_script_path {
                let py = aesthetic_core::export::generate_resolve_timeline_script(
                    "AESTHETIC_RESCORED",
                    &sidecars_dir.to_string_lossy(),
                    &takes,
                    24.0,
                );
                if let Some(parent) = py_path.parent() {
                    let _ = std::fs::create_dir_all(parent);
                }
                if std::fs::write(py_path, py).is_ok() {
                    println!(
                        "[✓] DaVinci Resolve script exported to: {}",
                        py_path.display()
                    );
                }
            }
        }
        Err(e) => eprintln!("Rescore failed: {}", e),
    }
}

fn run_video_analysis(video_path: &Path, flags: &[String]) {
    println!(
        "\nInitiating Video Intelligence Pipeline for: {}",
        video_path.display()
    );

    let mut options = BatchOptions::default();

    let mut i = 0;
    while i < flags.len() {
        match flags[i].as_str() {
            "--top" | "--top-n" if i + 1 < flags.len() => {
                if let Ok(n) = flags[i + 1].parse::<usize>() {
                    options.top_n = Some(n);
                }
                i += 1;
            }
            "--edl" if i + 1 < flags.len() => {
                options.export_edl_path = Some(PathBuf::from(&flags[i + 1]));
                i += 1;
            }
            "--csv" if i + 1 < flags.len() => {
                options.export_csv_path = Some(PathBuf::from(&flags[i + 1]));
                i += 1;
            }
            "--xml" | "--fcpxml" if i + 1 < flags.len() => {
                options.export_fcpxml_path = Some(PathBuf::from(&flags[i + 1]));
                i += 1;
            }
            "--contact-sheet" if i + 1 < flags.len() => {
                options.export_contact_sheet_path = Some(PathBuf::from(&flags[i + 1]));
                i += 1;
            }
            "--sidecars" if i + 1 < flags.len() => {
                options.export_sidecars_dir = Some(PathBuf::from(&flags[i + 1]));
                i += 1;
            }
            "--clips" if i + 1 < flags.len() => {
                options.export_clips_dir = Some(PathBuf::from(&flags[i + 1]));
                i += 1;
            }
            "--step" if i + 1 < flags.len() => {
                if let Ok(s) = flags[i + 1].parse::<f64>() {
                    options.sample_step_sec = s;
                }
                i += 1;
            }
            _ => {}
        }
        i += 1;
    }

    let start = Instant::now();
    match analyze_video_file(video_path, &options) {
        Ok(result) => {
            let elapsed = start.elapsed().as_secs_f64();
            println!("\nAnalysis completed in {:.2}s", elapsed);
            println!("------------------------------------------------------------");
            println!("Video Source: {}", result.video_info.file_path);
            println!(
                "Dimensions: {}x{} | Codec: {} | FPS: {:.2} | Duration: {:.1}s",
                result.video_info.width,
                result.video_info.height,
                result.video_info.codec,
                result.video_info.frame_rate,
                result.video_info.duration_sec
            );
            println!(
                "Candidate Selects Identified: {}",
                result.ranked_takes.len()
            );
            println!("------------------------------------------------------------");

            println!(
                "{:<6} {:<12} {:<12} {:<6} {:<8} {:<16} {:<15} {:<24}",
                "Rank", "In TC", "Out TC", "Dur(s)", "Score", "Lighting Key", "Scale", "Nearest Award Ref"
            );
            println!("{}", "-".repeat(100));

            for (idx, take) in result.ranked_takes.iter().enumerate() {
                let in_tc = seconds_to_smpte_timecode(take.start_sec, result.video_info.frame_rate);
                let out_tc = seconds_to_smpte_timecode(take.end_sec, result.video_info.frame_rate);
                let dp_match = take
                    .style
                    .cinematographer_match
                    .as_deref()
                    .unwrap_or("Baseline Cinema");
                let scale = if take.style.shot_scale.is_empty() {
                    "Medium"
                } else {
                    take.style.shot_scale.as_str()
                };

                println!(
                    "#{:<5} {:<12} {:<12} {:<6.1} {:<8.1} {:<16} {:<15} {:<24}",
                    idx + 1,
                    in_tc,
                    out_tc,
                    take.duration_sec,
                    take.scores.overall,
                    take.style.lighting_key,
                    scale,
                    dp_match
                );
            }

            let seq = &result.sequence_metrics;
            println!("------------------------------------------------------------");
            println!(
                "Sequence & Reel Continuity (Transfer: {}):",
                seq.transfer_curve_label
            );
            println!(
                "  * Grading Uniformity:    {:.1}/100  (WB Std: {:.2}, CCT Std: {:.0}K, Luma Std: {:.1})",
                seq.grading_uniformity_score,
                seq.wb_cross_scene_std,
                seq.color_temp_cross_scene_std,
                seq.exposure_consistency_std
            );
            println!(
                "  * Coverage Consistency:  {:.1}/100  | Reel Diversity: {:.1}/100  | Visual Fatigue Index: {:.1}/100",
                seq.coverage_consistency_score,
                seq.reel_diversity_score,
                seq.visual_fatigue_index
            );

            if let Some(ref p) = options.export_edl_path {
                println!("\n[✓] CMX 3600 EDL exported to: {}", p.display());
            }
            if let Some(ref p) = options.export_csv_path {
                println!("[✓] CSV Selects manifest exported to: {}", p.display());
            }
            if let Some(ref p) = options.export_fcpxml_path {
                println!("[✓] FCPXML timeline project exported to: {}", p.display());
            }
            if let Some(ref p) = options.export_contact_sheet_path {
                println!("[✓] Visual HTML contact sheet exported to: {}", p.display());
            }
            if options.export_sidecars_dir.is_some() {
                println!("[✓] Exported {} JSON shot sidecars.", result.sidecars_count);
            }
            if options.export_clips_dir.is_some() {
                println!(
                    "[✓] Extracted {} trimmed sub-clips with handles.",
                    result.extracted_clips_count
                );
            }
        }
        Err(err) => {
            eprintln!("\nAnalysis Failed: {}", err);
            eprintln!("Ensure FFmpeg is in PATH or tools/ directory and video path is valid.");
        }
    }
}

fn run_baseline_ingest(media_path: &Path, flags: &[String]) {
    let mut title = "Reference Cinema".to_string();
    let mut dp = "Cinema Master".to_string();
    let mut year = 2024;
    let mut step = 2.0;

    let mut i = 0;
    while i < flags.len() {
        match flags[i].as_str() {
            "--title" if i + 1 < flags.len() => {
                title = flags[i + 1].clone();
                i += 1;
            }
            "--dp" if i + 1 < flags.len() => {
                dp = flags[i + 1].clone();
                i += 1;
            }
            "--year" if i + 1 < flags.len() => {
                if let Ok(y) = flags[i + 1].parse::<u32>() {
                    year = y;
                }
                i += 1;
            }
            "--step" if i + 1 < flags.len() => {
                if let Ok(s) = flags[i + 1].parse::<f64>() {
                    step = s;
                }
                i += 1;
            }
            _ => {}
        }
        i += 1;
    }

    let mut store = BaselineStore::new();

    let is_dir = media_path.is_dir();
    let is_still = if let Some(ext) = media_path.extension().and_then(|e| e.to_str()) {
        matches!(
            ext.to_lowercase().as_str(),
            "png" | "jpg" | "jpeg" | "tiff" | "tif" | "exr" | "webp" | "bmp"
        )
    } else {
        false
    };

    println!("\nIngesting into Golden Baseline Corpus:");
    println!("  * Source Path:      {}", media_path.display());
    println!("  * Title:            {}", title);
    println!("  * Cinematographer:  {}", dp);
    println!("  * Release Year:     {}", year);

    let res = if is_dir {
        println!("  * Mode:             Directory of Still Reference Frames");
        store.ingest_reference_directory(media_path, &title, &dp, Some(year))
    } else if is_still {
        println!("  * Mode:             Single Reference Still Image");
        store.ingest_reference_still(media_path, &title, &dp, Some(year))
    } else {
        println!(
            "  * Mode:             Reference Film / Video (sample step: {:.1}s)",
            step
        );
        store.ingest_reference_film(media_path, &title, &dp, None, year, step)
    };

    match res {
        Ok(summary) => {
            let baseline_dir = Path::new("assets").join("baseline");
            if let Err(e) = store.save_to_dir(&baseline_dir) {
                eprintln!("Warning: Failed to save baseline to disk: {}", e);
            }
            println!("\n[✓] Ingestion Successful!");
            println!("  * Reference Shots Ingested: {}", summary.shots_added);
            println!(
                "  * Total Baseline Corpus:    {} shots",
                summary.total_corpus_shots
            );
            println!(
                "  * Recalibrated Dynamic Range (p50): {:.2} stops",
                summary.new_dynamic_range_p50
            );
            println!(
                "  * Recalibrated Roll-Off (p50):       {:.2}%",
                summary.new_highlight_rolloff_p50
            );
            println!(
                "  * Recalibrated Sharpness (p50):      {:.2}",
                summary.new_sharpness_p50
            );
        }
        Err(err) => {
            eprintln!("\nBaseline Ingest Failed: {}", err);
        }
    }
}

fn print_baseline_info() {
    println!("\n--- Golden Baseline Corpus State ---");
    let store = BaselineStore::new();
    println!("Master Cinematographer Signatures (Active):");
    for sig in &store.master_signatures {
        println!(
            "  * {:<18} ({}) — Key: {:<20} Motion: {}",
            sig.dp_name,
            sig.representative_films.join(", "),
            sig.preferred_lighting_key,
            sig.preferred_motion_style
        );
    }
    println!("\nEmpirical Quantiles Active:");
    println!(
        "  - Dynamic Range Stops: p10={:.1}, p50={:.1}, p90={:.1}",
        store.manifest.dynamic_range_quantiles.p10,
        store.manifest.dynamic_range_quantiles.p50,
        store.manifest.dynamic_range_quantiles.p90
    );
    println!(
        "  - Highlight Roll-Off %: p10={:.1}, p50={:.1}, p90={:.1}",
        store.manifest.highlight_rolloff_quantiles.p10,
        store.manifest.highlight_rolloff_quantiles.p50,
        store.manifest.highlight_rolloff_quantiles.p90
    );
}

fn run_benchmark() {
    println!("\nRunning Performance Benchmark across 4K Image Rasters...");
    let width = 3840;
    let height = 2160;

    let mut img = RgbImage::new(width, height);
    for y in 0..height {
        for x in 0..width {
            let val = ((x + y) % 256) as u8;
            img.put_pixel(x, y, Rgb([val, val.saturating_add(30), (val * 2) % 255]));
        }
    }

    let start = Instant::now();
    let physics = aesthetic_metrics::compute_objective_physics(&img);
    let elapsed = start.elapsed();

    println!("4K Frame Physics Computation Time: {:.2?}", elapsed);
    println!(
        "  - True Dynamic Range Stops: {:.2}",
        physics.exposure.dynamic_range_stops
    );
    println!(
        "  - Highlight Roll-Off:       {:.2}%",
        physics.exposure.highlight_rolloff
    );
    println!(
        "  - Laplacian Focus Variance: {:.2}",
        physics.optics.sharpness_laplacian
    );
    println!(
        "  - CIE 1931 Rec.2020 Gamut:  {:.2}%",
        physics.color.gamut_coverage_rec2020
    );

    let engine = aesthetic_core::inference::ModelInferenceEngine::new();
    println!("\nInference Architecture: {}", engine.backend_name);
    let start_craft = Instant::now();
    let craft = engine.infer_craft(&img);
    let emb = engine.infer_embedding(&img);
    let craft_time = start_craft.elapsed();
    println!(
        "4K Monocular Depth & Craft Inference Time: {:.2?}",
        craft_time
    );
    println!(
        "  - Depth Separation Score:   {:.2}",
        craft.staging.depth_separation_score
    );
    println!(
        "  - Key-to-Fill Contrast:     {:.2}:1",
        craft.lighting.key_to_fill_ratio
    );
    println!(
        "  - Inferred Key Azimuth:     {:.1} deg",
        craft.lighting.key_azimuth_deg.unwrap_or(0.0)
    );
    println!(
        "  - Gaze Staging Poise:       {:.1} / 100",
        craft.staging.gaze_poise_score
    );
    println!(
        "  - 1152-dim Embedding Norm:  {:.4}",
        emb.iter().map(|v| v * v).sum::<f32>().sqrt()
    );

    let mut store = BaselineStore::new();
    for i in 0..5000 {
        store.add_reference_shot(ReferenceShot {
            shot_id: format!("shot_{}", i),
            film_title: "Benchmark Film".to_string(),
            cinematographer: "DP".to_string(),
            timestamp_sec: i as f64,
            embedding: vec![0.1f32; 1152],
            dynamic_range_stops: 13.5,
            highlight_rolloff: 85.0,
            sharpness_laplacian: 140.0,
            key_fill_ratio: 3.5,
            style_label: "Moody".to_string(),
            motion_optical_flow: None,
            camera_motion_ratio: None,
        });
    }

    let query = vec![0.1f32; 1152];
    let start_search = Instant::now();
    let matches = store.search_nearest(&query, 10);
    let search_time = start_search.elapsed();

    println!(
        "Vector Similarity Search Time (5,000 reference shots): {:.2?}",
        search_time
    );
    println!("  - Top match score: {:.2}%", matches[0].1);
}

fn run_demo_analysis() {
    println!("\nRunning Demo Analysis on Synthetic 1080p Mezzanine Frame...");
    let mut img = RgbImage::new(1920, 1080);
    for y in 0..1080 {
        for x in 0..1920 {
            if !(140..940).contains(&y) {
                img.put_pixel(x, y, Rgb([0, 0, 0]));
            } else {
                let luma = ((x as f32 / 1920.0) * 180.0) as u8;
                img.put_pixel(x, y, Rgb([luma, luma.saturating_add(20), (255 - luma) / 2]));
            }
        }
    }

    let dr_q = MetricQuantiles {
        min: 8.0,
        p10: 10.5,
        p25: 12.0,
        p50: 13.5,
        p75: 14.8,
        p90: 16.0,
        max: 18.0,
    };
    let rolloff_q = MetricQuantiles {
        min: 25.0,
        p10: 60.0,
        p25: 75.0,
        p50: 88.0,
        p75: 93.0,
        p90: 97.0,
        max: 100.0,
    };
    let sharp_q = MetricQuantiles {
        min: 10.0,
        p10: 35.0,
        p25: 75.0,
        p50: 130.0,
        p75: 185.0,
        p90: 240.0,
        max: 400.0,
    };

    let shot = evaluate_candidate_frame(&img, "DEMO_TAKE_01", 1, 14.5, &dr_q, &rolloff_q, &sharp_q);

    println!("\n------------------------------------------------------------");
    println!("Take ID:            {}", shot.take_id);
    println!("Overall Score:      {:.1} / 100", shot.scores.overall);
    println!("  * Technical:      {:.1} / 100", shot.scores.technical);
    println!("  * Creative:       {:.1} / 100", shot.scores.creative);
    println!("  * Temporal:       {:.1} / 100", shot.scores.temporal);
    println!(
        "Discovered Style:   {} [{}]",
        shot.style.lighting_key, shot.style.motion_type
    );
    println!(
        "Dynamic Range:      {:.2} stops",
        shot.measured.exposure.dynamic_range_stops
    );
    println!(
        "Highlight Roll-Off: {:.2}%",
        shot.measured.exposure.highlight_rolloff
    );
    println!("Concerns Detected:  {}", shot.concerns.len());
    println!("------------------------------------------------------------");
}

fn print_awards_list() {
    use aesthetic_models::awards::CINEMATOGRAPHY_AWARDS_REGISTRY;

    println!("\n============================================================");
    println!("  AESTHETIC Cinematography Awards Registry (1995 – 2025+)");
    println!(
        "  Total Tracked Titles: {}",
        CINEMATOGRAPHY_AWARDS_REGISTRY.len()
    );
    println!("============================================================");

    for (idx, record) in CINEMATOGRAPHY_AWARDS_REGISTRY.iter().enumerate() {
        println!(
            "[{:02}] {:<32} ({}) — DP: {:<20} [Dir: {}] | Aspect: {:<6} | Style: {:<20} | {}",
            idx + 1,
            record.title,
            record.year,
            record.cinematographer,
            record.director,
            record.aspect_ratio,
            record.style_family,
            record.awards.join(", ")
        );
    }
}

use aesthetic_core::{find_primary_video_file, parse_movie_folder_name};

fn run_server_ingest(server_dir: &Path, flags: &[String]) {
    use aesthetic_models::awards::{find_award_match, CINEMATOGRAPHY_AWARDS_REGISTRY};
    use std::fs;

    let mut limit: Option<usize> = None;
    let mut shots_per_film = 10usize;
    let mut dry_run = false;
    let mut force = false;

    let mut i = 0;
    while i < flags.len() {
        match flags[i].as_str() {
            "--limit" if i + 1 < flags.len() => {
                if let Ok(l) = flags[i + 1].parse::<usize>() {
                    limit = Some(l);
                }
                i += 1;
            }
            "--shots-per-film" | "--shots" if i + 1 < flags.len() => {
                if let Ok(s) = flags[i + 1].parse::<usize>() {
                    shots_per_film = s;
                }
                i += 1;
            }
            "--dry-run" => {
                dry_run = true;
            }
            "--force" => {
                force = true;
            }
            _ => {}
        }
        i += 1;
    }

    println!("\n============================================================");
    println!("  AESTHETIC Media Server Baseline Ingestion");
    println!("  Scanning: {}", server_dir.display());
    println!(
        "  Registry: {} Oscar / ASC / BSC Award & Landmark Titles",
        CINEMATOGRAPHY_AWARDS_REGISTRY.len()
    );
    println!("============================================================");

    if !server_dir.exists() {
        eprintln!(
            "Error: Server directory does not exist or is not accessible: {}",
            server_dir.display()
        );
        return;
    }

    let entries = match fs::read_dir(server_dir) {
        Ok(e) => e,
        Err(err) => {
            eprintln!("Failed to read directory {}: {}", server_dir.display(), err);
            return;
        }
    };

    let mut matched_jobs = Vec::new();

    for entry in entries.flatten() {
        if let Ok(file_type) = entry.file_type() {
            if file_type.is_dir() {
                let folder_name = entry.file_name().to_string_lossy().to_string();
                let (title, year) = parse_movie_folder_name(&folder_name);
                if let Some(award) = find_award_match(&title, year) {
                    if let Some(video_file) = find_primary_video_file(&entry.path()) {
                        matched_jobs.push((folder_name, video_file, award));
                    }
                }
            }
        }
    }

    println!(
        "\nFound {} award-winning/nominated films in library:",
        matched_jobs.len()
    );
    for (idx, (folder, _file, award)) in matched_jobs.iter().enumerate() {
        println!(
            "  [{:02}] {:<35} -> {} ({}, DP: {}) [Awards: {}]",
            idx + 1,
            folder,
            award.title,
            award.year,
            award.cinematographer,
            award.awards.join(", ")
        );
    }

    if dry_run {
        println!("\n[DRY RUN] Cataloging complete. Run without --dry-run to execute shot-separated ingest.");
        return;
    }

    let mut store = BaselineStore::new();

    let pending_jobs: Vec<_> = if force {
        matched_jobs
    } else {
        let mut pending = Vec::new();
        let mut skipped = 0;
        for job in matched_jobs {
            let award_title = job.2.title;
            let exists = store
                .measured_shots()
                .iter()
                .any(|s| s.film_title.eq_ignore_ascii_case(award_title));
            if exists {
                skipped += 1;
            } else {
                pending.push(job);
            }
        }
        if skipped > 0 {
            println!(
                "\nDeduplication: Skipping {} already-ingested films in baseline (pass --force to re-ingest).",
                skipped
            );
        }
        pending
    };

    let to_process = if let Some(lim) = limit {
        &pending_jobs[..lim.min(pending_jobs.len())]
    } else {
        &pending_jobs[..]
    };

    println!(
        "\nStarting Shot-Separated Ingestion for {} films ({} hero shots/film)...",
        to_process.len(),
        shots_per_film
    );
    let mut total_shots = 0;

    for (idx, (folder, file_path, award)) in to_process.iter().enumerate() {
        println!("\n[{}/{}] Ingesting: {}", idx + 1, to_process.len(), folder);
        println!("  File: {}", file_path.display());
        println!(
            "  DP:   {} | Style: {}",
            award.cinematographer, award.style_family
        );

        let ingest_meta = aesthetic_core::baseline_store::FilmIngestMeta {
            title: award.title,
            cinematographer: award.cinematographer,
            director: Some(award.director),
            year: award.year,
            style_family: award.style_family,
            max_shots: shots_per_film,
        };

        match store.ingest_reference_film_shots(file_path, &ingest_meta) {
            Ok(summary) => {
                println!(
                    "  [✓] Extracted {} clean continuous shots (Corpus Total: {} shots)",
                    summary.shots_added, summary.total_corpus_shots
                );
                println!(
                    "      Dynamic Range p50: {:.2} stops | Roll-Off p50: {:.1}%",
                    summary.new_dynamic_range_p50, summary.new_highlight_rolloff_p50
                );
                total_shots += summary.shots_added;
                let baseline_dir = Path::new("assets").join("baseline");
                let _ = store.save_to_dir(&baseline_dir);
            }
            Err(err) => {
                eprintln!("  [!] Failed to ingest {}: {}", folder, err);
            }
        }
    }

    let baseline_dir = Path::new("assets").join("baseline");
    if let Err(e) = store.save_to_dir(&baseline_dir) {
        eprintln!("Warning: Failed to save baseline to disk: {}", e);
    } else {
        println!(
            "\n[✓] Golden Baseline successfully updated and saved to: {}",
            baseline_dir.display()
        );
    }

    println!(
        "\nIngestion Complete! Ingested {} clean shots across {} award films.",
        total_shots,
        to_process.len()
    );
}
