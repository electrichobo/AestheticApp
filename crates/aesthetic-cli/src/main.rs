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
    println!("  baseline-info          Display current Golden Baseline statistics and films");
    println!("  benchmark              Run multi-threaded SIMD physics & vector search benchmarks");
    println!("  demo                   Run synthetic benchmark on high-resolution frame raster");
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
                "{:<6} {:<12} {:<12} {:<6} {:<8} {:<16} {:<24}",
                "Rank", "In TC", "Out TC", "Dur(s)", "Score", "Lighting Key", "Master DP Match"
            );
            println!("{}", "-".repeat(84));

            for (idx, take) in result.ranked_takes.iter().enumerate() {
                let in_tc = seconds_to_smpte_timecode(take.start_sec, result.video_info.frame_rate);
                let out_tc = seconds_to_smpte_timecode(take.end_sec, result.video_info.frame_rate);
                let dp_match = take
                    .style
                    .cinematographer_match
                    .as_deref()
                    .unwrap_or("Baseline Cinema");

                println!(
                    "#{:<5} {:<12} {:<12} {:<6.1} {:<8.1} {:<16} {:<24}",
                    idx + 1,
                    in_tc,
                    out_tc,
                    take.duration_sec,
                    take.scores.overall,
                    take.style.lighting_key,
                    dp_match
                );
            }

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
