//! Video Ingest and Demuxing
//!
//! Probes video metadata and extracts frames using FFmpeg without
//! requiring complex native C library bindings.

use aesthetic_models::manifest::VideoSourceInfo;
use std::path::{Path, PathBuf};
use std::process::Command;

/// Locate the FFmpeg executable (checks tools/, adjacent to executable, or system PATH).
pub fn find_ffmpeg() -> Option<PathBuf> {
    // 1. Check tools/ directory relative to workspace root
    let local_tools = Path::new("tools").join("ffmpeg.exe");
    if local_tools.exists() {
        return Some(local_tools);
    }

    // 2. Check adjacent to current running binary
    if let Ok(current_exe) = std::env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            let adjacent = parent.join("ffmpeg.exe");
            if adjacent.exists() {
                return Some(adjacent);
            }
        }
    }

    // 3. Fallback to system PATH
    Some(PathBuf::from("ffmpeg"))
}

/// Locate the FFprobe executable.
pub fn find_ffprobe() -> Option<PathBuf> {
    let local_tools = Path::new("tools").join("ffprobe.exe");
    if local_tools.exists() {
        return Some(local_tools);
    }
    Some(PathBuf::from("ffprobe"))
}

/// Probes video file metadata.
pub fn probe_video_metadata(video_path: &Path) -> Result<VideoSourceInfo, String> {
    let ffprobe = find_ffprobe().ok_or_else(|| "ffprobe not found".to_string())?;

    let output = Command::new(ffprobe)
        .args([
            "-v",
            "error",
            "-show_entries",
            "stream=width,height,r_frame_rate,codec_name,color_primaries,color_transfer:format=duration",
            "-of",
            "json",
            video_path.to_str().unwrap_or_default(),
        ])
        .output()
        .map_err(|e| format!("Failed to execute ffprobe: {}", e))?;

    if !output.status.success() {
        return Err(format!(
            "ffprobe failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    let json_str = String::from_utf8_lossy(&output.stdout);
    let val: serde_json::Value =
        serde_json::from_str(&json_str).map_err(|e| format!("JSON parse error: {}", e))?;

    let duration_sec = val["format"]["duration"]
        .as_str()
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);

    let stream = &val["streams"][0];
    let width = stream["width"].as_u64().unwrap_or(1920) as u32;
    let height = stream["height"].as_u64().unwrap_or(1080) as u32;
    let codec = stream["codec_name"]
        .as_str()
        .unwrap_or("unknown")
        .to_string();

    // Parse frame rate (e.g. "24/1" or "30000/1001")
    let fps = if let Some(fps_str) = stream["r_frame_rate"].as_str() {
        if let Some((num, den)) = fps_str.split_once('/') {
            let n: f64 = num.parse().unwrap_or(24.0);
            let d: f64 = den.parse().unwrap_or(1.0);
            if d > 0.0 {
                n / d
            } else {
                24.0
            }
        } else {
            24.0
        }
    } else {
        24.0
    };

    Ok(VideoSourceInfo {
        file_path: video_path.to_string_lossy().to_string(),
        duration_sec,
        frame_rate: fps,
        width,
        height,
        codec,
        color_primaries: stream["color_primaries"].as_str().map(|s| s.to_string()),
        transfer_characteristic: stream["color_transfer"].as_str().map(|s| s.to_string()),
    })
}

/// Extracts a single frame at the specified timestamp as an RGB image.
pub fn extract_frame_rgb(video_path: &Path, timestamp_sec: f64) -> Result<image::RgbImage, String> {
    let ffmpeg = find_ffmpeg().ok_or_else(|| "ffmpeg not found".to_string())?;

    let output = Command::new(ffmpeg)
        .args([
            "-ss",
            &format!("{:.3}", timestamp_sec),
            "-i",
            video_path.to_str().unwrap_or_default(),
            "-vframes",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "ppm",
            "-",
        ])
        .output()
        .map_err(|e| format!("Failed to execute ffmpeg: {}", e))?;

    if !output.status.success() || output.stdout.is_empty() {
        return Err(format!(
            "ffmpeg frame extraction failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    let dynamic_img = image::load_from_memory_with_format(&output.stdout, image::ImageFormat::Pnm)
        .map_err(|e| format!("Failed to decode PPM frame: {}", e))?;

    Ok(dynamic_img.to_rgb8())
}

/// Trims a sub-clip with optional padding handles and writes to output_path.
pub fn extract_trimmed_clip(
    video_path: &Path,
    start_sec: f64,
    duration_sec: f64,
    output_path: &Path,
) -> Result<(), String> {
    let ffmpeg = find_ffmpeg().ok_or_else(|| "ffmpeg not found".to_string())?;

    let status = Command::new(ffmpeg)
        .args([
            "-y",
            "-ss",
            &format!("{:.3}", start_sec),
            "-i",
            video_path.to_str().unwrap_or_default(),
            "-t",
            &format!("{:.3}", duration_sec),
            "-c",
            "copy",
            output_path.to_str().unwrap_or_default(),
        ])
        .status()
        .map_err(|e| format!("Failed to execute ffmpeg trim: {}", e))?;

    if !status.success() {
        return Err("ffmpeg clip extraction failed".to_string());
    }

    Ok(())
}
