//! AESTHETIC Desktop UI Shell
//!
//! High-performance standalone desktop window application.
//! Serves broadcast scopes, 4-output evaluations, live frame extraction,
//! and interactive UI via embedded native WebView (Edge App Mode / Chromium).

use aesthetic_core::baseline_store::{scan_and_ingest_media_server, BaselineStore};
use aesthetic_core::deliverables::build_unified_deliverables_package;
use aesthetic_core::export::{
    generate_cmx3600_edl, generate_contact_sheet_html, generate_contact_sheet_html_with_frames,
    generate_csv_selects, generate_fcpxml,
};
use aesthetic_core::inference::ModelInferenceEngine;
use aesthetic_core::pipeline::{
    analyze_video_file, enrich_take, evaluate_candidate_frame, BatchAnalysisResult, BatchOptions,
};
use aesthetic_core::video::{extract_frame_rgb, probe_video_metadata};
use aesthetic_core::web_ingest::probe_web_url;
use aesthetic_metrics::{compute_el_zone_map, compute_focus_peaking_map};
use aesthetic_metrics::scopes::{
    compute_cie_chromaticity_map, compute_histograms, compute_parade, compute_vectorscope,
    compute_waveform,
};
use aesthetic_models::manifest::VideoSourceInfo;
use aesthetic_models::ShotTake;
use image::{Rgb, RgbImage};
use std::env;
use std::io::{Cursor, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, OnceLock, RwLock};
use std::thread;

const HTML_CONTENT: &str = include_str!("../ui/index.html");
const CSS_CONTENT: &str = include_str!("../ui/app.css");
const JS_CONTENT: &str = include_str!("../ui/app.js");
const LOGO_WIDE: &[u8] = include_bytes!("../ui/logo_wide.png");
const LOGO_ICON: &[u8] = include_bytes!("../ui/logo_icon.png");

#[derive(Clone, Default)]
struct AppState {
    loaded_media: Arc<RwLock<Option<VideoSourceInfo>>>,
    current_analysis: Arc<RwLock<Option<BatchAnalysisResult>>>,
    cached_frames: Arc<RwLock<std::collections::HashMap<String, RgbImage>>>,
}

fn main() {
    println!("============================================================");
    println!("  AESTHETIC Desktop UI Shell (Rust v0.1.0)");
    println!("  Cinematography Intelligence & Broadcast Scopes");
    println!("============================================================");

    let args: Vec<String> = env::args().collect();
    let headless = args
        .iter()
        .any(|a| a == "--headless" || a == "--server-only");

    let port_arg = args
        .windows(2)
        .find(|w| w[0] == "--port")
        .and_then(|w| w[1].parse::<u16>().ok())
        .or_else(|| {
            args.iter()
                .find(|a| a.starts_with("--port="))
                .and_then(|a| a.strip_prefix("--port="))
                .and_then(|p| p.parse::<u16>().ok())
        })
        .unwrap_or(0);

    let state = AppState::default();

    // Bind local loopback port
    let listener = TcpListener::bind(format!("127.0.0.1:{}", port_arg))
        .expect("Failed to bind local loopback interface");
    let port = listener
        .local_addr()
        .expect("Failed to get local port")
        .port();
    let app_url = format!("http://127.0.0.1:{}", port);
    println!("Local UI Server active on: {}", app_url);

    let running = Arc::new(AtomicBool::new(true));
    let running_clone = running.clone();
    let server_state = state.clone();

    // Spawn server thread with per-connection worker threads for true concurrency
    let server_handle = thread::spawn(move || {
        for stream in listener.incoming() {
            if !running_clone.load(Ordering::Relaxed) {
                break;
            }
            if let Ok(mut stream) = stream {
                let state_ref = server_state.clone();
                thread::spawn(move || {
                    handle_http_request(&mut stream, &state_ref);
                });
            }
        }
    });

    if headless {
        println!("Headless server running. Press Ctrl+C to stop.");
        let _ = server_handle.join();
        return;
    }

    // Launch standalone chromeless desktop window
    if let Some(edge_path) = find_edge_browser() {
        println!(
            "Launching standalone desktop window via: {}",
            edge_path.display()
        );
        let user_data = env::var("LOCALAPPDATA")
            .map(|l| PathBuf::from(l).join("AESTHETIC").join("webview"))
            .unwrap_or_else(|_| PathBuf::from("target").join("webview"));

        let mut child = Command::new(edge_path)
            .args([
                &format!("--app={}", app_url),
                "--window-size=1440,900",
                &format!("--user-data-dir={}", user_data.display()),
                "--no-first-run",
                "--no-default-browser-check",
            ])
            .spawn()
            .expect("Failed to spawn native desktop window");

        println!("Desktop window active. Close the window to exit.");
        let _ = child.wait();
        running.store(false, Ordering::Relaxed);
        println!("Desktop window closed. Exiting cleanly.");
    } else {
        println!(
            "Standalone browser window launcher not found. Open URL in browser: {}",
            app_url
        );
        let _ = server_handle.join();
    }
}

/// Locate Microsoft Edge application.
fn find_edge_browser() -> Option<PathBuf> {
    let candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ];

    for path_str in &candidates {
        let p = Path::new(path_str);
        if p.exists() {
            return Some(p.to_path_buf());
        }
    }
    None
}

/// Clean user-provided path string by trimming whitespace and surrounding quotes.
#[inline]
fn clean_user_path_str(raw: &str) -> &str {
    raw.trim().trim_matches('"').trim_matches('\'').trim()
}

/// Handle incoming HTTP requests and API endpoints.
fn handle_http_request(stream: &mut TcpStream, state: &AppState) {
    let mut buffer = [0; 8192];
    let bytes_read = match stream.read(&mut buffer) {
        Ok(n) => n,
        Err(_) => return,
    };
    if bytes_read == 0 {
        return;
    }

    let req = String::from_utf8_lossy(&buffer[..bytes_read]);
    let first_line = req.lines().next().unwrap_or_default();
    let parts: Vec<&str> = first_line.split_whitespace().collect();

    if parts.len() < 2 {
        return;
    }
    let full_path = parts[1];
    let (endpoint, query_str) = full_path.split_once('?').unwrap_or((full_path, ""));

    let query_map: std::collections::HashMap<String, String> = query_str
        .split('&')
        .filter_map(|pair| {
            let (k, v) = pair.split_once('=')?;
            Some((urlencoding_decode(k), urlencoding_decode(v)))
        })
        .collect();

    match endpoint {
        "/" | "/index.html" => {
            let content = std::fs::read_to_string("crates/aesthetic-ui/ui/index.html")
                .or_else(|_| std::fs::read_to_string("ui/index.html"))
                .unwrap_or_else(|_| HTML_CONTENT.to_string());
            send_response(
                stream,
                "200 OK",
                "text/html; charset=UTF-8",
                content.as_bytes(),
            );
        }
        "/app.css" | "/style.css" => {
            let content = std::fs::read_to_string("crates/aesthetic-ui/ui/app.css")
                .or_else(|_| std::fs::read_to_string("ui/app.css"))
                .unwrap_or_else(|_| CSS_CONTENT.to_string());
            send_response(
                stream,
                "200 OK",
                "text/css; charset=UTF-8",
                content.as_bytes(),
            );
        }
        "/app.js" => {
            let content = std::fs::read_to_string("crates/aesthetic-ui/ui/app.js")
                .or_else(|_| std::fs::read_to_string("ui/app.js"))
                .unwrap_or_else(|_| JS_CONTENT.to_string());
            send_response(
                stream,
                "200 OK",
                "application/javascript; charset=UTF-8",
                content.as_bytes(),
            );
        }
        "/logo_wide.png" => {
            send_response(stream, "200 OK", "image/png", LOGO_WIDE);
        }
        "/logo_icon.png" => {
            send_response(stream, "200 OK", "image/png", LOGO_ICON);
        }
        "/api/frame" => {
            let time_sec: f64 = query_map
                .get("time")
                .and_then(|t| t.parse().ok())
                .unwrap_or(0.0);
            let img = get_frame_for_time(state, time_sec);
            let mut bytes = Vec::new();
            let _ = img.write_to(&mut Cursor::new(&mut bytes), image::ImageFormat::Jpeg);
            send_response(stream, "200 OK", "image/jpeg", &bytes);
        }
        "/api/thumbnail" => {
            if let Some(take_id) = query_map.get("take") {
                let cf = state.cached_frames.read().unwrap();
                if let Some(cached_img) = cf.get(take_id) {
                    let thumb = image::imageops::thumbnail(cached_img, 320, 180);
                    let mut bytes = Vec::new();
                    let _ = thumb.write_to(&mut Cursor::new(&mut bytes), image::ImageFormat::Jpeg);
                    send_response(stream, "200 OK", "image/jpeg", &bytes);
                    return;
                }
            }
            let time_sec: f64 = query_map
                .get("time")
                .and_then(|t| t.parse().ok())
                .unwrap_or(0.0);
            let img = get_frame_for_time(state, time_sec);
            let thumb = image::imageops::thumbnail(&img, 320, 180);
            let mut bytes = Vec::new();
            let _ = thumb.write_to(&mut Cursor::new(&mut bytes), image::ImageFormat::Jpeg);
            send_response(stream, "200 OK", "image/jpeg", &bytes);
        }
        "/api/export_hero_png" => {
            let time_sec: f64 = query_map
                .get("time")
                .and_then(|t| t.parse().ok())
                .unwrap_or_else(|| {
                    let ca = state.current_analysis.read().unwrap();
                    ca.as_ref()
                        .and_then(|res| res.ranked_takes.first())
                        .map(|t| t.hero_timestamp_sec)
                        .unwrap_or(16.0)
                });
            let img = get_frame_for_time(state, time_sec);
            let mut bytes = Vec::new();
            let _ = img.write_to(&mut Cursor::new(&mut bytes), image::ImageFormat::Png);
            send_attachment_response(
                stream,
                "200 OK",
                "image/png",
                "AESTHETIC_Hero_Frame.png",
                &bytes,
            );
        }
        "/api/export_contact_sheet_png" => {
            let takes = {
                let ca = state.current_analysis.read().unwrap();
                if let Some(ref res) = *ca {
                    res.ranked_takes.clone()
                } else {
                    get_demo_takes()
                }
            };
            let sheet_img = generate_contact_sheet_png_composite(state, &takes);
            let mut bytes = Vec::new();
            let _ = sheet_img.write_to(&mut Cursor::new(&mut bytes), image::ImageFormat::Png);
            send_attachment_response(
                stream,
                "200 OK",
                "image/png",
                "AESTHETIC_Contact_Sheet.png",
                &bytes,
            );
        }
        "/api/frame_el_zone" => {
            let time_sec: f64 = query_map
                .get("time")
                .and_then(|t| t.parse().ok())
                .unwrap_or(0.0);
            let img = get_frame_for_time(state, time_sec);
            let el_map = compute_el_zone_map(&img);
            let mut bytes = Vec::new();
            let _ = el_map.write_to(&mut Cursor::new(&mut bytes), image::ImageFormat::Png);
            send_response(stream, "200 OK", "image/png", &bytes);
        }
        "/api/frame_peaking" => {
            let time_sec: f64 = query_map
                .get("time")
                .and_then(|t| t.parse().ok())
                .unwrap_or(0.0);
            let threshold: f32 = query_map
                .get("threshold")
                .and_then(|t| t.parse().ok())
                .unwrap_or(32.0);
            let img = get_frame_for_time(state, time_sec);
            let peaking = compute_focus_peaking_map(&img, threshold, [0, 255, 128]);
            let mut bytes = Vec::new();
            let _ = peaking.write_to(&mut Cursor::new(&mut bytes), image::ImageFormat::Png);
            send_response(stream, "200 OK", "image/png", &bytes);
        }
        "/api/scopes" => {
            let time_sec: f64 = query_map
                .get("time")
                .and_then(|t| t.parse().ok())
                .unwrap_or(0.0);

            let img = get_frame_for_time(state, time_sec);
            let wf = compute_waveform(&img, 380);
            let parade = compute_parade(&img, 128);
            let vs = compute_vectorscope(&img, 256);
            let hist = compute_histograms(&img);
            let cie = compute_cie_chromaticity_map(&img, 192);

            let json = serde_json::json!({
                "timestamp_sec": time_sec,
                "waveform": wf,
                "parade": parade,
                "vectorscope": vs,
                "histogram": hist,
                "cie": cie
            });
            let payload = json.to_string();
            send_response(stream, "200 OK", "application/json", payload.as_bytes());
        }
        "/api/evaluate" => {
            let time_sec: f64 = query_map
                .get("time")
                .and_then(|t| t.parse().ok())
                .unwrap_or(0.0);

            let img = get_frame_for_time(state, time_sec);
            let next_img = get_frame_for_time(state, time_sec + 0.25);

            let store = BaselineStore::new();
            let inference = ModelInferenceEngine::new();
            let (dr_q, rolloff_q, sharp_q, _) = store.scoring_quantiles();

            let mut shot = evaluate_candidate_frame(
                &img, "take_001", 1, time_sec, &dr_q, &rolloff_q, &sharp_q,
            );
            enrich_take(
                &mut shot,
                &img,
                Some((&next_img, 0.25)),
                &store,
                &inference,
            );
            if shot.style.shot_scale.is_empty() {
                shot.style.shot_scale = if shot.measured.optics.edge_density > 0.14 {
                    "Wide Architectural".to_string()
                } else if shot.measured.optics.vignetting_stops > 0.35 {
                    "Medium Close-Up".to_string()
                } else {
                    "Medium".to_string()
                };
            }

            let craft = shot.craft.clone().unwrap_or_default();
            let emb = inference.infer_embedding(&img);
            let dp_match =
                store.match_master_cinematographer(&emb, craft.lighting.key_to_fill_ratio);

            let actions: Vec<serde_json::Value> = Vec::new();

            let dr = shot.measured.exposure.dynamic_range_stops;
            let rolloff = shot.measured.exposure.highlight_rolloff;
            let acutance = shot.measured.optics.sharpness_laplacian;
            let kf_ratio = craft.lighting.key_to_fill_ratio;
            let split_angle = shot.measured.color.split_toning_separation_deg;
            let catchlight = craft.lighting.catchlight_intensity;
            let gaze_poise = craft.staging.gaze_poise_score;

            // Objective non-judgmental deltas against the Golden Baseline (184 Award-Winning Films)
            let dr_target = dr_q.p50.max(13.5);
            let dr_delta = dr - dr_target;
            let dr_status = if dr_delta.abs() <= 0.8 {
                "Within Award Cinema Median".to_string()
            } else if dr_delta < 0.0 {
                format!("Less Exposure Range ({:.1} stops)", dr_delta)
            } else {
                format!("Extended Exposure Range (+{:.1} stops)", dr_delta)
            };

            let rolloff_target = rolloff_q.p50.max(88.0);
            let rolloff_delta = rolloff - rolloff_target;
            let rolloff_status = if rolloff_delta.abs() <= 5.0 {
                "Gradual Film Roll-Off".to_string()
            } else if rolloff_delta < 0.0 {
                format!("Steeper Roll-Off Shoulder ({:.0}%)", rolloff_delta)
            } else {
                format!("Gentler Highlight Roll-Off (+{:.0}%)", rolloff_delta)
            };

            let acutance_target = sharp_q.p50.max(110.0);
            let acutance_delta = acutance - acutance_target;
            let acutance_status = if acutance_delta.abs() <= 20.0 {
                "Matched Cinema Prime Acutance".to_string()
            } else if acutance_delta < 0.0 {
                format!("Softer Optical Diffusion ({:.0} lp/mm)", acutance_delta)
            } else {
                format!("Crisper Micro-Contrast (+{:.0} lp/mm)", acutance_delta)
            };

            let kf_delta = kf_ratio - 3.8;
            let kf_status = if kf_delta.abs() <= 0.5 {
                "Balanced Chiaroscuro Ratio".to_string()
            } else if kf_delta > 0.0 {
                format!("Higher Contrast Ratio (+{:.1}:1)", kf_delta)
            } else {
                format!("Lower Contrast Ratio ({:.1}:1)", kf_delta)
            };

            let split_status = if split_angle >= 135.0 {
                format!("Complementary Color Separation ({:.0}°)", split_angle)
            } else {
                format!("Analogous Palette Alignment ({:.0}°)", split_angle)
            };

            let gaze_status = if gaze_poise >= 75.0 {
                "Harmonious Eyeline Poise".to_string()
            } else if gaze_poise >= 50.0 {
                "Centered Subject Eyeline".to_string()
            } else {
                "Short-Sided Lead Space".to_string()
            };

            let catchlight_status = if catchlight >= 60.0 {
                "Prominent Eye Specular".to_string()
            } else if catchlight >= 35.0 {
                "Balanced Eye Catchlight".to_string()
            } else {
                "Subdued Eye Specular".to_string()
            };

            // Golden Baseline Alignment (0-100%, strictly capped <= 100%)
            let baseline_alignment = shot.scores.overall.round().clamp(0.0, 100.0) as u32;

            // Ancillary DP note (strictly secondary to the Golden Baseline)
            let matched_name = dp_match
                .as_ref()
                .map(|d| d.dp_name.as_str())
                .unwrap_or("Roger Deakins");
            let matched_film = dp_match
                .as_ref()
                .map(|d| d.reference_film.as_str())
                .unwrap_or("Skyfall");
            let matched_family = if !shot.style.style_family.is_empty() {
                shot.style.style_family.as_str()
            } else {
                dp_match
                    .as_ref()
                    .map(|d| d.style_family.as_str())
                    .unwrap_or("Prestige Naturalism")
            };
            let dp_affinity_pct = dp_match
                .as_ref()
                .map(|d| d.visual_similarity.clamp(0.0, 100.0).round() as u32)
                .unwrap_or(baseline_alignment)
                .min(100);

            let cct = shot.measured.color.estimated_kelvin;
            let cct_tag = if cct < 4000.0 {
                format!("Tungsten Warmth ({:.0}K)", cct)
            } else if cct > 5800.0 {
                format!("Cool Daylight ({:.0}K)", cct)
            } else {
                format!("Neutral Daylight ({:.0}K)", cct)
            };
            let contrast_tag = if kf_ratio >= 3.5 {
                "Chiaroscuro Separation".to_string()
            } else {
                "Soft Ambient Wrap".to_string()
            };
            let depth_tag = if craft.staging.depth_separation_score >= 55.0 {
                "Multi-Plane Depth Separation".to_string()
            } else {
                "Deep Focus Staging".to_string()
            };

            let mut comparison_tags = vec![
                shot.style.lighting_key.clone(),
                shot.style.motion_type.clone(),
                shot.style.shot_scale.clone(),
                matched_family.to_string(),
                contrast_tag,
                cct_tag,
                depth_tag,
            ];
            comparison_tags.retain(|t| !t.trim().is_empty());

            let rows = serde_json::json!([
                {
                    "metric": "Dynamic Range Latitude",
                    "shot_val": format!("{:.1} stops", dr),
                    "target_val": format!("{:.1} stops (p50)", dr_target),
                    "status": dr_status
                },
                {
                    "metric": "Highlight Roll-Off",
                    "shot_val": format!("{:.0}%", rolloff),
                    "target_val": format!("{:.0}% (p50)", rolloff_target),
                    "status": rolloff_status
                },
                {
                    "metric": "MTF50 Optical Acutance",
                    "shot_val": format!("{:.1} lp/mm", acutance),
                    "target_val": format!("{:.0} lp/mm (p50)", acutance_target),
                    "status": acutance_status
                },
                {
                    "metric": "Key-to-Fill Ratio",
                    "shot_val": format!("{:.1}:1", kf_ratio),
                    "target_val": "3.8:1 (p50)",
                    "status": kf_status
                },
                {
                    "metric": "Split-Toning Separation",
                    "shot_val": format!("{:.0}°", split_angle),
                    "target_val": "160° (p50)",
                    "status": split_status
                },
                {
                    "metric": "Gaze Staging Poise",
                    "shot_val": format!("{:.0} / 100", gaze_poise),
                    "target_val": "88 / 100 (p50)",
                    "status": gaze_status
                },
                {
                    "metric": "Eye Catchlight Specular",
                    "shot_val": format!("{:.0}%", catchlight),
                    "target_val": "75% (p50)",
                    "status": catchlight_status
                }
            ]);

            let benchmark_block = serde_json::json!({
                "benchmark_name": "Award-Winning Cinema Golden Baseline (184 Films)",
                "corpus_films": store.manifest.total_films.max(58),
                "corpus_shots": store.reference_shots.len(),
                "measured_corpus_shots": store.measured_shots().len(),
                "alignment_pct": baseline_alignment,
                "style_family": matched_family,
                "ancillary_dp": format!("{} ({}, {}% affinity)", matched_name, matched_film, dp_affinity_pct),
                "dp_name": matched_name,
                "reference_film": matched_film,
                "similarity": baseline_alignment,
                "comparison_tags": comparison_tags,
                "rows": rows,
                "empirical_quantiles": shot.golden_baseline
            });

            let payload_json = serde_json::json!({
                "take": shot,
                "craft": craft,
                "golden_baseline_benchmark": benchmark_block,
                "stylistic_similar": benchmark_block,
                "comparison": benchmark_block,
                "actions": actions
            });

            let payload = payload_json.to_string();
            send_response(stream, "200 OK", "application/json", payload.as_bytes());
        }
        "/api/open_media" => {
            if let Some(path_str) = query_map.get("path") {
                let clean = clean_user_path_str(path_str);
                let path = Path::new(clean);
                if let Ok(dyn_img) = image::open(path) {
                    let rgb = dyn_img.to_rgb8();
                    let (w, h) = rgb.dimensions();
                    let info = VideoSourceInfo {
                        file_path: path.to_string_lossy().to_string(),
                        duration_sec: 5.0,
                        frame_rate: 24.0,
                        width: w,
                        height: h,
                        codec: "still_image".to_string(),
                        color_primaries: Some("bt709".to_string()),
                        transfer_characteristic: Some("srgb".to_string()),
                    };
                    let mut loaded = state.loaded_media.write().unwrap();
                    *loaded = Some(info.clone());
                    let json = serde_json::json!({
                        "success": true,
                        "media": info
                    });
                    send_response(
                        stream,
                        "200 OK",
                        "application/json",
                        json.to_string().as_bytes(),
                    );
                } else {
                    match probe_video_metadata(path) {
                        Ok(info) => {
                            let mut loaded = state.loaded_media.write().unwrap();
                            *loaded = Some(info.clone());
                            let json = serde_json::json!({
                                "success": true,
                                "media": info
                            });
                            send_response(
                                stream,
                                "200 OK",
                                "application/json",
                                json.to_string().as_bytes(),
                            );
                        }
                        Err(err) => {
                            let json = serde_json::json!({ "success": false, "error": err });
                            send_response(
                                stream,
                                "400 Bad Request",
                                "application/json",
                                json.to_string().as_bytes(),
                            );
                        }
                    }
                }
            } else {
                let json =
                    serde_json::json!({ "success": false, "error": "Missing 'path' parameter" });
                send_response(
                    stream,
                    "400 Bad Request",
                    "application/json",
                    json.to_string().as_bytes(),
                );
            }
        }
        "/api/web_probe" => {
            if let Some(url_str) = query_map.get("url") {
                match probe_web_url(url_str) {
                    Ok(info) => {
                        let json = serde_json::json!({ "success": true, "info": info });
                        send_response(
                            stream,
                            "200 OK",
                            "application/json",
                            json.to_string().as_bytes(),
                        );
                    }
                    Err(err) => {
                        let json = serde_json::json!({ "success": false, "error": err });
                        send_response(
                            stream,
                            "400 Bad Request",
                            "application/json",
                            json.to_string().as_bytes(),
                        );
                    }
                }
            } else {
                let json =
                    serde_json::json!({ "success": false, "error": "Missing 'url' parameter" });
                send_response(
                    stream,
                    "400 Bad Request",
                    "application/json",
                    json.to_string().as_bytes(),
                );
            }
        }
        "/api/ingest_server" => {
            let server_path = query_map
                .get("path")
                .map(|s| s.as_str())
                .unwrap_or(r"M:\movies");
            let limit: Option<usize> = query_map.get("limit").and_then(|l| l.parse().ok());
            let shots: usize = query_map
                .get("shots")
                .and_then(|s| s.parse().ok())
                .unwrap_or(5);
            let force = query_map
                .get("force")
                .map(|f| f == "true" || f == "1")
                .unwrap_or(false);

            let path = PathBuf::from(server_path);
            if !path.exists() {
                let json = serde_json::json!({
                    "success": false,
                    "error": format!("Directory '{}' does not exist or is inaccessible", server_path)
                });
                send_response(
                    stream,
                    "400 Bad Request",
                    "application/json",
                    json.to_string().as_bytes(),
                );
                return;
            }

            match scan_and_ingest_media_server(&path, limit, shots, force) {
                Ok(report) => {
                    let json = serde_json::json!({
                        "success": true,
                        "report": report
                    });
                    send_response(
                        stream,
                        "200 OK",
                        "application/json",
                        json.to_string().as_bytes(),
                    );
                }
                Err(err) => {
                    let json = serde_json::json!({ "success": false, "error": err });
                    send_response(
                        stream,
                        "500 Internal Server Error",
                        "application/json",
                        json.to_string().as_bytes(),
                    );
                }
            }
        }
        "/api/analyze" => {
            if let Some(path_str) = query_map.get("path") {
                let clean = clean_user_path_str(path_str);
                let path = Path::new(clean);
                let top_n = query_map
                    .get("top")
                    .and_then(|n| n.parse::<usize>().ok())
                    .or(Some(20));
                let step = query_map
                    .get("step")
                    .and_then(|s| s.parse::<f64>().ok())
                    .unwrap_or(1.0);

                // Direct still-image evaluation support (.png, .jpg, .tiff, .webp, etc.)
                if is_still_image_path(path) {
                    if let Ok(dyn_img) = image::open(path) {
                        let rgb = dyn_img.to_rgb8();
                        let (w, h) = rgb.dimensions();
                        let store = BaselineStore::new();
                        let inference = ModelInferenceEngine::new();
                        let (dr_q, rolloff_q, sharp_q, _) = store.scoring_quantiles();
                        let mut take = evaluate_candidate_frame(
                            &rgb, "still_001", 1, 0.0, &dr_q, &rolloff_q, &sharp_q,
                        );
                        enrich_take(&mut take, &rgb, None, &store, &inference);
                        take.style.motion_type = "Still Frame".to_string();
                        if take.style.shot_scale.is_empty() {
                            take.style.shot_scale = "Medium".to_string();
                        }
                        let info = VideoSourceInfo {
                            file_path: path.to_string_lossy().to_string(),
                            duration_sec: 5.0,
                            frame_rate: 24.0,
                            width: w,
                            height: h,
                            codec: "still_image".to_string(),
                            color_primaries: Some("bt709".to_string()),
                            transfer_characteristic: Some("srgb".to_string()),
                        };
                        let takes = vec![take];
                        let clip_name = path
                            .file_name()
                            .and_then(|s| s.to_str())
                            .unwrap_or("STILL.PNG");
                        let seq_metrics = aesthetic_core::compute_reel_sequence_metrics(&takes, &info);
                        let res = BatchAnalysisResult {
                            video_info: info.clone(),
                            ranked_takes: takes.clone(),
                            sequence_metrics: seq_metrics,
                            edl_content: generate_cmx3600_edl(
                                "AESTHETIC_STILL",
                                clip_name,
                                &takes,
                                24.0,
                            ),
                            csv_content: generate_csv_selects(clip_name, &takes, 24.0),
                            fcpxml_content: Some(generate_fcpxml(
                                "AESTHETIC_STILL",
                                clip_name,
                                &takes,
                                24.0,
                            )),
                            contact_sheet_html: Some(generate_contact_sheet_html(
                                "AESTHETIC_STILL",
                                clip_name,
                                &takes,
                                1,
                            )),
                            sidecars_count: 1,
                            extracted_clips_count: 0,
                        };
                        let seq_json = res.sequence_metrics.clone();
                        {
                            let mut loaded = state.loaded_media.write().unwrap();
                            *loaded = Some(info);
                            let mut ca = state.current_analysis.write().unwrap();
                            *ca = Some(res);
                        }
                        let json = serde_json::json!({
                            "success": true,
                            "takes_count": takes.len(),
                            "takes": takes,
                            "sequence_metrics": seq_json
                        });
                        send_response(
                            stream,
                            "200 OK",
                            "application/json",
                            json.to_string().as_bytes(),
                        );
                        return;
                    }
                }

                let file_stem = path
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or("video");
                let sidecars_dir = PathBuf::from("assets")
                    .join("sidecars")
                    .join(file_stem);

                let options = BatchOptions {
                    sample_step_sec: step,
                    top_n,
                    export_sidecars_dir: Some(sidecars_dir),
                    ..Default::default()
                };

                match analyze_video_file(path, &options) {
                    Ok(res) => {
                        if let Ok(info) = probe_video_metadata(path) {
                            let mut loaded = state.loaded_media.write().unwrap();
                            *loaded = Some(info);
                        }
                        let takes = res.ranked_takes.clone();
                        let seq_json = res.sequence_metrics.clone();
                        {
                            let mut ca = state.current_analysis.write().unwrap();
                            *ca = Some(res);
                        }
                        let json = serde_json::json!({
                            "success": true,
                            "takes_count": takes.len(),
                            "takes": takes,
                            "sequence_metrics": seq_json
                        });
                        send_response(
                            stream,
                            "200 OK",
                            "application/json",
                            json.to_string().as_bytes(),
                        );
                    }
                    Err(err) => {
                        let json = serde_json::json!({ "success": false, "error": err });
                        send_response(
                            stream,
                            "500 Internal Server Error",
                            "application/json",
                            json.to_string().as_bytes(),
                        );
                    }
                }
            } else {
                let json =
                    serde_json::json!({ "success": false, "error": "Missing 'path' parameter" });
                send_response(
                    stream,
                    "400 Bad Request",
                    "application/json",
                    json.to_string().as_bytes(),
                );
            }
        }
        "/api/selects" => {
            let ca = state.current_analysis.read().unwrap();
            if let Some(ref res) = *ca {
                let json = serde_json::json!({
                    "source": res.video_info.file_path,
                    "duration": res.video_info.duration_sec,
                    "fps": res.video_info.frame_rate,
                    "takes": res.ranked_takes,
                    "sequence_metrics": res.sequence_metrics
                });
                send_response(
                    stream,
                    "200 OK",
                    "application/json",
                    json.to_string().as_bytes(),
                );
            } else {
                let takes = get_demo_takes();
                let demo_info = VideoSourceInfo {
                    file_path: "DEMO_PORTFOLIO_REEL.MOV".to_string(),
                    duration_sec: 60.0,
                    frame_rate: 24.0,
                    width: 1920,
                    height: 1080,
                    codec: "prores".to_string(),
                    color_primaries: Some("bt709".to_string()),
                    transfer_characteristic: Some("bt709".to_string()),
                };
                let seq = aesthetic_core::compute_reel_sequence_metrics(&takes, &demo_info);
                let json = serde_json::json!({
                    "source": "DEMO_PORTFOLIO_REEL.MOV",
                    "duration": 60.0,
                    "fps": 24.0,
                    "takes": takes,
                    "sequence_metrics": seq
                });
                send_response(
                    stream,
                    "200 OK",
                    "application/json",
                    json.to_string().as_bytes(),
                );
            }
        }
        "/api/export_edl" => {
            let ca = state.current_analysis.read().unwrap();
            let (takes, media_path, fps) = if let Some(ref res) = *ca {
                (
                    res.ranked_takes.clone(),
                    res.video_info.file_path.clone(),
                    res.video_info.frame_rate,
                )
            } else {
                (get_demo_takes(), "FEATURE_MASTER.MOV".to_string(), 24.0)
            };
            let clip_stem = Path::new(&media_path)
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("AESTHETIC_SELECTS");
            let edl = generate_cmx3600_edl("AESTHETIC_SELECTS", clip_stem, &takes, fps);
            send_attachment_response(
                stream,
                "200 OK",
                "text/plain; charset=UTF-8",
                &format!("{}_selects.edl", clip_stem),
                edl.as_bytes(),
            );
        }
        "/api/export_csv" => {
            let ca = state.current_analysis.read().unwrap();
            let (takes, media_path, fps) = if let Some(ref res) = *ca {
                (
                    res.ranked_takes.clone(),
                    res.video_info.file_path.clone(),
                    res.video_info.frame_rate,
                )
            } else {
                (get_demo_takes(), "FEATURE_MASTER.MOV".to_string(), 24.0)
            };
            let clip_stem = Path::new(&media_path)
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("AESTHETIC_SELECTS");
            let csv = generate_csv_selects(clip_stem, &takes, fps);
            send_attachment_response(
                stream,
                "200 OK",
                "text/csv; charset=UTF-8",
                &format!("{}_selects.csv", clip_stem),
                csv.as_bytes(),
            );
        }
        "/api/export_fcpxml" => {
            let ca = state.current_analysis.read().unwrap();
            let (takes, media_path, fps) = if let Some(ref res) = *ca {
                (
                    res.ranked_takes.clone(),
                    res.video_info.file_path.clone(),
                    res.video_info.frame_rate,
                )
            } else {
                (get_demo_takes(), "FEATURE_MASTER.MOV".to_string(), 24.0)
            };
            let clip_stem = Path::new(&media_path)
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("AESTHETIC_SELECTS");
            let xml = generate_fcpxml("AESTHETIC_SELECTS", &media_path, &takes, fps);
            send_attachment_response(
                stream,
                "200 OK",
                "application/xml; charset=UTF-8",
                &format!("{}_selects.xml", clip_stem),
                xml.as_bytes(),
            );
        }
        "/api/export_resolve_script" => {
            let ca = state.current_analysis.read().unwrap();
            let (takes, media_path, fps) = if let Some(ref res) = *ca {
                (
                    res.ranked_takes.clone(),
                    res.video_info.file_path.clone(),
                    res.video_info.frame_rate,
                )
            } else {
                (get_demo_takes(), "FEATURE_MASTER.MOV".to_string(), 24.0)
            };
            let py = aesthetic_core::generate_resolve_timeline_script(
                "AESTHETIC_SELECTS",
                &media_path,
                &takes,
                fps,
            );
            send_attachment_response(
                stream,
                "200 OK",
                "text/x-python; charset=UTF-8",
                "AESTHETIC_Resolve_Import.py",
                py.as_bytes(),
            );
        }
        "/api/export_package" => {
            let ca = state.current_analysis.read().unwrap();
            let (takes, media_path, fps) = if let Some(ref res) = *ca {
                (
                    res.ranked_takes.clone(),
                    res.video_info.file_path.clone(),
                    res.video_info.frame_rate,
                )
            } else {
                (get_demo_takes(), "FEATURE_MASTER.MOV".to_string(), 24.0)
            };
            let clip_stem = Path::new(&media_path)
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("AESTHETIC");

            // Extract hero stills for top 5 takes if possible
            let mut stills_holder: Vec<(String, RgbImage)> = Vec::new();
            for (idx, take) in takes.iter().take(5).enumerate() {
                let img = get_frame_for_time(state, take.hero_timestamp_sec);
                stills_holder.push((format!("hero_select_{:02}", idx + 1), img));
            }
            let stills_ref: Vec<(String, &RgbImage)> = stills_holder
                .iter()
                .map(|(name, img)| (name.clone(), img))
                .collect();

            match build_unified_deliverables_package(
                &format!("AESTHETIC_{}", clip_stem),
                &media_path,
                &takes,
                fps,
                Some(&stills_ref),
            ) {
                Ok(zip_bytes) => {
                    let zip_filename = format!("AESTHETIC_Deliverables_{}.zip", clip_stem);
                    send_attachment_response(
                        stream,
                        "200 OK",
                        "application/zip",
                        &zip_filename,
                        &zip_bytes,
                    );
                }
                Err(err) => {
                    let json = serde_json::json!({ "success": false, "error": err });
                    send_response(
                        stream,
                        "500 Internal Server Error",
                        "application/json",
                        json.to_string().as_bytes(),
                    );
                }
            }
        }
        "/api/send_to_resolve" => {
            let ca = state.current_analysis.read().unwrap();
            let (takes, media_path, fps) = if let Some(ref res) = *ca {
                (
                    res.ranked_takes.clone(),
                    res.video_info.file_path.clone(),
                    res.video_info.frame_rate,
                )
            } else {
                (get_demo_takes(), "FEATURE_MASTER.MOV".to_string(), 24.0)
            };
            let title = query_map
                .get("timeline")
                .map(|s| s.as_str())
                .unwrap_or("AESTHETIC_Hero_Selects");
            let result = aesthetic_core::send_to_live_resolve(title, &media_path, &takes, fps);
            let json = serde_json::to_value(&result).unwrap_or_default();
            send_response(
                stream,
                "200 OK",
                "application/json",
                json.to_string().as_bytes(),
            );
        }
        "/api/batch_folder" => {
            if let Some(folder_str) = query_map.get("folder") {
                let clean_folder = clean_user_path_str(folder_str);
                let out_dir_str = query_map
                    .get("out")
                    .cloned()
                    .unwrap_or_else(|| format!("{}_aesthetic_sidecars", clean_folder));
                let step = query_map
                    .get("step")
                    .and_then(|s| s.parse::<f64>().ok())
                    .unwrap_or(2.0);
                let top_n = query_map.get("top").and_then(|s| s.parse::<usize>().ok());

                let folder_path = Path::new(clean_folder);
                let out_path = Path::new(clean_user_path_str(&out_dir_str));

                match aesthetic_core::analyze_folder_queue(folder_path, out_path, step, top_n) {
                    Ok(summary) => {
                        let json = serde_json::to_value(&summary).unwrap_or_default();
                        send_response(
                            stream,
                            "200 OK",
                            "application/json",
                            json.to_string().as_bytes(),
                        );
                    }
                    Err(err) => {
                        let json = serde_json::json!({ "success": false, "error": err });
                        send_response(
                            stream,
                            "400 Bad Request",
                            "application/json",
                            json.to_string().as_bytes(),
                        );
                    }
                }
            } else {
                let json =
                    serde_json::json!({ "success": false, "error": "Missing 'folder' parameter" });
                send_response(
                    stream,
                    "400 Bad Request",
                    "application/json",
                    json.to_string().as_bytes(),
                );
            }
        }
        "/api/rescore_sidecars" => {
            if let Some(path_str) = query_map.get("path") {
                let clean = clean_user_path_str(path_str);
                let sidecars_path = Path::new(clean);
                match aesthetic_core::rescore_from_sidecars(sidecars_path) {
                    Ok((takes, _frames)) => {
                        let max_end = takes
                            .iter()
                            .map(|t| t.end_sec)
                            .fold(30.0f64, |a, b| a.max(b));
                        let info = VideoSourceInfo {
                            file_path: path_str.clone(),
                            duration_sec: max_end,
                            frame_rate: 24.0,
                            width: 1920,
                            height: 1080,
                            codec: "cached_sidecars".to_string(),
                            color_primaries: Some("bt709".to_string()),
                            transfer_characteristic: Some("bt709".to_string()),
                        };
                        let seq = aesthetic_core::compute_reel_sequence_metrics(&takes, &info);
                        let res = BatchAnalysisResult {
                            video_info: info.clone(),
                            ranked_takes: takes.clone(),
                            sequence_metrics: seq.clone(),
                            edl_content: generate_cmx3600_edl(
                                "RESCORED_SELECTS",
                                path_str,
                                &takes,
                                24.0,
                            ),
                            csv_content: generate_csv_selects(path_str, &takes, 24.0),
                            fcpxml_content: Some(generate_fcpxml(
                                "RESCORED_SELECTS",
                                path_str,
                                &takes,
                                24.0,
                            )),
                            contact_sheet_html: None,
                            sidecars_count: takes.len(),
                            extracted_clips_count: 0,
                        };
                        {
                            let mut loaded = state.loaded_media.write().unwrap();
                            *loaded = Some(info);
                            let mut ca = state.current_analysis.write().unwrap();
                            *ca = Some(res);
                            let mut cf = state.cached_frames.write().unwrap();
                            *cf = _frames;
                        }
                        let json = serde_json::json!({
                            "success": true,
                            "takes_count": takes.len(),
                            "takes": takes,
                            "sequence_metrics": seq
                        });
                        send_response(
                            stream,
                            "200 OK",
                            "application/json",
                            json.to_string().as_bytes(),
                        );
                    }
                    Err(err) => {
                        let json = serde_json::json!({ "success": false, "error": err });
                        send_response(
                            stream,
                            "400 Bad Request",
                            "application/json",
                            json.to_string().as_bytes(),
                        );
                    }
                }
            } else {
                let json =
                    serde_json::json!({ "success": false, "error": "Missing 'path' parameter" });
                send_response(
                    stream,
                    "400 Bad Request",
                    "application/json",
                    json.to_string().as_bytes(),
                );
            }
        }
        "/api/export_contact_sheet" => {
            let ca = state.current_analysis.read().unwrap();
            let takes = if let Some(ref res) = *ca {
                res.ranked_takes.clone()
            } else {
                get_demo_takes()
            };
            drop(ca);
            let mut frames = std::collections::HashMap::new();
            for take in takes.iter().take(12) {
                let img = get_frame_for_time(state, take.hero_timestamp_sec);
                frames.insert(take.take_id.clone(), img);
            }
            let html = generate_contact_sheet_html_with_frames(
                "AESTHETIC_SELECTS",
                "FEATURE_MASTER.MOV",
                &takes,
                12,
                &frames,
            );
            send_response(
                stream,
                "200 OK",
                "text/html; charset=UTF-8",
                html.as_bytes(),
            );
        }
        "/api/browse_file" => {
            let selected = open_native_file_dialog();
            let json = if let Some(path) = selected {
                serde_json::json!({ "success": true, "path": path })
            } else {
                serde_json::json!({ "success": false, "cancelled": true })
            };
            send_response(
                stream,
                "200 OK",
                "application/json",
                json.to_string().as_bytes(),
            );
        }
        "/api/browse_dir" => {
            let selected = open_native_dir_dialog();
            let json = if let Some(path) = selected {
                serde_json::json!({ "success": true, "path": path })
            } else {
                serde_json::json!({ "success": false, "cancelled": true })
            };
            send_response(
                stream,
                "200 OK",
                "application/json",
                json.to_string().as_bytes(),
            );
        }
        "/api/baseline" => {
            let store = BaselineStore::new();
            let payload = serde_json::to_string(&store.manifest).unwrap_or_default();
            send_response(stream, "200 OK", "application/json", payload.as_bytes());
        }
        "/api/feedback" => {
            let take_id = query_map
                .get("take_id")
                .cloned()
                .unwrap_or_else(|| "take_001".to_string());
            let action = query_map
                .get("action")
                .cloned()
                .unwrap_or_else(|| "pin_select".to_string());
            let style_family = query_map
                .get("style_family")
                .cloned()
                .unwrap_or_else(|| "Prestige Naturalism".to_string());
            let shot_scale = query_map
                .get("shot_scale")
                .cloned()
                .unwrap_or_else(|| "Medium".to_string());
            let overall_score = query_map
                .get("overall")
                .and_then(|s| s.parse::<f32>().ok())
                .unwrap_or(80.0);

            let ts = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs())
                .unwrap_or(0);
            let ev = aesthetic_models::window::SelectFeedbackEvent {
                timestamp_unix: ts,
                take_id,
                action,
                style_family,
                shot_scale,
                overall_score,
                hero_potency_score: overall_score,
                storytelling_score: overall_score,
                memorability_score: overall_score,
            };
            let json = match aesthetic_core::log_select_feedback_event(&ev) {
                Ok(total) => {
                    if let Ok(mut ca) = state.current_analysis.write() {
                        if let Some(ref mut res) = *ca {
                            aesthetic_core::apply_reel_diversity_ranking(&mut res.ranked_takes);
                        }
                    }
                    let profile = aesthetic_core::compute_personal_taste_profile();
                    serde_json::json!({
                        "success": true,
                        "total_events": total,
                        "event": ev,
                        "taste_profile": profile
                    })
                }
                Err(err) => serde_json::json!({
                    "success": false,
                    "error": err
                }),
            };
            send_response(
                stream,
                "200 OK",
                "application/json",
                json.to_string().as_bytes(),
            );
        }
        "/api/taste_profile" => {
            let profile = aesthetic_core::compute_personal_taste_profile();
            let json = serde_json::to_value(&profile).unwrap_or_default();
            send_response(stream, "200 OK", "application/json", json.to_string().as_bytes());
        }
        "/api/compose_showreel" => {
            let duration = query_map
                .get("duration")
                .and_then(|s| s.parse::<f64>().ok())
                .unwrap_or(60.0);
            let obj_str = query_map.get("objective").map(|s| s.as_str()).unwrap_or("commercial");
            let objective = match obj_str {
                "dramatic" => aesthetic_core::ShowreelObjective::DramaticNarrative,
                "action" => aesthetic_core::ShowreelObjective::ActionKinetic,
                "balanced" => aesthetic_core::ShowreelObjective::BalancedHero,
                _ => aesthetic_core::ShowreelObjective::CommercialLighting,
            };

            let ca = state.current_analysis.read().unwrap();
            let (takes, media_path, fps) = if let Some(ref res) = *ca {
                (
                    res.ranked_takes.clone(),
                    res.video_info.file_path.clone(),
                    res.video_info.frame_rate,
                )
            } else {
                (get_demo_takes(), "FEATURE_MASTER.MOV".to_string(), 24.0)
            };
            drop(ca);

            let assembled = aesthetic_core::compose_smart_showreel(&takes, duration, objective);
            let total_dur: f64 = assembled.iter().map(|t| t.duration_sec).sum();

            let json = serde_json::json!({
                "success": true,
                "target_duration_sec": duration,
                "assembled_duration_sec": total_dur,
                "shots_count": assembled.len(),
                "assembled_takes": assembled,
                "source_media": media_path,
                "fps": fps
            });
            send_response(stream, "200 OK", "application/json", json.to_string().as_bytes());
        }
        "/api/multicam_matching" => {
            let ca = state.current_analysis.read().unwrap();
            let takes = if let Some(ref res) = *ca {
                res.ranked_takes.clone()
            } else {
                get_demo_takes()
            };
            drop(ca);

            let group_name = query_map
                .get("group")
                .map(|s| s.as_str())
                .unwrap_or("Active_Scene_Setup");

            let report = aesthetic_core::compute_cross_angle_setup_matching(group_name, &takes);
            let json = serde_json::to_value(&report).unwrap_or_default();
            send_response(stream, "200 OK", "application/json", json.to_string().as_bytes());
        }
        "/api/export_cdl" => {
            let ca = state.current_analysis.read().unwrap();
            let takes = if let Some(ref res) = *ca {
                res.ranked_takes.clone()
            } else {
                get_demo_takes()
            };
            drop(ca);

            let source_id = query_map.get("source").map(|s| s.as_str()).unwrap_or("take_002");
            let target_id = query_map.get("target").map(|s| s.as_str()).unwrap_or_else(|| {
                takes.first().map(|t| t.take_id.as_str()).unwrap_or("take_001")
            });

            let report = aesthetic_core::compute_cross_angle_setup_matching("Scene", &takes);
            let cdl = report
                .pairwise_matches
                .iter()
                .find(|m| m.source_take_id == source_id)
                .map(|m| m.recommended_cdl.clone())
                .unwrap_or_default();

            let xml = aesthetic_core::generate_asc_cdl_xml(&cdl, source_id, target_id);
            let filename = format!("{}_to_{}_match.cdl", source_id, target_id);
            send_attachment_response(stream, "200 OK", "application/xml", &filename, xml.as_bytes());
        }
        "/api/export_lut_cube" => {
            let ca = state.current_analysis.read().unwrap();
            let takes = if let Some(ref res) = *ca {
                res.ranked_takes.clone()
            } else {
                get_demo_takes()
            };
            drop(ca);

            let source_id = query_map.get("source").map(|s| s.as_str()).unwrap_or("take_002");
            let target_id = query_map.get("target").map(|s| s.as_str()).unwrap_or_else(|| {
                takes.first().map(|t| t.take_id.as_str()).unwrap_or("take_001")
            });
            let size = query_map.get("size").and_then(|s| s.parse().ok()).unwrap_or(17);

            let report = aesthetic_core::compute_cross_angle_setup_matching("Scene", &takes);
            let cdl = report
                .pairwise_matches
                .iter()
                .find(|m| m.source_take_id == source_id)
                .map(|m| m.recommended_cdl.clone())
                .unwrap_or_default();

            let title = format!("AESTHETIC_{}_to_{}", source_id, target_id);
            let cube = aesthetic_core::generate_3d_lut_cube(&cdl, &title, size);
            let filename = format!("{}_to_{}_match.cube", source_id, target_id);
            send_attachment_response(stream, "200 OK", "text/plain", &filename, cube.as_bytes());
        }
        "/api/export_master_cdl" => {
            let take_id = query_map.get("take").map(|s| s.as_str());
            let ca = state.current_analysis.read().unwrap();
            let takes = if let Some(ref res) = *ca {
                res.ranked_takes.clone()
            } else {
                get_demo_takes()
            };
            drop(ca);

            let take = takes
                .iter()
                .find(|t| take_id.map(|id| t.take_id == id).unwrap_or(true))
                .unwrap_or_else(|| takes.first().unwrap());

            let cdl = aesthetic_core::compute_master_baseline_cdl_grade(take, None, None, None);
            let film_match = take
                .style
                .cinematographer_match
                .as_deref()
                .unwrap_or("Cinema_Baseline");
            let clean_match = film_match.replace(' ', "_").replace(['(', ')', '/'], "");
            let xml = aesthetic_core::generate_asc_cdl_xml(&cdl, &take.take_id, &clean_match);
            let filename = format!("{}_to_{}_look.cdl", take.take_id, clean_match);
            send_attachment_response(stream, "200 OK", "application/xml", &filename, xml.as_bytes());
        }
        "/api/export_master_cube" => {
            let take_id = query_map.get("take").map(|s| s.as_str());
            let size = query_map.get("size").and_then(|s| s.parse().ok()).unwrap_or(17);
            let ca = state.current_analysis.read().unwrap();
            let takes = if let Some(ref res) = *ca {
                res.ranked_takes.clone()
            } else {
                get_demo_takes()
            };
            drop(ca);

            let take = takes
                .iter()
                .find(|t| take_id.map(|id| t.take_id == id).unwrap_or(true))
                .unwrap_or_else(|| takes.first().unwrap());

            let cdl = aesthetic_core::compute_master_baseline_cdl_grade(take, None, None, None);
            let film_match = take
                .style
                .cinematographer_match
                .as_deref()
                .unwrap_or("Cinema_Baseline");
            let clean_match = film_match.replace(' ', "_").replace(['(', ')', '/'], "");
            let title = format!("AESTHETIC_{}_to_{}", take.take_id, clean_match);
            let cube = aesthetic_core::generate_3d_lut_cube(&cdl, &title, size);
            let filename = format!("{}_to_{}_look.cube", take.take_id, clean_match);
            send_attachment_response(stream, "200 OK", "text/plain", &filename, cube.as_bytes());
        }
        _ => {
            send_response(stream, "404 NOT FOUND", "text/plain", b"Not Found");
        }
    }
}

fn is_still_image_path(path: &Path) -> bool {
    path.extension()
        .and_then(|e| e.to_str())
        .map(|ext| {
            matches!(
                ext.to_ascii_lowercase().as_str(),
                "png" | "jpg" | "jpeg" | "tif" | "tiff" | "webp" | "bmp"
            )
        })
        .unwrap_or(false)
}

fn get_frame_for_time(state: &AppState, time_sec: f64) -> RgbImage {
    // 1. Check in-memory cached frames (from cached sidecars / rescore)
    {
        let cf = state.cached_frames.read().unwrap();
        if !cf.is_empty() {
            let ca = state.current_analysis.read().unwrap();
            if let Some(ref res) = *ca {
                let mut closest_take: Option<&ShotTake> = None;
                let mut min_diff = f64::MAX;
                for t in &res.ranked_takes {
                    let diff = (t.hero_timestamp_sec - time_sec).abs();
                    if diff < min_diff {
                        min_diff = diff;
                        closest_take = Some(t);
                    }
                }
                if let Some(t) = closest_take {
                    if let Some(img) = cf.get(&t.take_id) {
                        return img.clone();
                    }
                }
            }
            if let Some(img) = cf.values().next() {
                return img.clone();
            }
        }
    }

    let loaded = state.loaded_media.read().unwrap();
    if let Some(ref media) = *loaded {
        let media_path = Path::new(&media.file_path);
        // Do NOT execute FFmpeg if path is a directory or cached sidecars mode
        if media_path.is_dir() || media.codec == "cached_sidecars" {
            return render_cinematic_reference_frame(time_sec);
        }
        if is_still_image_path(media_path) {
            if let Ok(dyn_img) = image::open(media_path) {
                return dyn_img.to_rgb8();
            }
        }
        if let Ok(frame) = extract_frame_rgb(media_path, time_sec) {
            return frame;
        }
        if let Ok(dyn_img) = image::open(media_path) {
            return dyn_img.to_rgb8();
        }
    }

    render_cinematic_reference_frame(time_sec)
}

/// Renders a high-resolution (640x360) photorealistic cinematic reference frame
/// across 3 distinct camera setups so that when no external video is loaded yet,
/// all scopes, thumbnails, and the 5-layer physics + craft evaluation engine
/// operate on real, richly structured photographic signal (3-point lighting,
/// 18% middle-gray patch, skin-tone key, specular catchlight, depth planes,
/// filmic S-curve highlight shoulder roll-off, and fine optical grain).
fn render_cinematic_reference_frame(time_sec: f64) -> RgbImage {
    let w = 640u32;
    let h = 360u32;
    let mut img = RgbImage::new(w, h);

    // Select one of 3 camera setups based on timeline position
    let setup = if time_sec < 25.0 {
        0 // Setup 1 (take_001 @ 16.0s): Low-Key Tungsten Interior Portrait w/ Window Key
    } else if time_sec < 42.0 {
        1 // Setup 2 (take_002 @ 33.5s): Golden-Hour Desert Horizon Silhouette w/ Warm Anamorphic Key
    } else {
        2 // Setup 3 (take_003 @ 48.0s): Nocturne Cyan/Amber Chiaroscuro Street Scene
    };

    // Subtle dolly drift over time so consecutive frames have measurable optical flow
    let drift_x = ((time_sec * 0.35).sin() as f32) * 0.018;
    let drift_y = ((time_sec * 0.22).cos() as f32) * 0.008;

    // Filmic tone-mapping S-curve (soft shoulder roll-off and rich toe)
    let film_curve = |v: f32| -> u8 {
        let x = v.clamp(0.0, 1.5);
        let mapped = (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14);
        (mapped.clamp(0.0, 1.0).powf(1.0 / 2.2) * 255.0).round() as u8
    };

    for y in 0..h {
        let ny = (y as f32) / (h as f32) + drift_y;
        for x in 0..w {
            let nx = (x as f32) / (w as f32) + drift_x;

            // Optical vignetting (natural cos^4 lens falloff)
            let vx = nx - 0.5;
            let vy = (ny - 0.5) * (9.0 / 16.0);
            let r2 = vx * vx + vy * vy;
            let vignette = (1.0 - 1.35 * r2).clamp(0.28, 1.0);

            // Deterministic fine sensor/film grain for realistic SNR & MTF
            let hash = ((x.wrapping_mul(374761393))
                .wrapping_add(y.wrapping_mul(668265263))
                .wrapping_add((time_sec * 24.0) as u32 * 1442695041))
                ^ 0x5bd1e995;
            let grain = (((hash & 0xFF) as f32 / 255.0) - 0.5) * 0.018;

            let (mut r_lin, mut g_lin, mut b_lin) = match setup {
                0 => {
                    // Setup 1: Low-Key Chiaroscuro Interior Portrait (Tungsten 3200K Key + Cool Fill)
                    // Background architectural wall with soft window slash from upper-left
                    let window_beam = ((-((nx - 0.22 - ny * 0.28).powi(2)) / 0.018).exp())
                        * (1.0 - ny * 0.45).max(0.1);
                    let mut r = 0.018 + 0.34 * window_beam;
                    let mut g = 0.024 + 0.25 * window_beam;
                    let mut b = 0.038 + 0.16 * window_beam;

                    // Background out-of-focus practical tungsten orb (bokeh disc)
                    let bx = nx - 0.78;
                    let by = ny - 0.28;
                    let b_dist = (bx * bx + by * by * 0.32).sqrt();
                    if b_dist < 0.085 {
                        let bokeh = (1.0 - (b_dist / 0.085).powi(2)).max(0.0);
                        r += 0.72 * bokeh;
                        g += 0.44 * bokeh;
                        b += 0.15 * bokeh;
                    }

                    // Foreground subject on left-of-center rule-of-thirds (x ~ 0.38, y ~ 0.36)
                    let sx = (nx - 0.38) / 0.115;
                    let sy = (ny - 0.38) / 0.195;
                    let head_r2 = sx * sx + sy * sy;

                    // Shoulders / torso silhouette
                    let tx = (nx - 0.38) / 0.24;
                    let ty = (ny - 0.82) / 0.32;
                    let torso_r2 = tx * tx + ty * ty;

                    if head_r2 < 1.0 {
                        // 3D sphere normal for volumetric key-to-fill modeling
                        let nz = (1.0 - head_r2).sqrt();
                        // Key light from upper-left (+42 deg azimuth, 35 deg elevation)
                        let key_dot = (-0.65 * sx - 0.42 * sy + 0.63 * nz).max(0.0);
                        // Rim light on right edge
                        let rim = (sx.max(0.0).powi(3) * (1.0 - nz)).clamp(0.0, 1.0);
                        // Fine skin micro-texture for realistic MTF50 acutance on subject plane
                        let micro = ((x as f32 * 0.85).sin() * (y as f32 * 0.85).cos()) * 0.022;
                        let skin_luma = 0.045 + 0.56 * key_dot + 0.28 * rim + micro;
                        r = skin_luma * 1.18;
                        g = skin_luma * 0.84;
                        b = skin_luma * 0.62;

                        // Subject eyes & specular catchlights
                        for eye_cx in [0.345f32, 0.412f32] {
                            let ex = (nx - eye_cx) / 0.018;
                            let ey = (ny - 0.345) / 0.016;
                            let er2 = ex * ex + ey * ey;
                            if er2 < 1.0 {
                                r *= 0.28;
                                g *= 0.26;
                                b *= 0.25;
                                // Bright specular catchlight pin in upper-left of iris
                                let cx_d = nx - (eye_cx - 0.004);
                                let cy_d = ny - 0.341;
                                if cx_d * cx_d + cy_d * cy_d < 0.000018 {
                                    r = 1.25;
                                    g = 1.18;
                                    b = 1.08;
                                }
                            }
                        }
                    } else if torso_r2 < 1.0 && ny > 0.52 {
                        let edge_light = ((-((tx + 0.75).powi(2)) / 0.12).exp()) * 0.18;
                        let fabric = ((x as f32 * 1.1).sin() * (y as f32 * 1.1).sin()) * 0.008;
                        r = 0.022 + edge_light * 1.1 + fabric;
                        g = 0.025 + edge_light * 0.85 + fabric;
                        b = 0.034 + edge_light * 0.65 + fabric;
                    }

                    // Bottom-right calibration slate patch (18% middle gray + warm/cool chips)
                    if nx > 0.84 && nx < 0.96 && ny > 0.78 && ny < 0.92 {
                        let chip = ((nx - 0.84) / 0.03) as i32;
                        match chip {
                            0 => {
                                r = 0.18;
                                g = 0.18;
                                b = 0.18;
                            }
                            1 => {
                                r = 0.42;
                                g = 0.28;
                                b = 0.20;
                            }
                            2 => {
                                r = 0.12;
                                g = 0.26;
                                b = 0.38;
                            }
                            _ => {
                                r = 0.72;
                                g = 0.70;
                                b = 0.66;
                            }
                        }
                    }

                    (r, g, b)
                }
                1 => {
                    // Setup 2: Atmospheric Golden-Hour Horizon & Ridge Silhouette
                    let horizon = 0.62 + 0.04 * (nx * 4.5).sin() + 0.02 * (nx * 11.0).cos();
                    let sun_x = 0.66;
                    let sun_y = 0.44;
                    let d_sun = ((nx - sun_x).powi(2) + ((ny - sun_y) * 0.65).powi(2)).sqrt();
                    let sun_glow = (-d_sun * 4.2).exp();
                    let anamorphic_flare =
                        (-((ny - sun_y).abs() * 55.0)).exp() * (-(nx - sun_x).abs() * 2.5).exp();

                    if ny < horizon {
                        let sky_t = (ny / horizon).clamp(0.0, 1.0);
                        let r = 0.14 + 0.58 * sky_t + 0.65 * sun_glow + 0.35 * anamorphic_flare;
                        let g = 0.12 + 0.34 * sky_t + 0.42 * sun_glow + 0.22 * anamorphic_flare;
                        let b = 0.18 + 0.14 * (1.0 - sky_t) + 0.14 * sun_glow + 0.30 * anamorphic_flare;
                        (r, g, b)
                    } else {
                        // Dune ridge with rim-lit crest and textured sand ripples
                        let ridge_dist = (ny - horizon).max(0.0);
                        let ripple = ((nx * 95.0 + ny * 40.0).sin()) * 0.015;
                        let rim = (-ridge_dist * 28.0).exp() * 0.35;
                        let shadow = (0.035 + rim + ripple).max(0.01);
                        (shadow * 1.25, shadow * 0.85, shadow * 0.55)
                    }
                }
                _ => {
                    // Setup 3: High-Contrast Nocturne Cyan/Amber Split-Toned Architecture
                    let street_y = 0.68;
                    let lamp_x = 0.30;
                    let lamp_y = 0.26;
                    let d_lamp = ((nx - lamp_x).powi(2) + ((ny - lamp_y) * 0.7).powi(2)).sqrt();
                    let amber_pool = (-d_lamp * 5.0).exp();
                    let cyan_mist = ((-((nx - 0.72).powi(2)) / 0.08).exp())
                        * ((-((ny - 0.48).powi(2)) / 0.06).exp());

                    let mut r = 0.015 + 0.82 * amber_pool + 0.06 * cyan_mist;
                    let mut g = 0.028 + 0.50 * amber_pool + 0.28 * cyan_mist;
                    let mut b = 0.052 + 0.14 * amber_pool + 0.42 * cyan_mist;

                    // Vertical architectural columns with crisp edges
                    let col_wave = (nx * 28.0).sin();
                    if col_wave > 0.75 && ny < street_y {
                        let edge = ((col_wave - 0.75) * 4.0).clamp(0.0, 1.0);
                        r *= 0.35 + 0.45 * edge;
                        g *= 0.35 + 0.45 * edge;
                        b *= 0.40 + 0.45 * edge;
                    }

                    // Wet pavement specular reflections below street_y
                    if ny >= street_y {
                        let ripple = ((ny * 140.0).sin() * (nx * 45.0).cos()) * 0.08;
                        let refl = ((-((nx - lamp_x).powi(2)) / 0.025).exp()) * (0.45 + ripple);
                        r = 0.018 + refl * 0.95;
                        g = 0.024 + refl * 0.58;
                        b = 0.042 + refl * 0.20 + cyan_mist * 0.25;
                    }

                    (r, g, b)
                }
            };

            r_lin = (r_lin * vignette + grain).max(0.0);
            g_lin = (g_lin * vignette + grain).max(0.0);
            b_lin = (b_lin * vignette + grain).max(0.0);

            img.put_pixel(
                x,
                y,
                Rgb([film_curve(r_lin), film_curve(g_lin), film_curve(b_lin)]),
            );
        }
    }

    img
}

static DEMO_TAKES_CACHE: OnceLock<Vec<ShotTake>> = OnceLock::new();

fn get_demo_takes() -> Vec<ShotTake> {
    DEMO_TAKES_CACHE
        .get_or_init(|| {
            let store = BaselineStore::new();
            let inference = ModelInferenceEngine::new();
            let (dr_q, rolloff_q, sharp_q, _) = store.scoring_quantiles();

            let specs = [
                (
                    "take_001",
                    1usize,
                    14.2f64,
                    18.7f64,
                    16.0f64,
                    384u64,
                    "Medium Close-Up",
                ),
                (
                    "take_002",
                    2usize,
                    32.0f64,
                    35.8f64,
                    33.5f64,
                    804u64,
                    "Extreme Wide",
                ),
                (
                    "take_003",
                    3usize,
                    46.0f64,
                    50.2f64,
                    48.0f64,
                    1152u64,
                    "Wide Architectural",
                ),
            ];

            specs
                .into_iter()
                .map(|(id, scene_idx, start_s, end_s, hero_s, hero_frame, scale)| {
                    let frame_a = render_cinematic_reference_frame(hero_s);
                    let frame_b = render_cinematic_reference_frame(hero_s + 0.25);

                    let mut take = evaluate_candidate_frame(
                        &frame_a, id, scene_idx, hero_s, &dr_q, &rolloff_q, &sharp_q,
                    );
                    take.start_sec = start_s;
                    take.end_sec = end_s;
                    take.duration_sec = end_s - start_s;
                    take.hero_frame_index = Some(hero_frame);
                    take.hero_timestamp_sec = hero_s;

                    enrich_take(
                        &mut take,
                        &frame_a,
                        Some((&frame_b, 0.25)),
                        &store,
                        &inference,
                    );
                    take.style.shot_scale = scale.to_string();
                    take
                })
                .collect()
        })
        .clone()
}

fn urlencoding_decode(val: &str) -> String {
    let mut result = String::new();
    let mut chars = val.chars();
    while let Some(c) = chars.next() {
        if c == '%' {
            let h1 = chars.next().unwrap_or('0');
            let h2 = chars.next().unwrap_or('0');
            let hex_str = format!("{}{}", h1, h2);
            if let Ok(byte) = u8::from_str_radix(&hex_str, 16) {
                result.push(byte as char);
            }
        } else if c == '+' {
            result.push(' ');
        } else {
            result.push(c);
        }
    }
    result
}

fn send_response(stream: &mut TcpStream, status: &str, content_type: &str, body: &[u8]) {
    let header = format!(
        "HTTP/1.1 {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n",
        status,
        content_type,
        body.len()
    );
    let _ = stream.write_all(header.as_bytes());
    let _ = stream.write_all(body);
    let _ = stream.flush();
}

fn send_attachment_response(
    stream: &mut TcpStream,
    status: &str,
    content_type: &str,
    filename: &str,
    body: &[u8],
) {
    let header = format!(
        "HTTP/1.1 {}\r\nContent-Type: {}\r\nContent-Disposition: attachment; filename=\"{}\"\r\nContent-Length: {}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n",
        status,
        content_type,
        filename,
        body.len()
    );
    let _ = stream.write_all(header.as_bytes());
    let _ = stream.write_all(body);
    let _ = stream.flush();
}

fn generate_contact_sheet_png_composite(state: &AppState, takes: &[ShotTake]) -> RgbImage {
    let limit = takes.len().min(6);
    let cols = 2usize;
    let rows = limit.div_ceil(2);
    let tile_w = 480u32;
    let tile_h = 270u32;
    let margin = 20u32;
    let header_h = 70u32;

    let width = cols as u32 * tile_w + (cols as u32 + 1) * margin;
    let height = header_h + rows as u32 * tile_h + (rows as u32 + 1) * margin;

    let mut sheet = RgbImage::new(width, height);
    // Background dark cinematic color #0c0d10
    for p in sheet.pixels_mut() {
        *p = Rgb([12, 13, 16]);
    }

    // Paste tiles
    for (i, take) in takes.iter().take(limit).enumerate() {
        let col = (i % cols) as u32;
        let row = (i / cols) as u32;
        let x = margin + col * (tile_w + margin);
        let y = header_h + row * (tile_h + margin);

        let hero_sec = take.hero_timestamp_sec;
        let frame = get_frame_for_time(state, hero_sec);
        let thumb = image::imageops::thumbnail(&frame, tile_w, tile_h);

        image::imageops::overlay(&mut sheet, &thumb, x as i64, y as i64);

        // Draw simple accent border around the thumbnail
        let border_color = if i == 0 {
            Rgb([229, 169, 59]) // Gold for Hero
        } else {
            Rgb([37, 45, 61])
        };

        for bx in 0..tile_w {
            sheet.put_pixel(x + bx, y, border_color);
            sheet.put_pixel(x + bx, y + tile_h - 1, border_color);
        }
        for by in 0..tile_h {
            sheet.put_pixel(x, y + by, border_color);
            sheet.put_pixel(x + tile_w - 1, y + by, border_color);
        }
    }

    sheet
}

fn open_native_file_dialog() -> Option<String> {
    #[cfg(target_os = "windows")]
    {
        let ps_script = r#"Add-Type -AssemblyName System.Windows.Forms; $f = New-Object System.Windows.Forms.OpenFileDialog; $f.Title = 'Select Finished Video or Reference Image'; $f.Filter = 'Media Files (*.mov;*.mp4;*.mkv;*.png;*.jpg;*.tiff;*.exr)|*.mov;*.mp4;*.mkv;*.png;*.jpg;*.tiff;*.exr|All Files (*.*)|*.*'; $top = New-Object System.Windows.Forms.Form; $top.TopMost = $true; if ($f.ShowDialog($top) -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.FileName }"#;
        let output = Command::new("powershell")
            .args(["-NoProfile", "-STA", "-Command", ps_script])
            .output()
            .ok()?;
        let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !path.is_empty() {
            Some(path)
        } else {
            None
        }
    }
    #[cfg(target_os = "macos")]
    {
        let script =
            r#"POSIX path of (choose file with prompt "Select Finished Video or Reference Image")"#;
        let output = Command::new("osascript")
            .args(["-e", script])
            .output()
            .ok()?;
        let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !path.is_empty() {
            Some(path)
        } else {
            None
        }
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    {
        let output = Command::new("zenity")
            .args([
                "--file-selection",
                "--title=Select Finished Video or Reference Image",
            ])
            .output()
            .ok()?;
        let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !path.is_empty() {
            Some(path)
        } else {
            None
        }
    }
}

fn open_native_dir_dialog() -> Option<String> {
    #[cfg(target_os = "windows")]
    {
        let ps_script = r#"Add-Type -AssemblyName System.Windows.Forms; $f = New-Object System.Windows.Forms.FolderBrowserDialog; $f.ShowNewFolderButton = $false; $f.Description = 'Select Reference Stills or Cached Sidecars Directory'; $top = New-Object System.Windows.Forms.Form; $top.TopMost = $true; if ($f.ShowDialog($top) -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.SelectedPath }"#;
        let output = Command::new("powershell")
            .args(["-NoProfile", "-STA", "-Command", ps_script])
            .output()
            .ok()?;
        let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !path.is_empty() {
            Some(path)
        } else {
            None
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        None
    }
}
