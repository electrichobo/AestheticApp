//! Editorial & Selects Export Engine
//!
//! Generates industry-standard CMX 3600 EDLs, CSV selects manifests,
//! and clips packages for editorial handoff in DaVinci Resolve,
//! Premiere Pro, and Avid Media Composer.

use aesthetic_models::ShotTake;
use std::fmt::Write as FmtWrite;

/// Formats a time in seconds into an SMPTE timecode string (HH:MM:SS:FF).
pub fn seconds_to_smpte_timecode(seconds: f64, fps: f64) -> String {
    let fps = if fps <= 0.0 { 24.0 } else { fps };
    let total_frames = (seconds * fps).round() as u64;

    let frames_per_second = fps.round() as u64;
    let frames_per_minute = frames_per_second * 60;
    let frames_per_hour = frames_per_minute * 60;

    let hours = total_frames / frames_per_hour;
    let rem = total_frames % frames_per_hour;

    let minutes = rem / frames_per_minute;
    let rem = rem % frames_per_minute;

    let secs = rem / frames_per_second;
    let frames = rem % frames_per_second;

    format!("{:02}:{:02}:{:02}:{:02}", hours, minutes, secs, frames)
}

/// Generates a CMX 3600 standard Edit Decision List (EDL) from ranked shot selects.
pub fn generate_cmx3600_edl(
    title: &str,
    source_clip_name: &str,
    takes: &[ShotTake],
    fps: f64,
) -> String {
    let mut edl = String::new();
    let _ = writeln!(edl, "TITLE: {}", title.to_uppercase());
    let _ = writeln!(edl, "FCM: NON-DROP FRAME\n");

    let mut record_in_sec = 3600.0; // Standard 01:00:00:00 timeline start

    for (idx, take) in takes.iter().enumerate() {
        let event_num = idx + 1;
        let reel_name = "AX";
        let track_type = "V     C"; // Video, Cut

        let src_in_tc = seconds_to_smpte_timecode(take.start_sec, fps);
        let src_out_tc = seconds_to_smpte_timecode(take.end_sec, fps);

        let duration_sec = (take.end_sec - take.start_sec).max(0.0);
        let rec_in_tc = seconds_to_smpte_timecode(record_in_sec, fps);
        let rec_out_tc = seconds_to_smpte_timecode(record_in_sec + duration_sec, fps);

        let _ = writeln!(
            edl,
            "{:03}  {:<8} {}        {} {} {} {}",
            event_num, reel_name, track_type, src_in_tc, src_out_tc, rec_in_tc, rec_out_tc
        );

        let _ = writeln!(edl, "* FROM CLIP NAME: {}", source_clip_name);
        let _ = writeln!(
            edl,
            "* AESTHETIC SCORE: {:.1} (TECH: {:.1}, CREATIVE: {:.1}, TEMPORAL: {:.1})",
            take.scores.overall, take.scores.technical, take.scores.creative, take.scores.temporal
        );
        let match_str = take
            .style
            .cinematographer_match
            .as_deref()
            .unwrap_or("Baseline Match");
        let _ = writeln!(
            edl,
            "* STYLE: {} [{}] (MOTION: {}, SCALE: {})",
            match_str, take.style.lighting_key, take.style.motion_type, take.style.shot_scale
        );

        if !take.concerns.is_empty() {
            let concerns_str: Vec<String> = take
                .concerns
                .iter()
                .map(|c| format!("{}: {}", c.code, c.description))
                .collect();
            let _ = writeln!(edl, "* CONCERNS: {}", concerns_str.join(" | "));
        }

        let _ = writeln!(edl);
        record_in_sec += duration_sec;
    }

    edl
}

/// Generates a CSV selects manifest detailing each recommended take.
pub fn generate_csv_selects(source_clip_name: &str, takes: &[ShotTake], fps: f64) -> String {
    let mut csv = String::new();
    let _ = writeln!(
        csv,
        "Take Index,Source Clip,In Timecode,Out Timecode,Duration (s),Overall Score,Technical Score,Creative Score,Temporal Score,Lighting Key,Motion Type,Shot Scale,DP Match,Concerns Count"
    );

    for (idx, take) in takes.iter().enumerate() {
        let src_in_tc = seconds_to_smpte_timecode(take.start_sec, fps);
        let src_out_tc = seconds_to_smpte_timecode(take.end_sec, fps);
        let duration = (take.end_sec - take.start_sec).max(0.0);
        let dp_match = take
            .style
            .cinematographer_match
            .as_deref()
            .unwrap_or("Baseline");

        let _ = writeln!(
            csv,
            "{},\"{}\",{},{},{:.2},{:.1},{:.1},{:.1},{:.1},\"{}\",\"{}\",\"{}\",\"{}\",{}",
            idx + 1,
            source_clip_name,
            src_in_tc,
            src_out_tc,
            duration,
            take.scores.overall,
            take.scores.technical,
            take.scores.creative,
            take.scores.temporal,
            take.style.lighting_key,
            take.style.motion_type,
            take.style.shot_scale,
            dp_match,
            take.concerns.len()
        );
    }

    csv
}

#[cfg(test)]
mod tests {
    use super::*;
    use aesthetic_models::{DiscoveredStyle, PillarScores};

    #[test]
    fn test_seconds_to_smpte_timecode() {
        assert_eq!(seconds_to_smpte_timecode(0.0, 24.0), "00:00:00:00");
        assert_eq!(seconds_to_smpte_timecode(1.0, 24.0), "00:00:01:00");
        assert_eq!(seconds_to_smpte_timecode(65.5, 24.0), "00:01:05:12");
        assert_eq!(seconds_to_smpte_timecode(3661.0, 25.0), "01:01:01:00");
    }

    #[test]
    fn test_generate_edl_and_csv() {
        let take = ShotTake {
            take_id: "take_001".to_string(),
            scene_index: 1,
            start_sec: 10.0,
            end_sec: 14.5,
            duration_sec: 4.5,
            hero_frame_index: Some(240),
            hero_timestamp_sec: 12.0,
            scores: PillarScores {
                overall: 90.5,
                technical: 91.0,
                creative: 88.0,
                temporal: 93.0,
            },
            style: DiscoveredStyle {
                lighting_key: "Low-Key".to_string(),
                motion_type: "Smooth Track / Dolly".to_string(),
                shot_scale: "Medium Close-Up".to_string(),
                cinematographer_match: Some("Roger Deakins (Skyfall)".to_string()),
                match_confidence: 94.2,
            },
            measured: Default::default(),
            concerns: vec![],
        };

        let edl = generate_cmx3600_edl(
            "REEL_SELECTS",
            "FEATURE_MEZZANINE.MOV",
            std::slice::from_ref(&take),
            24.0,
        );
        assert!(edl.contains("TITLE: REEL_SELECTS"));
        assert!(edl.contains("001  AX"));
        assert!(edl.contains("00:00:10:00 00:00:14:12 01:00:00:00 01:00:04:12"));
        assert!(edl.contains("* FROM CLIP NAME: FEATURE_MEZZANINE.MOV"));
        assert!(edl.contains("* AESTHETIC SCORE: 90.5"));
        assert!(edl.contains("* STYLE: Roger Deakins (Skyfall) [Low-Key]"));

        let csv = generate_csv_selects("FEATURE_MEZZANINE.MOV", &[take], 24.0);
        assert!(csv.contains("Take Index,Source Clip"));
        assert!(csv.contains("1,\"FEATURE_MEZZANINE.MOV\",00:00:10:00,00:00:14:12,4.50,90.5"));
        assert!(csv.contains("\"Roger Deakins (Skyfall)\""));
    }
}
