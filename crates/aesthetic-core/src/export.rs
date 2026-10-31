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

/// Generates an FCPXML (Final Cut Pro / DaVinci Resolve) timeline project.
pub fn generate_fcpxml(title: &str, media_path: &str, takes: &[ShotTake], fps: f64) -> String {
    let fps = if fps <= 0.0 { 24.0 } else { fps };
    let frame_duration = format!("100/{}00s", (fps * 100.0).round() as u64);

    let total_duration_sec: f64 = takes
        .iter()
        .map(|t| (t.end_sec - t.start_sec).max(0.0))
        .sum();

    let mut xml = String::new();
    let _ = writeln!(xml, r#"<?xml version="1.0" encoding="UTF-8"?>"#);
    let _ = writeln!(xml, r#"<!DOCTYPE fcpxml>"#);
    let _ = writeln!(xml, r#"<fcpxml version="1.9">"#);
    let _ = writeln!(xml, r#"  <resources>"#);
    let _ = writeln!(
        xml,
        r#"    <format id="r1" name="FFVideoFormat1080p{}" frameDuration="{}"/>"#,
        fps.round() as u64,
        frame_duration
    );
    let file_name = std::path::Path::new(media_path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("MEDIA");
    let _ = writeln!(
        xml,
        r#"    <asset id="r2" name="{}" src="file://localhost/{}" format="r1"/>"#,
        file_name,
        media_path.replace('\\', "/")
    );
    let _ = writeln!(xml, r#"  </resources>"#);
    let _ = writeln!(xml, r#"  <library>"#);
    let _ = writeln!(xml, r#"    <event name="AESTHETIC Showreel Selects">"#);
    let _ = writeln!(xml, r#"      <project name="{}">"#, title);
    let _ = writeln!(
        xml,
        r#"        <sequence format="r1" duration="{}/{}s">"#,
        (total_duration_sec * 2400.0).round() as u64,
        2400
    );
    let _ = writeln!(xml, r#"          <spine>"#);

    let mut offset_frames = 0u64;

    for take in takes {
        let duration_sec = (take.end_sec - take.start_sec).max(0.0);
        let duration_frames = (duration_sec * fps).round() as u64;
        let start_frames = (take.start_sec * fps).round() as u64;

        let dp_match = take
            .style
            .cinematographer_match
            .as_deref()
            .unwrap_or("Baseline Match");

        let note = format!(
            "Score: {:.1} (Tech: {:.1}, Creat: {:.1}, Temp: {:.1}) | DP: {} | Key: {}",
            take.scores.overall,
            take.scores.technical,
            take.scores.creative,
            take.scores.temporal,
            dp_match,
            take.style.lighting_key
        );

        let _ = writeln!(
            xml,
            r#"            <asset-clip name="{} ({})" ref="r2" offset="{}/{}s" duration="{}/{}s" start="{}/{}s">"#,
            take.take_id,
            dp_match,
            (offset_frames as f64 * 100.0).round() as u64,
            (fps * 100.0).round() as u64,
            (duration_frames as f64 * 100.0).round() as u64,
            (fps * 100.0).round() as u64,
            (start_frames as f64 * 100.0).round() as u64,
            (fps * 100.0).round() as u64
        );
        let _ = writeln!(xml, r#"              <note>{}</note>"#, note);
        let _ = writeln!(
            xml,
            r#"              <marker start="{}/{}s" duration="100/{}00s" value="Hero Frame [Score: {:.1}]"/>"#,
            ((start_frames + duration_frames / 2) as f64 * 100.0).round() as u64,
            (fps * 100.0).round() as u64,
            fps.round() as u64,
            take.scores.overall
        );
        let _ = writeln!(xml, r#"            </asset-clip>"#);

        offset_frames += duration_frames;
    }

    let _ = writeln!(xml, r#"          </spine>"#);
    let _ = writeln!(xml, r#"        </sequence>"#);
    let _ = writeln!(xml, r#"      </project>"#);
    let _ = writeln!(xml, r#"    </event>"#);
    let _ = writeln!(xml, r#"  </library>"#);
    let _ = writeln!(xml, r#"</fcpxml>"#);

    xml
}

/// Generates a standalone, dark-themed HTML visual contact sheet of top selects.
pub fn generate_contact_sheet_html(
    title: &str,
    media_file: &str,
    takes: &[ShotTake],
    top_n: usize,
) -> String {
    let limit = if top_n == 0 {
        takes.len()
    } else {
        top_n.min(takes.len())
    };
    let selects = &takes[..limit];

    let mut html = String::new();
    let _ = writeln!(html, "<!DOCTYPE html>");
    let _ = writeln!(html, "<html lang=\"en\">");
    let _ = writeln!(html, "<head>");
    let _ = writeln!(html, "  <meta charset=\"UTF-8\">");
    let _ = writeln!(
        html,
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
    );
    let _ = writeln!(html, "  <title>AESTHETIC Contact Sheet — {}</title>", title);
    let _ = writeln!(html, "  <style>");
    let _ = writeln!(
        html,
        r#"
    :root {{
      --bg: #0c0d0f;
      --panel: #14161a;
      --card: #1a1d24;
      --accent: #e5a93c;
      --text: #e8eaed;
      --text-muted: #8a919e;
      --border: #282c35;
      --green: #4ade80;
      --cyan: #38bdf8;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      padding: 32px 24px;
      line-height: 1.5;
    }}
    header {{
      max-width: 1400px;
      margin: 0 auto 32px auto;
      border-bottom: 1px solid var(--border);
      padding-bottom: 20px;
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
    }}
    h1 {{ font-size: 26px; font-weight: 700; letter-spacing: -0.5px; color: #fff; }}
    .subtitle {{ color: var(--text-muted); font-size: 14px; margin-top: 4px; }}
    .badge-count {{
      background: var(--accent);
      color: #000;
      font-weight: 700;
      font-size: 13px;
      padding: 6px 14px;
      border-radius: 999px;
    }}
    .grid {{
      max-width: 1400px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
      gap: 24px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }}
    .card-top {{
      padding: 16px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
      background: #15181f;
    }}
    .rank-tag {{ font-weight: 800; font-size: 18px; color: var(--accent); }}
    .score-badge {{
      background: rgba(229, 169, 60, 0.15);
      border: 1px solid var(--accent);
      color: var(--accent);
      font-weight: 700;
      font-size: 15px;
      padding: 4px 10px;
      border-radius: 6px;
    }}
    .card-body {{ padding: 20px; display: flex; flex-direction: column; gap: 14px; flex: 1; }}
    .timecode-row {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
    }}
    .score-bars {{ display: flex; flex-direction: column; gap: 6px; }}
    .score-bar-row {{ display: flex; align-items: center; justify-content: space-between; font-size: 12px; }}
    .bar-track {{ flex: 1; height: 6px; background: #262a33; border-radius: 3px; margin: 0 10px; overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 3px; }}
    .fill-tech {{ background: var(--cyan); }}
    .fill-creat {{ background: var(--accent); }}
    .fill-temp {{ background: var(--green); }}
    .master-banner {{
      background: #20242d;
      border: 1px solid #333844;
      border-radius: 6px;
      padding: 10px 14px;
      font-size: 13px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .master-icon {{ color: var(--accent); font-size: 16px; }}
    .tags-row {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .tag {{
      background: #222630;
      color: var(--text-muted);
      font-size: 11px;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    "#
    );
    let _ = writeln!(html, "  </style>");
    let _ = writeln!(html, "</head>");
    let _ = writeln!(html, "<body>");
    let _ = writeln!(html, "  <header>");
    let _ = writeln!(html, "    <div>");
    let _ = writeln!(
        html,
        "      <h1>AESTHETIC &mdash; Top {} Selects Breakout</h1>",
        limit
    );
    let _ = writeln!(html, "      <div class=\"subtitle\">Source Media: {} | Ranked against Golden Baseline cinema</div>", media_file);
    let _ = writeln!(html, "    </div>");
    let _ = writeln!(
        html,
        "    <div class=\"badge-count\">{} Hero Shots</div>",
        limit
    );
    let _ = writeln!(html, "  </header>");
    let _ = writeln!(html, "  <main class=\"grid\">");

    for (idx, take) in selects.iter().enumerate() {
        let rank = idx + 1;
        let dp_match = take
            .style
            .cinematographer_match
            .as_deref()
            .unwrap_or("Cinema Reference Match");

        let duration = (take.end_sec - take.start_sec).max(0.0);
        let in_tc = seconds_to_smpte_timecode(take.start_sec, 24.0);
        let out_tc = seconds_to_smpte_timecode(take.end_sec, 24.0);

        let _ = writeln!(html, "    <article class=\"card\">");
        let _ = writeln!(html, "      <div class=\"card-top\">");
        let _ = writeln!(
            html,
            "        <span class=\"rank-tag\">#{} &mdash; {}</span>",
            rank, take.take_id
        );
        let _ = writeln!(
            html,
            "        <span class=\"score-badge\">{:.1} / 100</span>",
            take.scores.overall
        );
        let _ = writeln!(html, "      </div>");
        let _ = writeln!(html, "      <div class=\"card-body\">");
        let _ = writeln!(html, "        <div class=\"timecode-row\">");
        let _ = writeln!(html, "          <span>{} &rarr; {}</span>", in_tc, out_tc);
        let _ = writeln!(html, "          <span>{:.1}s</span>", duration);
        let _ = writeln!(html, "        </div>");

        let _ = writeln!(html, "        <div class=\"score-bars\">");
        let _ = writeln!(html, "          <div class=\"score-bar-row\"><span>Technical</span><div class=\"bar-track\"><div class=\"bar-fill fill-tech\" style=\"width:{:.0}%\"></div></div><span>{:.1}</span></div>", take.scores.technical, take.scores.technical);
        let _ = writeln!(html, "          <div class=\"score-bar-row\"><span>Creative</span><div class=\"bar-track\"><div class=\"bar-fill fill-creat\" style=\"width:{:.0}%\"></div></div><span>{:.1}</span></div>", take.scores.creative, take.scores.creative);
        let _ = writeln!(html, "          <div class=\"score-bar-row\"><span>Temporal</span><div class=\"bar-track\"><div class=\"bar-fill fill-temp\" style=\"width:{:.0}%\"></div></div><span>{:.1}</span></div>", take.scores.temporal, take.scores.temporal);
        let _ = writeln!(html, "        </div>");

        let _ = writeln!(html, "        <div class=\"master-banner\"><span class=\"master-icon\">&#9733;</span><span>{}</span></div>", dp_match);

        let _ = writeln!(html, "        <div class=\"tags-row\">");
        let _ = writeln!(
            html,
            "          <span class=\"tag\">{}</span>",
            take.style.lighting_key
        );
        let _ = writeln!(
            html,
            "          <span class=\"tag\">{}</span>",
            take.style.motion_type
        );
        let _ = writeln!(
            html,
            "          <span class=\"tag\">{}</span>",
            take.style.shot_scale
        );
        let _ = writeln!(html, "        </div>");

        let _ = writeln!(html, "      </div>");
        let _ = writeln!(html, "    </article>");
    }

    let _ = writeln!(html, "  </main>");
    let _ = writeln!(html, "</body>");
    let _ = writeln!(html, "</html>");

    html
}

/// Exports JSON shot sidecars for each take into `output_dir/metrics/<take_id>.json`.
pub fn export_shot_sidecars(
    output_dir: &std::path::Path,
    media_file: &str,
    takes: &[ShotTake],
) -> Result<usize, String> {
    let metrics_dir = output_dir.join("metrics");
    std::fs::create_dir_all(&metrics_dir)
        .map_err(|e| format!("Failed to create metrics directory: {}", e))?;

    let mut written = 0;
    for take in takes {
        let sidecar = serde_json::json!({
            "metrics_version": "1.0",
            "source_file": media_file,
            "take_id": take.take_id,
            "scene_index": take.scene_index,
            "start_sec": take.start_sec,
            "end_sec": take.end_sec,
            "duration_sec": take.duration_sec,
            "scores": {
                "overall": take.scores.overall,
                "technical": take.scores.technical,
                "creative": take.scores.creative,
                "temporal": take.scores.temporal,
            },
            "style": {
                "lighting_key": take.style.lighting_key,
                "motion_type": take.style.motion_type,
                "shot_scale": take.style.shot_scale,
                "cinematographer_match": take.style.cinematographer_match,
                "match_confidence": take.style.match_confidence,
            },
            "measured_physics": take.measured,
            "concerns": take.concerns,
        });

        let json_str = serde_json::to_string_pretty(&sidecar)
            .map_err(|e| format!("Serialization error for {}: {}", take.take_id, e))?;
        let sidecar_path = metrics_dir.join(format!("{}.json", take.take_id));
        std::fs::write(&sidecar_path, json_str)
            .map_err(|e| format!("Failed to write sidecar {}: {}", sidecar_path.display(), e))?;
        written += 1;
    }

    Ok(written)
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

        let csv = generate_csv_selects("FEATURE_MEZZANINE.MOV", std::slice::from_ref(&take), 24.0);
        assert!(csv.contains("Take Index,Source Clip"));
        assert!(csv.contains("1,\"FEATURE_MEZZANINE.MOV\",00:00:10:00,00:00:14:12,4.50,90.5"));
        assert!(csv.contains("\"Roger Deakins (Skyfall)\""));

        let xml = generate_fcpxml(
            "REEL_SELECTS",
            "FEATURE_MEZZANINE.MOV",
            std::slice::from_ref(&take),
            24.0,
        );
        assert!(xml.contains("<!DOCTYPE fcpxml>"));
        assert!(xml.contains("<fcpxml version=\"1.9\">"));
        assert!(xml.contains("Roger Deakins (Skyfall)"));

        let html = generate_contact_sheet_html(
            "REEL_SELECTS",
            "FEATURE_MEZZANINE.MOV",
            std::slice::from_ref(&take),
            5,
        );
        assert!(html.contains("Top 1 Selects Breakout"));
        assert!(html.contains("take_001"));
        assert!(html.contains("90.5 / 100"));

        let temp_dir = std::env::temp_dir().join("aesthetic_test_sidecars");
        let written = export_shot_sidecars(&temp_dir, "FEATURE_MEZZANINE.MOV", &[take]);
        assert_eq!(written.unwrap(), 1);
        assert!(temp_dir.join("metrics").join("take_001.json").exists());
        let _ = std::fs::remove_dir_all(&temp_dir);
    }
}
