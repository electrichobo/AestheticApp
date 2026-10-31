//! Web Video Ingest (YouTube, Vimeo, Web Streams)
//!
//! Downloads or streams video from web URLs using yt-dlp sidecar integration.

use aesthetic_models::manifest::VideoSourceInfo;
use std::path::{Path, PathBuf};
use std::process::Command;

/// Locate the yt-dlp executable.
pub fn find_ytdlp() -> Option<PathBuf> {
    let local_tools = Path::new("tools").join("yt-dlp.exe");
    if local_tools.exists() {
        return Some(local_tools);
    }

    if let Ok(current_exe) = std::env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            let adjacent = parent.join("yt-dlp.exe");
            if adjacent.exists() {
                return Some(adjacent);
            }
        }
    }

    Some(PathBuf::from("yt-dlp"))
}

/// Probes metadata for a remote video URL without downloading the media payload.
pub fn probe_web_url(url: &str) -> Result<VideoSourceInfo, String> {
    let ytdlp = find_ytdlp().ok_or_else(|| "yt-dlp not found".to_string())?;

    let output = Command::new(ytdlp)
        .args(["--dump-json", "--no-playlist", "--skip-download", url])
        .output()
        .map_err(|e| format!("Failed to run yt-dlp: {}", e))?;

    if !output.status.success() {
        return Err(format!(
            "yt-dlp probe failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    let json_str = String::from_utf8_lossy(&output.stdout);
    let val: serde_json::Value = serde_json::from_str(&json_str)
        .map_err(|e| format!("Failed to parse yt-dlp JSON: {}", e))?;

    let duration_sec = val["duration"].as_f64().unwrap_or(0.0);
    let width = val["width"].as_u64().unwrap_or(1920) as u32;
    let height = val["height"].as_u64().unwrap_or(1080) as u32;
    let fps = val["fps"].as_f64().unwrap_or(24.0);
    let vcodec = val["vcodec"].as_str().unwrap_or("unknown").to_string();

    Ok(VideoSourceInfo {
        file_path: url.to_string(),
        duration_sec,
        frame_rate: fps,
        width,
        height,
        codec: vcodec,
        color_primaries: None,
        transfer_characteristic: None,
    })
}

/// Downloads web video from URL to target cache directory.
pub fn download_web_video(url: &str, output_dir: &Path) -> Result<PathBuf, String> {
    let ytdlp = find_ytdlp().ok_or_else(|| "yt-dlp not found".to_string())?;

    let output_template = output_dir.join("%(id)s.%(ext)s");

    let output = Command::new(ytdlp)
        .args([
            "-f",
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--no-playlist",
            "-o",
            output_template.to_str().unwrap_or_default(),
            url,
        ])
        .output()
        .map_err(|e| format!("Failed to execute yt-dlp download: {}", e))?;

    if !output.status.success() {
        return Err(format!(
            "Download failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    // Return the downloaded file path in output_dir
    Ok(output_dir.to_path_buf())
}
