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

/// Probes video file metadata using FFprobe or FFmpeg fallback.
pub fn probe_video_metadata(video_path: &Path) -> Result<VideoSourceInfo, String> {
    if let Some(ffprobe) = find_ffprobe() {
        if ffprobe.exists() {
            if let Ok(meta) = probe_with_ffprobe(&ffprobe, video_path) {
                return Ok(meta);
            }
        }
    }
    probe_with_ffmpeg(video_path)
}

fn probe_with_ffprobe(ffprobe: &Path, video_path: &Path) -> Result<VideoSourceInfo, String> {
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

fn probe_with_ffmpeg(video_path: &Path) -> Result<VideoSourceInfo, String> {
    let ffmpeg = find_ffmpeg().ok_or_else(|| "ffmpeg not found".to_string())?;

    let output = Command::new(ffmpeg)
        .args(["-i", video_path.to_str().unwrap_or_default()])
        .output()
        .map_err(|e| format!("Failed to execute ffmpeg: {}", e))?;

    let stderr = String::from_utf8_lossy(&output.stderr);

    let mut duration_sec = 0.0;
    if let Some(dur_idx) = stderr.find("Duration: ") {
        let sub = &stderr[dur_idx + 10..];
        if let Some(comma) = sub.find(',') {
            let tc = sub[..comma].trim();
            let parts: Vec<&str> = tc.split(':').collect();
            if parts.len() == 3 {
                let h: f64 = parts[0].parse().unwrap_or(0.0);
                let m: f64 = parts[1].parse().unwrap_or(0.0);
                let s: f64 = parts[2].parse().unwrap_or(0.0);
                duration_sec = h * 3600.0 + m * 60.0 + s;
            }
        }
    }

    let mut width = 1920;
    let mut height = 1080;
    let mut fps = 24.0;
    let mut codec = "unknown".to_string();

    for line in stderr.lines() {
        if line.contains("Stream #") && line.contains("Video:") {
            if let Some(v_idx) = line.find("Video: ") {
                let rest = &line[v_idx + 7..];
                let tokens: Vec<&str> = rest.split(',').collect();
                if let Some(c) = tokens.first() {
                    codec = c.split_whitespace().next().unwrap_or("unknown").to_string();
                }

                for tok in &tokens {
                    let t = tok.trim();
                    if let Some(x_idx) = t.find('x') {
                        let w_part = t[..x_idx].split_whitespace().last().unwrap_or("");
                        let h_part = t[x_idx + 1..].split_whitespace().next().unwrap_or("");
                        if let (Ok(w), Ok(h)) = (w_part.parse::<u32>(), h_part.parse::<u32>()) {
                            if w >= 320 && h >= 240 {
                                width = w;
                                height = h;
                            }
                        }
                    }
                    if t.ends_with("fps") {
                        let fps_str = t.trim_end_matches("fps").trim();
                        if let Ok(f) = fps_str.parse::<f64>() {
                            fps = f;
                        }
                    }
                }
            }
            break;
        }
    }

    Ok(VideoSourceInfo {
        file_path: video_path.to_string_lossy().to_string(),
        duration_sec,
        frame_rate: fps,
        width,
        height,
        codec,
        color_primaries: None,
        transfer_characteristic: None,
    })
}

/// Extracts a single frame at the specified timestamp as an RGB image.
pub fn extract_frame_rgb(video_path: &Path, timestamp_sec: f64) -> Result<image::RgbImage, String> {
    let frames = extract_frames_burst(video_path, timestamp_sec, 1, 1.0, None)?;
    frames
        .into_iter()
        .next()
        .ok_or_else(|| "Failed to extract frame".to_string())
}

/// Extracts a burst of RGB frames at `timestamp_sec` at the given sample rate `fps` and frame count.
/// Executes a single FFmpeg invocation and seek to minimize network latency on remote media servers.
pub fn extract_frames_burst(
    video_path: &Path,
    timestamp_sec: f64,
    frame_count: usize,
    sample_fps: f64,
    max_width: Option<u32>,
) -> Result<Vec<image::RgbImage>, String> {
    let ffmpeg = find_ffmpeg().ok_or_else(|| "ffmpeg not found".to_string())?;

    let mut filter_parts = Vec::new();
    if frame_count > 1 {
        filter_parts.push(format!("fps={:.2}", sample_fps));
    }
    if let Some(mw) = max_width {
        filter_parts.push(format!("scale='min({},iw)':-2", mw));
    }
    filter_parts.push("format=rgb24".to_string());
    let vf_filter = filter_parts.join(",");

    let mut args = vec![
        "-ss".to_string(),
        format!("{:.3}", timestamp_sec),
        "-i".to_string(),
        video_path.to_str().unwrap_or_default().to_string(),
        "-vf".to_string(),
        vf_filter,
    ];

    args.extend([
        "-vframes".to_string(),
        frame_count.to_string(),
        "-pix_fmt".to_string(),
        "rgb24".to_string(),
        "-vcodec".to_string(),
        "ppm".to_string(),
        "-f".to_string(),
        "image2pipe".to_string(),
        "-".to_string(),
    ]);

    let output = Command::new(ffmpeg)
        .args(&args)
        .output()
        .map_err(|e| format!("Failed to execute ffmpeg: {}", e))?;

    if !output.status.success() || output.stdout.is_empty() {
        return Err(format!(
            "ffmpeg frame burst extraction failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    let frames = parse_ppm_frames(&output.stdout);
    if frames.is_empty() {
        return Err("No valid frames decoded from ffmpeg burst".to_string());
    }

    Ok(frames)
}

/// Parses concatenated PPM (P6) binary frames from a buffer, supporting both 8-bit (max_val=255)
/// and 16-bit HDR (max_val=65535, rgb48be) formats.
fn parse_ppm_frames(data: &[u8]) -> Vec<image::RgbImage> {
    let mut images = Vec::new();
    let mut cursor = 0;
    let len = data.len();

    while cursor + 3 < len {
        // Find 'P6'
        if data[cursor] != b'P' || data[cursor + 1] != b'6' {
            cursor += 1;
            continue;
        }
        cursor += 2;

        let skip_ws_and_comments = |cur: &mut usize| {
            while *cur < len {
                let b = data[*cur];
                if b == b'#' {
                    while *cur < len && data[*cur] != b'\n' {
                        *cur += 1;
                    }
                } else if b == b' ' || b == b'\t' || b == b'\r' || b == b'\n' {
                    *cur += 1;
                } else {
                    break;
                }
            }
        };

        skip_ws_and_comments(&mut cursor);

        let mut width: u32 = 0;
        while cursor < len && data[cursor].is_ascii_digit() {
            width = width
                .saturating_mul(10)
                .saturating_add((data[cursor] - b'0') as u32);
            cursor += 1;
        }

        skip_ws_and_comments(&mut cursor);

        let mut height: u32 = 0;
        while cursor < len && data[cursor].is_ascii_digit() {
            height = height
                .saturating_mul(10)
                .saturating_add((data[cursor] - b'0') as u32);
            cursor += 1;
        }

        skip_ws_and_comments(&mut cursor);

        let mut max_val: u32 = 0;
        while cursor < len && data[cursor].is_ascii_digit() {
            max_val = max_val
                .saturating_mul(10)
                .saturating_add((data[cursor] - b'0') as u32);
            cursor += 1;
        }

        if cursor < len && (data[cursor] == b'\n' || data[cursor] == b' ' || data[cursor] == b'\r')
        {
            cursor += 1;
        }

        if width == 0 || height == 0 {
            break;
        }

        if max_val == 255 {
            let frame_bytes = (width as usize)
                .checked_mul(height as usize)
                .and_then(|wh| wh.checked_mul(3));
            let Some(byte_len) = frame_bytes else {
                break;
            };

            if cursor + byte_len <= len {
                let buffer = data[cursor..cursor + byte_len].to_vec();
                if let Some(img) = image::RgbImage::from_raw(width, height, buffer) {
                    images.push(img);
                }
                cursor += byte_len;
            } else {
                break;
            }
        } else if max_val == 65535 {
            // 16-bit big endian: 6 bytes per pixel. Downscale high byte to 8-bit.
            let frame_bytes = (width as usize)
                .checked_mul(height as usize)
                .and_then(|wh| wh.checked_mul(6));
            let Some(byte_len) = frame_bytes else {
                break;
            };

            if cursor + byte_len <= len {
                let raw_16 = &data[cursor..cursor + byte_len];
                let mut buffer_8 = Vec::with_capacity((width as usize) * (height as usize) * 3);
                for chunk in raw_16.as_chunks::<2>().0 {
                    buffer_8.push(chunk[0]); // High byte of big-endian u16
                }
                if let Some(img) = image::RgbImage::from_raw(width, height, buffer_8) {
                    images.push(img);
                }
                cursor += byte_len;
            } else {
                break;
            }
        } else {
            break;
        }
    }

    images
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
