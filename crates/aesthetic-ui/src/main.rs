//! AESTHETIC Desktop UI Shell
//!
//! High-performance standalone desktop window application.
//! Serves broadcast scopes, 4-output evaluations, and interactive UI
//! via embedded zero-overhead native WebView (Edge App Mode / Chromium).

use aesthetic_core::baseline_store::BaselineStore;
use aesthetic_core::pipeline::evaluate_candidate_frame;
use aesthetic_metrics::scopes::{compute_parade, compute_waveform};
use aesthetic_models::baseline::MetricQuantiles;
use image::{Rgb, RgbImage};
use std::env;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;

const HTML_CONTENT: &str = include_str!("../ui/index.html");
const CSS_CONTENT: &str = include_str!("../ui/app.css");
const JS_CONTENT: &str = include_str!("../ui/app.js");

fn main() {
    println!("============================================================");
    println!("  AESTHETIC Desktop UI Shell (Rust v0.1.0)");
    println!("  Cinematography Intelligence & Broadcast Scopes");
    println!("============================================================");

    let args: Vec<String> = env::args().collect();
    let headless = args
        .iter()
        .any(|a| a == "--headless" || a == "--server-only");

    // Bind local ephemeral port
    let listener =
        TcpListener::bind("127.0.0.1:0").expect("Failed to bind local loopback interface");
    let port = listener
        .local_addr()
        .expect("Failed to get local port")
        .port();
    let app_url = format!("http://127.0.0.1:{}", port);
    println!("Local UI Server active on: {}", app_url);

    let running = Arc::new(AtomicBool::new(true));
    let running_clone = running.clone();

    // Spawn server thread
    let server_handle = thread::spawn(move || {
        for stream in listener.incoming() {
            if !running_clone.load(Ordering::Relaxed) {
                break;
            }
            if let Ok(mut stream) = stream {
                handle_http_request(&mut stream);
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

/// Handle incoming HTTP requests and API endpoints.
fn handle_http_request(stream: &mut TcpStream) {
    let mut buffer = [0; 4096];
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
    let path = parts[1];

    match path {
        "/" | "/index.html" => {
            send_response(
                stream,
                "200 OK",
                "text/html; charset=UTF-8",
                HTML_CONTENT.as_bytes(),
            );
        }
        "/app.css" => {
            send_response(
                stream,
                "200 OK",
                "text/css; charset=UTF-8",
                CSS_CONTENT.as_bytes(),
            );
        }
        "/app.js" => {
            send_response(
                stream,
                "200 OK",
                "application/javascript; charset=UTF-8",
                JS_CONTENT.as_bytes(),
            );
        }
        "/api/scopes" => {
            // Compute real-time broadcast scopes on test frame
            let img = RgbImage::from_pixel(320, 180, Rgb([120, 100, 180]));
            let wf = compute_waveform(&img, 64);
            let parade = compute_parade(&img, 64);

            let json = serde_json::json!({
                "waveform_density": wf.density,
                "parade_r": parade.r_density,
                "parade_g": parade.g_density,
                "parade_b": parade.b_density
            });
            let payload = json.to_string();
            send_response(stream, "200 OK", "application/json", payload.as_bytes());
        }
        "/api/evaluate" => {
            let img = RgbImage::from_pixel(640, 360, Rgb([140, 120, 100]));
            let dr_q = MetricQuantiles {
                min: 8.0,
                p10: 10.0,
                p25: 11.5,
                p50: 13.0,
                p75: 14.5,
                p90: 15.5,
                max: 17.0,
            };
            let rolloff_q = MetricQuantiles {
                min: 20.0,
                p10: 60.0,
                p25: 75.0,
                p50: 88.0,
                p75: 93.0,
                p90: 97.0,
                max: 100.0,
            };
            let sharp_q = MetricQuantiles {
                min: 5.0,
                p10: 25.0,
                p25: 60.0,
                p50: 110.0,
                p75: 160.0,
                p90: 210.0,
                max: 350.0,
            };

            let shot =
                evaluate_candidate_frame(&img, "take_001", 1, 14.5, &dr_q, &rolloff_q, &sharp_q);
            let payload = serde_json::to_string(&shot).unwrap_or_default();
            send_response(stream, "200 OK", "application/json", payload.as_bytes());
        }
        "/api/baseline" => {
            let store = BaselineStore::new();
            let payload = serde_json::to_string(&store.manifest).unwrap_or_default();
            send_response(stream, "200 OK", "application/json", payload.as_bytes());
        }
        _ => {
            send_response(stream, "404 NOT FOUND", "text/plain", b"Not Found");
        }
    }
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
