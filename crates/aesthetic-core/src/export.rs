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
    generate_contact_sheet_html_with_frames(
        title,
        media_file,
        takes,
        top_n,
        &std::collections::HashMap::new(),
    )
}

/// Generates a standalone, dark-themed HTML visual contact sheet of top selects,
/// embedding lossless PNG stills directly when `hero_frames` are supplied.
pub fn generate_contact_sheet_html_with_frames(
    title: &str,
    media_file: &str,
    takes: &[ShotTake],
    top_n: usize,
    hero_frames: &std::collections::HashMap<String, image::RgbImage>,
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
    .card-thumb-container {{
      width: 100%;
      height: 220px;
      background: #08090b;
      position: relative;
      overflow: hidden;
      border-bottom: 1px solid var(--border);
    }}
    .card-thumb {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
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
    .metrics-details {{
      margin-top: 6px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #121419;
      font-size: 12px;
    }}
    .metrics-details summary {{
      padding: 8px 12px;
      cursor: pointer;
      font-weight: 600;
      color: var(--accent);
      user-select: none;
    }}
    .metrics-tree-content {{
      padding: 8px 12px 12px 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      border-top: 1px solid var(--border);
      color: var(--text-muted);
    }}
    .metric-branch {{
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}
    .branch-title {{
      font-weight: 700;
      color: var(--text);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .leaf-row {{
      display: flex;
      justify-content: space-between;
      padding-left: 8px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
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

    let dummy_info = aesthetic_models::manifest::VideoSourceInfo {
        file_path: media_file.to_string(),
        duration_sec: 0.0,
        frame_rate: 24.0,
        width: 1920,
        height: 1080,
        codec: "unknown".to_string(),
        color_primaries: None,
        transfer_characteristic: None,
    };
    let seq = crate::pipeline::compute_reel_sequence_metrics(selects, &dummy_info);
    let _ = writeln!(
        html,
        r#"  <section style="max-width:1400px;margin:0 auto 24px auto;background:#14161a;border:1px solid #282c35;border-radius:10px;padding:14px 20px;display:flex;flex-wrap:wrap;gap:22px;align-items:center;justify-content:space-between;font-size:13px;">
    <div><span style="color:#8a919e;text-transform:uppercase;font-size:11px;font-weight:700;letter-spacing:0.6px;">Sequence &amp; Reel Continuity</span><div style="color:#fff;font-weight:600;margin-top:2px;">{}</div></div>
    <div><span style="color:#8a919e;font-size:11px;">Grading Uniformity</span><div style="color:#4ade80;font-weight:700;font-family:monospace;">{:.1} / 100</div></div>
    <div><span style="color:#8a919e;font-size:11px;">Coverage Consistency</span><div style="color:#38bdf8;font-weight:700;font-family:monospace;">{:.1} / 100</div></div>
    <div><span style="color:#8a919e;font-size:11px;">Reel Diversity</span><div style="color:#e5a93c;font-weight:700;font-family:monospace;">{:.1} / 100</div></div>
    <div><span style="color:#8a919e;font-size:11px;">Visual Fatigue Index</span><div style="color:#e8eaed;font-weight:700;font-family:monospace;">{:.1} / 100</div></div>
    <div><span style="color:#8a919e;font-size:11px;">Cross-Scene Spread</span><div style="color:#8a919e;font-family:monospace;font-size:12px;">WB &sigma;={:.2} | CCT &sigma;={:.0}K | Luma &sigma;={:.1}</div></div>
  </section>"#,
        seq.transfer_curve_label,
        seq.grading_uniformity_score,
        seq.coverage_consistency_score,
        seq.reel_diversity_score,
        seq.visual_fatigue_index,
        seq.wb_cross_scene_std,
        seq.color_temp_cross_scene_std,
        seq.exposure_consistency_std
    );

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
        let _ = writeln!(html, "      <div class=\"card-thumb-container\">");
        let thumb_src = hero_frames
            .get(&take.take_id)
            .and_then(|img| encode_rgb_png_data_uri(img, 640))
            .unwrap_or_else(|| format!("/api/thumbnail?time={:.2}", take.hero_timestamp_sec));
        let _ = writeln!(
            html,
            "        <img class=\"card-thumb\" src=\"{}\" alt=\"{}\" loading=\"lazy\" onerror=\"this.style.display='none'\">",
            thumb_src, take.take_id
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
        if !take.rationale_summary.is_empty() {
            let _ = writeln!(
                html,
                "        <div style=\"background:#0c0d10;border-left:3px solid #e5a93c;padding:8px 10px;border-radius:4px;font-size:11.5px;line-height:1.45;color:#cbd2dc;\">{}</div>",
                take.rationale_summary
            );
        }

        let _ = writeln!(html, "        <div class=\"tags-row\" data-tags=\"{},{},{},{}\">",
            take.style.lighting_key, take.style.motion_type, take.style.shot_scale, take.style.style_family
        );
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
        let _ = writeln!(
            html,
            "          <span class=\"tag tag-family\">{}</span>",
            take.style.style_family
        );
        let _ = writeln!(html, "        </div>");

        // Collapsible complete metrics tree displaying EVERY SINGLE METRIC
        let exp = &take.measured.exposure;
        let opt = &take.measured.optics;
        let col = &take.measured.color;
        let fcz = &exp.false_color_zones;
        let elz = &exp.el_zones;

        let _ = writeln!(html, "        <details class=\"metrics-details\">");
        let _ = writeln!(html, "          <summary>&#9656; Full Scoring Metrics &amp; Physics Breakdown (All Measured Metrics)</summary>");
        let _ = writeln!(html, "          <div class=\"metrics-tree-content\">");
        
        // 1. Exposure & Tonal Latitude
        let _ = writeln!(html, "            <div class=\"metric-branch\">");
        let _ = writeln!(html, "              <span class=\"branch-title\">Pillar 1: Exposure &amp; Tonal Physics ({:.1} / 100)</span>", take.scores.technical);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Dynamic Range Stops</span><span>{:.2} stops</span></div>", exp.dynamic_range_stops);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Highlight Roll-Off Shoulder</span><span>{:.1}%</span></div>", exp.highlight_rolloff);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Specular Highlight Clip</span><span>{:.2}%</span></div>", exp.highlight_clip_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Crushed Shadow Floor Clip</span><span>{:.2}%</span></div>", exp.shadow_clip_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Histogram Mean Luma</span><span>{:.1}</span></div>", exp.histogram_mean);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Histogram Median Luma</span><span>{:.1}</span></div>", exp.histogram_median);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Histogram Std Dev</span><span>{:.2}</span></div>", exp.histogram_std);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Histogram Skewness</span><span>{:.3}</span></div>", exp.histogram_skew);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Luma Signal-to-Noise Ratio (SNR)</span><span>{:.1} dB</span></div>", exp.snr_luma);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Chroma Signal-to-Noise Ratio (SNR)</span><span>{:.1} dB</span></div>", exp.snr_chroma);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Peak Signal-to-Noise Ratio (PSNR)</span><span>{:.1} dB</span></div>", exp.psnr_db);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Structural Similarity Index (SSIM)</span><span>{:.3}</span></div>", exp.ssim_score);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>False Color Zone: Crushed Black</span><span>{:.1}%</span></div>", fcz.black_clip_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>False Color Zone: Shadow Detail</span><span>{:.1}%</span></div>", fcz.shadow_zone_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>False Color Zone: 18% Middle Gray</span><span>{:.1}%</span></div>", fcz.middle_gray_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>False Color Zone: Skin Tone Key</span><span>{:.1}%</span></div>", fcz.skin_zone_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>False Color Zone: Highlight Texture</span><span>{:.1}%</span></div>", fcz.highlight_zone_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>False Color Zone: Specular Ceiling</span><span>{:.1}%</span></div>", fcz.specular_clip_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>EL Zone V (18% Middle Gray 0 EV)</span><span>{:.1}%</span></div>", elz.zone_5_gray_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>EL Zone VI (+1 EV Skin Key)</span><span>{:.1}%</span></div>", elz.zone_6_khaki_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>EL Zone VII (+2 EV Skin Highlight)</span><span>{:.1}%</span></div>", elz.zone_7_yellow_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>EL Zone VIII (+3 EV Texture)</span><span>{:.1}%</span></div>", elz.zone_8_orange_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>EL Zone IX (+4 EV Near Clip)</span><span>{:.1}%</span></div>", elz.zone_9_red_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>EL Zone X (+5+ EV Specular Clip)</span><span>{:.1}%</span></div>", elz.zone_10_magenta_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>EL Zone IV (-1 EV Shadow Fill)</span><span>{:.1}%</span></div>", elz.zone_4_olive_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>EL Zone III (-2 EV Cyan Shadow)</span><span>{:.1}%</span></div>", elz.zone_3_cyan_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>EL Zone II (-3 EV Deep Blue)</span><span>{:.1}%</span></div>", elz.zone_2_blue_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>EL Zone I (-4 EV Purple Toe)</span><span>{:.1}%</span></div>", elz.zone_1_purple_pct);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>EL Zone 0 (-5+ EV Sensor Floor)</span><span>{:.1}%</span></div>", elz.zone_0_black_pct);
        let _ = writeln!(html, "            </div>");

        // 2. Optics, Sharpness & Spatial Frequency
        let _ = writeln!(html, "            <div class=\"metric-branch\">");
        let _ = writeln!(html, "              <span class=\"branch-title\">Pillar 2: Optics &amp; Spatial Frequency</span>");
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>MTF50 Acutance (Laplacian Variance)</span><span>{:.1} lp/mm</span></div>", opt.sharpness_laplacian);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Edge Micro-Contrast Density</span><span>{:.3}</span></div>", opt.edge_density);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>MTF Modulation Transfer Proxy</span><span>{:.2}</span></div>", opt.mtf_proxy);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Optical Vignetting Falloff</span><span>{:.2} stops</span></div>", opt.vignetting_stops);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Chromatic Aberration Fringe Width</span><span>{:.2} px</span></div>", opt.chromatic_aberration_px);
        let _ = writeln!(html, "            </div>");

        // 3. Color Science & Gamut
        let _ = writeln!(html, "            <div class=\"metric-branch\">");
        let _ = writeln!(html, "              <span class=\"branch-title\">Pillar 3: Colorimetry &amp; Gamut Physics</span>");
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Correlated Color Temperature (CCT)</span><span>{:.0} K</span></div>", col.estimated_kelvin);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>White Balance Tint Deviation</span><span>{:.2}</span></div>", col.wb_deviation);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Mean Chromatic Saturation</span><span>{:.1}%</span></div>", col.saturation_mean);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Palette Chromatic Entropy</span><span>{:.2}</span></div>", col.palette_entropy);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Delta-E D65 Neutral Drift</span><span>{:.2} &Delta;E</span></div>", col.delta_e_d65);
        if let Some(sk) = col.skin_tone_delta_e {
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Skin Tone I-Line Deviation</span><span>{:.2} &Delta;E</span></div>", sk);
        }
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Gamut Coverage (sRGB)</span><span>{:.1}%</span></div>", col.gamut_coverage_srgb);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Gamut Coverage (DCI-P3)</span><span>{:.1}%</span></div>", col.gamut_coverage_p3);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Gamut Coverage (Rec.2020 Wide Gamut)</span><span>{:.1}%</span></div>", col.gamut_coverage_rec2020);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Split-Toning Separation Angle</span><span>{:.1}&deg;</span></div>", col.split_toning_separation_deg);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Harmonic Palette Balance Score</span><span>{:.1} / 100</span></div>", col.harmonic_palette_score);
        let _ = writeln!(html, "            </div>");

        // 4. Craft, Staging & Lighting
        let _ = writeln!(html, "            <div class=\"metric-branch\">");
        let _ = writeln!(html, "              <span class=\"branch-title\">Pillar 4: Model-Inferred Craft &amp; Staging ({:.1} / 100)</span>", take.scores.creative);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Lighting Key Classification</span><span>{}</span></div>", take.style.lighting_key);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Framing Shot Scale</span><span>{}</span></div>", take.style.shot_scale);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Chromatic Palette Family</span><span>{}</span></div>", take.style.palette_family);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Scene Environment Type</span><span>{}</span></div>", take.style.scene_type);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Narrative Shot Intent</span><span>{}</span></div>", take.style.shot_intent);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Style Family Cluster</span><span>{}</span></div>", take.style.style_family);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Cinema Corpus Match Affinity</span><span>{:.1}%</span></div>", take.style.match_confidence);
        if let Some(ref c) = take.craft {
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Key-to-Fill Ratio</span><span>{:.2}:1</span></div>", c.lighting.key_to_fill_ratio);
            if let Some(az) = c.lighting.key_azimuth_deg {
                let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Key Light Azimuth</span><span>{:.1}&deg;</span></div>", az);
            }
            if let Some(el) = c.lighting.key_elevation_deg {
                let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Key Light Elevation</span><span>{:.1}&deg;</span></div>", el);
            }
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Rim Light Separation</span><span>{:.1} / 100</span></div>", c.lighting.rim_light_separation);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Shadow Boundary Softness</span><span>{:.1} / 100</span></div>", c.lighting.shadow_softness);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Eye Catchlight Specular</span><span>{:.1}%</span></div>", c.lighting.catchlight_intensity);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Subject Focus Accuracy</span><span>{:.1} / 100</span></div>", c.focus.subject_focus_accuracy);
            if let Some(es) = c.focus.eye_sharpness {
                let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Subject Eye Sharpness</span><span>{:.1} / 100</span></div>", es);
            }
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Focus Stability Score</span><span>{:.1} / 100</span></div>", c.focus.focus_hunting_score);
            if let (Some(gx), Some(gy)) = (c.staging.gaze_vector_x, c.staging.gaze_vector_y) {
                let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Gaze Anchor Coordinates</span><span>({:.2}, {:.2})</span></div>", gx, gy);
            }
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Looking Room Lead Space</span><span>{:.1} / 100</span></div>", c.staging.looking_room_score);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Gaze Poise Score</span><span>{:.1} / 100</span></div>", c.staging.gaze_poise_score);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>3D Depth Plane Separation</span><span>{:.1} / 100 ({} planes)</span></div>", c.staging.depth_separation_score, c.staging.depth_plane_count);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Subject Silhouette Clarity</span><span>{:.1} / 100</span></div>", c.staging.silhouette_clarity);
        }
        let _ = writeln!(html, "            </div>");

        // 5. Temporal & Editorial Dynamics
        let _ = writeln!(html, "            <div class=\"metric-branch\">");
        let _ = writeln!(html, "              <span class=\"branch-title\">Pillar 5: Temporal Dynamics &amp; Editorial ({:.1} / 100)</span>", take.scores.temporal);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Usable Hero Window Duration</span><span>{:.2}s</span></div>", duration);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Camera Motion Intentionality</span><span>{}</span></div>", take.style.motion_type);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Start SMPTE Timecode</span><span>{}</span></div>", in_tc);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>End SMPTE Timecode</span><span>{}</span></div>", out_tc);
        if let Some(ref c) = take.craft {
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Optical Flow Mean Velocity</span><span>{:.2} px/s</span></div>", c.motion.optical_flow_mean);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Optical Flow Std Dev</span><span>{:.2} px/s</span></div>", c.motion.optical_flow_std);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Camera Motion Alignment Ratio</span><span>{:.0}%</span></div>", c.motion.camera_motion_ratio * 100.0);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Micro-Jitter Shake Score</span><span>{:.1} / 100</span></div>", c.motion.micro_jitter_score);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Depth Parallax Strength</span><span>{:.1} / 100</span></div>", c.motion.parallax_strength);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Strobe / Judder Risk</span><span>{:.1} / 100</span></div>", c.motion.judder_risk_score);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Motion Blur Trajectory Angle</span><span>{:.1}&deg;</span></div>", c.motion.motion_blur_angle_deg);
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Motion Trajectory Coherence</span><span>{:.1} / 100</span></div>", c.motion.motion_coherence_score);
        }
        let _ = writeln!(html, "            </div>");

        // 6. Narrative & Aesthetic Reranker Heads (M18 & M19)
        let _ = writeln!(html, "            <div class=\"metric-branch\">");
        let _ = writeln!(html, "              <span class=\"branch-title\">Narrative &amp; Aesthetic Reranker Heads</span>");
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Hero-Frame Potency (Thumbnail Suitability)</span><span>{:.1} / 100</span></div>", take.scores.hero_potency_score);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Three-Second Impact (Opening Authority)</span><span>{:.1} / 100</span></div>", take.scores.three_second_impact_score);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Authorship &amp; Distinctiveness</span><span>{:.1} / 100</span></div>", take.scores.authorship_distinctiveness_score);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Visual Storytelling Effectiveness</span><span>{:.1} / 100</span></div>", take.scores.storytelling_score);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Cinematic Technique Quality</span><span>{:.1} / 100</span></div>", take.scores.cinematic_technique_score);
        let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Visual Memorability</span><span>{:.1} / 100</span></div>", take.scores.memorability_score);
        let _ = writeln!(html, "            </div>");

        // 7. Golden Baseline Comparison
        if !take.golden_baseline.is_empty() {
            let _ = writeln!(html, "            <div class=\"metric-branch\">");
            let _ = writeln!(html, "              <span class=\"branch-title\">Golden Baseline Comparison (Award-Winning Cinema Distribution)</span>");
            for row in &take.golden_baseline {
                let _ = writeln!(
                    html,
                    "              <div class=\"leaf-row\"><span>{} (Shot: {:.2} {} | Award p50: {:.2} {})</span><span>{}</span></div>",
                    row.metric, row.shot_value, row.unit, row.corpus_p50, row.unit, row.descriptor
                );
            }
            let _ = writeln!(html, "            </div>");
        }

        // 8. Forensic Technical Diagnostics
        let _ = writeln!(html, "            <div class=\"metric-branch\">");
        let _ = writeln!(html, "              <span class=\"branch-title\">Forensics: Non-Punitive Advisory Flags</span>");
        if take.concerns.is_empty() {
            let _ = writeln!(html, "              <div class=\"leaf-row\"><span>Technical Flags</span><span>None (Clean Sensor &amp; Signal)</span></div>");
        } else {
            for c in &take.concerns {
                let _ = writeln!(html, "              <div class=\"leaf-row\"><span>[{}] {}</span><span>{:?}</span></div>", c.code, c.description, c.severity);
            }
        }
        let _ = writeln!(html, "            </div>");

        let _ = writeln!(html, "          </div>");
        let _ = writeln!(html, "        </details>");

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
    export_shot_sidecars_with_frames(
        output_dir,
        media_file,
        takes,
        &std::collections::HashMap::new(),
    )
}

/// Exports JSON shot sidecars into `output_dir/metrics/<take_id>.json` and attaches
/// a high-quality lossless PNG (`output_dir/metrics/<take_id>.png`) for each take.
pub fn export_shot_sidecars_with_frames(
    output_dir: &std::path::Path,
    media_file: &str,
    takes: &[ShotTake],
    hero_frames: &std::collections::HashMap<String, image::RgbImage>,
) -> Result<usize, String> {
    let metrics_dir = output_dir.join("metrics");
    std::fs::create_dir_all(&metrics_dir)
        .map_err(|e| format!("Failed to create metrics directory: {}", e))?;

    let mut written = 0;
    for take in takes {
        let mut png_filename: Option<String> = None;
        if let Some(frame) = hero_frames.get(&take.take_id) {
            let fname = format!("{}.png", take.take_id);
            let png_path = metrics_dir.join(&fname);
            if frame.save(&png_path).is_ok() {
                png_filename = Some(fname);
            }
        }

        let sidecar = serde_json::json!({
            "metrics_version": "1.1",
            "source_file": media_file,
            "take_id": take.take_id,
            "hero_frame_png": png_filename,
            "scene_index": take.scene_index,
            "start_sec": take.start_sec,
            "end_sec": take.end_sec,
            "duration_sec": take.duration_sec,
            "scores": {
                "overall": take.scores.overall,
                "technical": take.scores.technical,
                "creative": take.scores.creative,
                "temporal": take.scores.temporal,
                "hero_potency_score": take.scores.hero_potency_score,
                "three_second_impact_score": take.scores.three_second_impact_score,
                "authorship_distinctiveness_score": take.scores.authorship_distinctiveness_score,
                "storytelling_score": take.scores.storytelling_score,
                "cinematic_technique_score": take.scores.cinematic_technique_score,
                "memorability_score": take.scores.memorability_score,
            },
            "style": {
                "lighting_key": take.style.lighting_key,
                "motion_type": take.style.motion_type,
                "shot_scale": take.style.shot_scale,
                "style_family": take.style.style_family,
                "palette_family": take.style.palette_family,
                "scene_type": take.style.scene_type,
                "shot_intent": take.style.shot_intent,
                "cinematographer_match": take.style.cinematographer_match,
                "match_confidence": take.style.match_confidence,
            },
            "claimed_tags": [
                &take.style.lighting_key,
                &take.style.motion_type,
                &take.style.shot_scale,
                &take.style.style_family,
            ],
            "measured_physics": take.measured,
            "inferred_craft": take.craft,
            "golden_baseline": take.golden_baseline,
            "concerns": take.concerns,
            "rationale_summary": take.rationale_summary,
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

/// Re-scores and re-ranks cached JSON+PNG shot sidecars in `<sidecars_dir>/metrics`
/// against the current Golden Baseline corpus without re-decoding video (M17).
pub fn rescore_from_sidecars(
    sidecars_dir: &std::path::Path,
) -> Result<(Vec<ShotTake>, std::collections::HashMap<String, image::RgbImage>), String> {
    let metrics_dir = if sidecars_dir.join("metrics").is_dir() {
        sidecars_dir.join("metrics")
    } else {
        sidecars_dir.to_path_buf()
    };

    let entries = std::fs::read_dir(&metrics_dir).map_err(|e| {
        format!(
            "Failed to read sidecars directory {}: {}",
            metrics_dir.display(),
            e
        )
    })?;

    let store = crate::baseline_store::BaselineStore::new();
    let inference = crate::inference::ModelInferenceEngine::new();
    let (dr_q, rolloff_q, sharp_q, _) = store.scoring_quantiles();

    let mut takes: Vec<ShotTake> = Vec::new();
    let mut hero_frames: std::collections::HashMap<String, image::RgbImage> =
        std::collections::HashMap::new();

    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("json") {
            continue;
        }
        let raw = std::fs::read_to_string(&path)
            .map_err(|e| format!("Failed to read {}: {}", path.display(), e))?;
        let val: serde_json::Value = serde_json::from_str(&raw)
            .map_err(|e| format!("Invalid JSON in {}: {}", path.display(), e))?;

        let take_id = val["take_id"]
            .as_str()
            .unwrap_or("take_000")
            .to_string();
        let scene_index = val["scene_index"].as_u64().unwrap_or(1) as usize;
        let start_sec = val["start_sec"].as_f64().unwrap_or(0.0);
        let end_sec = val["end_sec"].as_f64().unwrap_or(start_sec + 2.5);
        let duration_sec = val["duration_sec"].as_f64().unwrap_or(end_sec - start_sec);

        let mut measured: aesthetic_models::physics::ObjectivePhysics =
            serde_json::from_value(val["measured_physics"].clone()).unwrap_or_default();
        if measured.exposure.psnr_db <= 0.0 {
            measured.exposure.psnr_db = (measured.exposure.snr_luma + 8.5).clamp(24.0, 52.0);
        }
        if measured.exposure.ssim_score <= 0.0 {
            measured.exposure.ssim_score =
                (0.82_f32 + (measured.exposure.snr_luma - 20.0) * 0.006).clamp(0.75, 0.995);
        }
        let craft: Option<aesthetic_models::inferred::ModelInferredCraft> =
            serde_json::from_value(val["inferred_craft"].clone()).ok();
        let concerns: Vec<aesthetic_models::forensics::DiagnosticFlag> =
            serde_json::from_value(val["concerns"].clone()).unwrap_or_default();

        let mut style = aesthetic_models::window::DiscoveredStyle {
            lighting_key: val["style"]["lighting_key"]
                .as_str()
                .unwrap_or("Mid-Key Naturalistic")
                .to_string(),
            motion_type: val["style"]["motion_type"]
                .as_str()
                .unwrap_or_default()
                .to_string(),
            shot_scale: val["style"]["shot_scale"]
                .as_str()
                .unwrap_or("Medium")
                .to_string(),
            cinematographer_match: val["style"]["cinematographer_match"]
                .as_str()
                .map(|s| s.to_string()),
            match_confidence: val["style"]["match_confidence"].as_f64().unwrap_or(0.0) as f32,
            style_family: val["style"]["style_family"]
                .as_str()
                .unwrap_or("Prestige Naturalism")
                .to_string(),
            palette_family: val["style"]["palette_family"]
                .as_str()
                .unwrap_or("Natural Daylight")
                .to_string(),
            scene_type: val["style"]["scene_type"]
                .as_str()
                .unwrap_or("Controlled Studio / Stage")
                .to_string(),
            shot_intent: val["style"]["shot_intent"]
                .as_str()
                .unwrap_or("Dialogue / Staging")
                .to_string(),
        };

        // Load companion PNG still if present
        let png_path = metrics_dir.join(format!("{}.png", take_id));
        if png_path.exists() {
            if let Ok(dyn_img) = image::open(&png_path) {
                let rgb = dyn_img.to_rgb8();
                let emb = inference.infer_embedding(&rgb);
                let kf = craft
                    .as_ref()
                    .map(|c| c.lighting.key_to_fill_ratio)
                    .unwrap_or(2.5);
                if let Some((shot, sim)) = store.nearest_measured_reference_with_craft(
                    &emb,
                    measured.exposure.dynamic_range_stops,
                    measured.optics.sharpness_laplacian,
                    kf,
                ) {
                    style.cinematographer_match =
                        Some(format!("{} ({})", shot.cinematographer, shot.film_title));
                    style.match_confidence = (sim * 100.0).clamp(0.0, 100.0);
                    style.style_family = shot.style_label.clone();
                }
                hero_frames.insert(take_id.clone(), rgb);
            }
        }

        let is_non_photographic = concerns
            .iter()
            .any(|c| c.code == "NON_PHOTOGRAPHIC_OR_CREDITS");

        let dr_score = dr_q.compute_percentile_score(measured.exposure.dynamic_range_stops);
        let rolloff_score = rolloff_q.compute_percentile_score(measured.exposure.highlight_rolloff);
        let sharp_score = sharp_q.compute_percentile_score(measured.optics.sharpness_laplacian);
        let mut technical =
            (dr_score * 0.35 + rolloff_score * 0.35 + sharp_score * 0.30).clamp(0.0, 100.0);
        if is_non_photographic {
            technical = (technical * 0.20).min(18.0);
        }

        let creative = val["scores"]["creative"].as_f64().unwrap_or(50.0) as f32;
        let temporal = val["scores"]["temporal"].as_f64().unwrap_or(0.0) as f32;
        let temporal_measured = temporal > 0.0;

        let raw_overall = if temporal_measured {
            technical * 0.45 + creative * 0.35 + temporal * 0.20
        } else {
            (technical * 0.45 + creative * 0.35) / 0.80
        }
        .clamp(0.0, 100.0);
        let overall = if is_non_photographic {
            (raw_overall * 0.25).min(18.0)
        } else {
            raw_overall
        };

        let kf_opt = craft.as_ref().map(|c| c.lighting.key_to_fill_ratio);
        let flow_opt = if temporal_measured {
            craft.as_ref().map(|c| c.motion.optical_flow_mean)
        } else {
            None
        };
        let golden_baseline = store.compare_to_golden_baseline_with_style(
            &measured,
            kf_opt,
            Some(style.style_family.as_str()),
            flow_opt,
        );

        let hero_potency_score = val["scores"]["hero_potency_score"]
            .as_f64()
            .map(|v| v as f32)
            .unwrap_or(overall);
        let three_second_impact_score = val["scores"]["three_second_impact_score"]
            .as_f64()
            .map(|v| v as f32)
            .unwrap_or(creative);
        let authorship_distinctiveness_score = val["scores"]["authorship_distinctiveness_score"]
            .as_f64()
            .map(|v| v as f32)
            .unwrap_or(style.match_confidence);

        let storytelling_score = val["scores"]["storytelling_score"]
            .as_f64()
            .map(|v| v as f32)
            .unwrap_or(creative);
        let cinematic_technique_score = val["scores"]["cinematic_technique_score"]
            .as_f64()
            .map(|v| v as f32)
            .unwrap_or(technical);
        let memorability_score = val["scores"]["memorability_score"]
            .as_f64()
            .map(|v| v as f32)
            .unwrap_or(overall);

        let mut take_obj = ShotTake {
            take_id,
            scene_index,
            start_sec,
            end_sec,
            duration_sec,
            hero_frame_index: Some(0),
            hero_timestamp_sec: start_sec,
            scores: aesthetic_models::window::PillarScores {
                overall,
                technical,
                creative,
                temporal,
                temporal_measured,
                hero_potency_score,
                three_second_impact_score,
                authorship_distinctiveness_score,
                storytelling_score,
                cinematic_technique_score,
                memorability_score,
            },
            style,
            measured,
            concerns,
            craft,
            golden_baseline,
            rationale_summary: String::new(),
        };
        take_obj.rationale_summary = crate::pipeline::generate_cinematographic_rationale(&take_obj);
        takes.push(take_obj);
    }

    crate::pipeline::apply_reel_diversity_ranking(&mut takes);

    // Persist updated sidecar JSONs in-place so cached sidecars reflect latest schema & rationale
    for take in &takes {
        let png_fname = format!("{}.png", take.take_id);
        let has_png = metrics_dir.join(&png_fname).exists();
        let sidecar = serde_json::json!({
            "metrics_version": "1.4.0",
            "source_file": sidecars_dir.display().to_string(),
            "take_id": take.take_id,
            "hero_frame_png": if has_png { Some(png_fname) } else { None },
            "scene_index": take.scene_index,
            "start_sec": take.start_sec,
            "end_sec": take.end_sec,
            "duration_sec": take.duration_sec,
            "scores": {
                "overall": take.scores.overall,
                "technical": take.scores.technical,
                "creative": take.scores.creative,
                "temporal": take.scores.temporal,
                "hero_potency_score": take.scores.hero_potency_score,
                "three_second_impact_score": take.scores.three_second_impact_score,
                "authorship_distinctiveness_score": take.scores.authorship_distinctiveness_score,
                "storytelling_score": take.scores.storytelling_score,
                "cinematic_technique_score": take.scores.cinematic_technique_score,
                "memorability_score": take.scores.memorability_score,
            },
            "style": {
                "lighting_key": take.style.lighting_key,
                "motion_type": take.style.motion_type,
                "shot_scale": take.style.shot_scale,
                "style_family": take.style.style_family,
                "palette_family": take.style.palette_family,
                "scene_type": take.style.scene_type,
                "shot_intent": take.style.shot_intent,
                "cinematographer_match": take.style.cinematographer_match,
                "match_confidence": take.style.match_confidence,
            },
            "claimed_tags": [
                &take.style.lighting_key,
                &take.style.motion_type,
                &take.style.shot_scale,
                &take.style.style_family,
            ],
            "measured_physics": take.measured,
            "inferred_craft": take.craft,
            "golden_baseline": take.golden_baseline,
            "concerns": take.concerns,
            "rationale_summary": take.rationale_summary,
        });
        if let Ok(json_str) = serde_json::to_string_pretty(&sidecar) {
            let _ = std::fs::write(metrics_dir.join(format!("{}.json", take.take_id)), json_str);
        }
    }

    Ok((takes, hero_frames))
}

/// Generates a DaVinci Resolve Python automation script (`DaVinciResolveScript`) that creates an
/// AESTHETIC Selects bin & timeline, appends the Top-N usable windows, and attaches color-coded
/// timeline markers containing each shot's scores, rationale, and forensic flags (M22).
pub fn generate_resolve_timeline_script(
    timeline_name: &str,
    media_file: &str,
    takes: &[ShotTake],
    fps: f64,
) -> String {
    let mut py = String::new();
    let fps_val = if fps <= 0.0 { 24.0 } else { fps };
    let escaped_media = media_file.replace('\\', "\\\\").replace('"', "\\\"");
    let escaped_tl = timeline_name.replace('"', "\\\"");

    let _ = writeln!(py, "#!/usr/bin/env python3");
    let _ = writeln!(
        py,
        "# AESTHETIC — DaVinci Resolve Timeline & Marker Bridge (M22)"
    );
    let _ = writeln!(py, "# Source Media: {}", media_file);
    let _ = writeln!(py, "import sys");
    let _ = writeln!(py, "try:");
    let _ = writeln!(py, "    import DaVinciResolveScript as dvr_script");
    let _ = writeln!(py, "except ImportError:");
    let _ = writeln!(
        py,
        "    print('Error: DaVinciResolveScript module not found in PYTHONPATH.')"
    );
    let _ = writeln!(py, "    sys.exit(1)\n");
    let _ = writeln!(py, "resolve = dvr_script.scriptapp('Resolve')");
    let _ = writeln!(py, "if not resolve:");
    let _ = writeln!(
        py,
        "    print('Error: Could not connect to running DaVinci Resolve instance.')"
    );
    let _ = writeln!(py, "    sys.exit(1)\n");
    let _ = writeln!(py, "pm = resolve.GetProjectManager()");
    let _ = writeln!(
        py,
        "project = pm.GetCurrentProject() or pm.CreateProject('AESTHETIC_Selects')"
    );
    let _ = writeln!(py, "media_pool = project.GetMediaPool()");
    let _ = writeln!(py, "root_folder = media_pool.GetRootFolder()");
    let _ = writeln!(
        py,
        "selects_bin = media_pool.AddSubFolder(root_folder, 'AESTHETIC_Hero_Selects')"
    );
    let _ = writeln!(py, "media_pool.SetCurrentFolder(selects_bin)");
    let _ = writeln!(
        py,
        "imported = media_pool.ImportMedia([\"{}\"])",
        escaped_media
    );
    let _ = writeln!(
        py,
        "timeline = media_pool.CreateEmptyTimeline(\"{}\")",
        escaped_tl
    );
    let _ = writeln!(py, "if imported and timeline:");
    let _ = writeln!(py, "    clip = imported[0]");
    let _ = writeln!(py, "    sub_clips = []");
    let _ = writeln!(py, "    rec_frame_cursor = 0");

    for (idx, take) in takes.iter().enumerate() {
        let start_frame = (take.start_sec * fps_val).round().max(0.0) as u64;
        let end_frame = (take.end_sec * fps_val).round().max((start_frame + 1) as f64) as u64;
        let dur_frames = end_frame.saturating_sub(start_frame).max(1);
        let marker_color = if !take.concerns.is_empty() {
            "Red"
        } else if idx == 0 {
            "Yellow"
        } else if take.scores.overall >= 70.0 {
            "Blue"
        } else {
            "Cyan"
        };
        let marker_name = format!(
            "#{} {} ({:.1}/100 | {})",
            idx + 1,
            take.take_id,
            take.scores.overall,
            take.style.shot_scale
        )
        .replace('"', "'");
        let note = format!(
            "{} | Tech {:.1} / Creat {:.1} / Temp {:.1} | Potency {:.1} | Impact {:.1}",
            take.rationale_summary,
            take.scores.technical,
            take.scores.creative,
            take.scores.temporal,
            take.scores.hero_potency_score,
            take.scores.three_second_impact_score
        )
        .replace('"', "'")
        .replace('\n', " ");

        let _ = writeln!(
            py,
            "    media_pool.AppendToTimeline([{{'mediaPoolItem': clip, 'startFrame': {}, 'endFrame': {}}})",
            start_frame, end_frame
        );
        let _ = writeln!(
            py,
            "    timeline.AddMarker(rec_frame_cursor, '{}', \"{}\", \"{}\", {})",
            marker_color, marker_name, note, dur_frames
        );
        let _ = writeln!(py, "    rec_frame_cursor += {}", dur_frames);
    }

    let _ = writeln!(
        py,
        "    print('Successfully assembled {} hero selects into timeline: {}')",
        takes.len(),
        escaped_tl
    );
    py
}

/// Encodes an `RgbImage` (optionally downscaled to `max_width`) into a `data:image/png;base64,...` URI.
fn encode_rgb_png_data_uri(img: &image::RgbImage, max_width: u32) -> Option<String> {
    use image::ImageEncoder;
    let (w, h) = img.dimensions();
    if w == 0 || h == 0 {
        return None;
    }
    let scaled = if w > max_width && max_width > 0 {
        let nh = ((h as f32) * (max_width as f32) / (w as f32)).round().max(1.0) as u32;
        image::imageops::resize(img, max_width, nh, image::imageops::FilterType::Lanczos3)
    } else {
        img.clone()
    };
    let mut png_bytes = Vec::new();
    let encoder = image::codecs::png::PngEncoder::new(&mut png_bytes);
    encoder
        .write_image(
            scaled.as_raw(),
            scaled.width(),
            scaled.height(),
            image::ExtendedColorType::Rgb8,
        )
        .ok()?;
    Some(format!("data:image/png;base64,{}", encode_base64(&png_bytes)))
}

/// Pure-Rust RFC 4648 Base64 encoder (zero external dependencies).
fn encode_base64(input: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(input.len().div_ceil(3) * 4);
    for chunk in input.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = if chunk.len() > 1 { chunk[1] as u32 } else { 0 };
        let b2 = if chunk.len() > 2 { chunk[2] as u32 } else { 0 };
        let triple = (b0 << 16) | (b1 << 8) | b2;
        out.push(TABLE[((triple >> 18) & 0x3F) as usize] as char);
        out.push(TABLE[((triple >> 12) & 0x3F) as usize] as char);
        if chunk.len() > 1 {
            out.push(TABLE[((triple >> 6) & 0x3F) as usize] as char);
        } else {
            out.push('=');
        }
        if chunk.len() > 2 {
            out.push(TABLE[(triple & 0x3F) as usize] as char);
        } else {
            out.push('=');
        }
    }
    out
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
                temporal_measured: true,
                ..Default::default()
            },
            style: DiscoveredStyle {
                lighting_key: "Low-Key".to_string(),
                motion_type: "Smooth Track / Dolly".to_string(),
                shot_scale: "Medium Close-Up".to_string(),
                cinematographer_match: Some("Roger Deakins (Skyfall)".to_string()),
                match_confidence: 94.2,
                style_family: "Prestige Naturalism".to_string(),
                ..Default::default()
            },
            measured: Default::default(),
            concerns: vec![],
            craft: None,
            golden_baseline: vec![],
            rationale_summary: "Medium Close-Up (Intimate Character)".to_string(),
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

        let resolve_py = generate_resolve_timeline_script(
            "REEL_SELECTS",
            "FEATURE_MEZZANINE.MOV",
            std::slice::from_ref(&take),
            24.0,
        );
        assert!(resolve_py.contains("DaVinciResolveScript"));
        assert!(resolve_py.contains("timeline.AddMarker"));

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
        let mut frames = std::collections::HashMap::new();
        frames.insert(
            "take_001".to_string(),
            image::RgbImage::from_pixel(32, 18, image::Rgb([120, 140, 160])),
        );
        let written = export_shot_sidecars_with_frames(
            &temp_dir,
            "FEATURE_MEZZANINE.MOV",
            std::slice::from_ref(&take),
            &frames,
        );
        assert_eq!(written.unwrap(), 1);
        assert!(temp_dir.join("metrics").join("take_001.json").exists());
        assert!(temp_dir.join("metrics").join("take_001.png").exists());
        let html_with_png = generate_contact_sheet_html_with_frames(
            "REEL_SELECTS",
            "FEATURE_MEZZANINE.MOV",
            std::slice::from_ref(&take),
            5,
            &frames,
        );
        assert!(html_with_png.contains("data:image/png;base64,"));
        let _ = std::fs::remove_dir_all(&temp_dir);
    }
}
