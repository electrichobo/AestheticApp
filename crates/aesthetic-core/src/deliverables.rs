//! Unified Deliverables Export Packaging
//!
//! Generates a complete, self-contained post-production deliverables package
//! in standard PKZIP (.zip) format and folder structure containing:
//! - CMX 3600 Edit Decision List (.edl)
//! - Final Cut Pro XML (.xml)
//! - DaVinci Resolve Studio automation script (.py)
//! - Tabular CSV candidate selects report (.csv)
//! - Standalone interactive HTML visual contact sheet (.html)
//! - Calibrated ASC CDL (.cdl) and 3D LUT (.cube) grades
//! - Hero stills in pristine PNG format
//! - Handoff README instruction manifest

use crate::export::{
    generate_cmx3600_edl, generate_contact_sheet_html, generate_csv_selects, generate_fcpxml,
    generate_resolve_timeline_script,
};
use crate::multicam::{
    compute_master_baseline_cdl_grade, generate_3d_lut_cube, generate_asc_cdl_xml,
};
use aesthetic_models::ShotTake;
use image::RgbImage;
use std::io::Cursor;
use std::path::{Path, PathBuf};

/// Compute standard IEEE 802.3 32-bit Cyclic Redundancy Check (CRC-32).
pub fn compute_crc32(data: &[u8]) -> u32 {
    let mut crc = 0xFFFFFFFFu32;
    for &byte in data {
        crc ^= byte as u32;
        for _ in 0..8 {
            let mask = (crc & 1).wrapping_neg();
            crc = (crc >> 1) ^ (0xEDB88320 & mask);
        }
    }
    !crc
}

/// Creates a standard, universally compliant PKZIP 2.0 archive in-memory.
///
/// Uses standard STORE method (compression 0), allowing zero-dependency,
/// zero-overhead lightning creation readable by Windows Explorer, macOS Finder,
/// Linux unzip, Python zipfile, DaVinci Resolve, and Premiere Pro.
pub fn create_pkzip_archive(files: &[(&str, &[u8])]) -> Result<Vec<u8>, String> {
    if files.is_empty() {
        return Err("Cannot create empty zip archive".to_string());
    }

    let mut archive = Vec::new();
    let mut cd_buf = Vec::new();

    for (raw_path, data) in files {
        // Enforce normalized forward slashes in ZIP path entries
        let name = raw_path.replace('\\', "/");
        let name_bytes = name.as_bytes();
        let offset = archive.len() as u32;
        let crc = compute_crc32(data);
        let size = data.len() as u32;

        // --- 1. Local File Header (30 bytes + name) ---
        archive.extend_from_slice(&0x04034b50u32.to_le_bytes()); // Signature
        archive.extend_from_slice(&20u16.to_le_bytes()); // Version needed (2.0)
        archive.extend_from_slice(&0x0800u16.to_le_bytes()); // General purpose flag: UTF-8
        archive.extend_from_slice(&0u16.to_le_bytes()); // Compression: 0 (Store)
        archive.extend_from_slice(&0x0000u16.to_le_bytes()); // Mod time (00:00:00)
        archive.extend_from_slice(&0x5821u16.to_le_bytes()); // Mod date (2024-01-01)
        archive.extend_from_slice(&crc.to_le_bytes()); // CRC-32
        archive.extend_from_slice(&size.to_le_bytes()); // Compressed size
        archive.extend_from_slice(&size.to_le_bytes()); // Uncompressed size
        archive.extend_from_slice(&(name_bytes.len() as u16).to_le_bytes()); // Name len
        archive.extend_from_slice(&0u16.to_le_bytes()); // Extra field len
        archive.extend_from_slice(name_bytes);
        archive.extend_from_slice(data);

        // --- 2. Central Directory Header (46 bytes + name) ---
        cd_buf.extend_from_slice(&0x02014b50u32.to_le_bytes()); // Signature
        cd_buf.extend_from_slice(&20u16.to_le_bytes()); // Version made by
        cd_buf.extend_from_slice(&20u16.to_le_bytes()); // Version needed
        cd_buf.extend_from_slice(&0x0800u16.to_le_bytes()); // UTF-8
        cd_buf.extend_from_slice(&0u16.to_le_bytes()); // Compression: Store
        cd_buf.extend_from_slice(&0x0000u16.to_le_bytes()); // Mod time
        cd_buf.extend_from_slice(&0x5821u16.to_le_bytes()); // Mod date
        cd_buf.extend_from_slice(&crc.to_le_bytes()); // CRC-32
        cd_buf.extend_from_slice(&size.to_le_bytes()); // Compressed size
        cd_buf.extend_from_slice(&size.to_le_bytes()); // Uncompressed size
        cd_buf.extend_from_slice(&(name_bytes.len() as u16).to_le_bytes()); // Name len
        cd_buf.extend_from_slice(&0u16.to_le_bytes()); // Extra len
        cd_buf.extend_from_slice(&0u16.to_le_bytes()); // Comment len
        cd_buf.extend_from_slice(&0u16.to_le_bytes()); // Disk start 0
        cd_buf.extend_from_slice(&0u16.to_le_bytes()); // Internal file attr
        cd_buf.extend_from_slice(&0u32.to_le_bytes()); // External file attr
        cd_buf.extend_from_slice(&offset.to_le_bytes()); // Local header offset
        cd_buf.extend_from_slice(name_bytes);
    }

    let cd_offset = archive.len() as u32;
    let cd_size = cd_buf.len() as u32;
    archive.extend_from_slice(&cd_buf);

    // --- 3. End of Central Directory Record (22 bytes) ---
    archive.extend_from_slice(&0x06054b50u32.to_le_bytes()); // Signature
    archive.extend_from_slice(&0u16.to_le_bytes()); // Disk number 0
    archive.extend_from_slice(&0u16.to_le_bytes()); // Disk with CD start 0
    archive.extend_from_slice(&(files.len() as u16).to_le_bytes()); // Entries on this disk
    archive.extend_from_slice(&(files.len() as u16).to_le_bytes()); // Total entries
    archive.extend_from_slice(&cd_size.to_le_bytes()); // Central directory size
    archive.extend_from_slice(&cd_offset.to_le_bytes()); // Central directory offset
    archive.extend_from_slice(&0u16.to_le_bytes()); // Comment len 0

    Ok(archive)
}

/// Generates a complete Unified Deliverables Package in-memory.
///
/// Returns the raw binary bytes of the .zip archive containing all timelines,
/// scripts, reports, contact sheets, CDL/CUBE grades, and hero stills.
pub fn build_unified_deliverables_package(
    title: &str,
    source_clip_name: &str,
    takes: &[ShotTake],
    fps: f64,
    hero_stills: Option<&[(String, &RgbImage)]>,
) -> Result<Vec<u8>, String> {
    let mut files: Vec<(String, Vec<u8>)> = Vec::new();

    // 1. CMX 3600 EDL
    let edl = generate_cmx3600_edl(title, source_clip_name, takes, fps);
    files.push(("EDL/AESTHETIC_Selects.edl".to_string(), edl.into_bytes()));

    // 2. FCPXML 1.8 Timeline
    let fcpxml = generate_fcpxml(title, source_clip_name, takes, fps);
    files.push(("XML/AESTHETIC_Timeline.xml".to_string(), fcpxml.into_bytes()));

    // 3. DaVinci Resolve Python Script
    let py_script = generate_resolve_timeline_script(title, source_clip_name, takes, fps);
    files.push(("Scripts/AESTHETIC_Resolve_Import.py".to_string(), py_script.into_bytes()));

    // 4. CSV Selects Manifest
    let csv = generate_csv_selects(source_clip_name, takes, fps);
    files.push(("Reports/AESTHETIC_Selects_Manifest.csv".to_string(), csv.into_bytes()));

    // 5. JSON Metadata Manifest
    let json_summary = serde_json::to_string_pretty(&serde_json::json!({
        "project_title": title,
        "source_clip": source_clip_name,
        "fps": fps,
        "takes_count": takes.len(),
        "takes": takes
    }))
    .unwrap_or_else(|_| "{}".to_string());
    files.push(("Manifest/manifest.json".to_string(), json_summary.into_bytes()));

    // 6. Visual Contact Sheet HTML
    let contact_sheet = generate_contact_sheet_html(title, source_clip_name, takes, 1);
    files.push(("ContactSheet/AESTHETIC_Contact_Sheet.html".to_string(), contact_sheet.into_bytes()));

    // 7. Master Baseline CDL & 3D LUT Grade Emulation
    if let Some(hero_take) = takes.first() {
        let master_grade = compute_master_baseline_cdl_grade(hero_take, None, None, None);
        let cdl_xml = generate_asc_cdl_xml(&master_grade, title, "Golden_Baseline");
        let lut_cube = generate_3d_lut_cube(&master_grade, &format!("{}_Master_Grade", title), 33);

        files.push(("Grades/Master_Baseline_Look.cdl".to_string(), cdl_xml.into_bytes()));
        files.push(("Grades/Master_Baseline_Look.cube".to_string(), lut_cube.into_bytes()));
    }

    // 8. Companion Hero Frame Stills
    if let Some(stills) = hero_stills {
        for (name, img) in stills {
            let mut png_bytes = Vec::new();
            if img.write_to(&mut Cursor::new(&mut png_bytes), image::ImageFormat::Png).is_ok() {
                let filename = format!("Stills/{}.png", name.trim_end_matches(".png"));
                files.push((filename, png_bytes));
            }
        }
    }

    // 9. README Deliverables Handover
    let readme = format!(
        r"================================================================================
  AESTHETIC (v0.1.0) — Unified Editorial & Cinematography Deliverables
================================================================================
Project:     {}
Source Media: {}
Frame Rate:   {:.3} fps
Hero Selects: {} takes

CONTENTS OVERVIEW:
------------------
1. EDL/
   - AESTHETIC_Selects.edl
     Standard CMX 3600 Edit Decision List for Avid Media Composer, Adobe Premiere,
     and FilmLight Baselight.

2. XML/
   - AESTHETIC_Timeline.xml
     Final Cut Pro XML interchange timeline with clip boundaries and markers.

3. Scripts/
   - AESTHETIC_Resolve_Import.py
     Python automation script for DaVinci Resolve Studio. Directly builds the
     hero selects timeline with frame-accurate, color-coded rationale & forensic markers.

4. Reports/
   - AESTHETIC_Selects_Manifest.csv
     Full tabular spreadsheet detailing timecodes, pillar scores, and DP affinities.

5. ContactSheet/
   - AESTHETIC_Contact_Sheet.html
     Interactive, zero-dependency browser contact sheet with collapsible metrics trees.

6. Grades/
   - Master_Baseline_Look.cdl
     ASC CDL XML tone & color transfer grade pulling footage toward the calibrated
     1,112-shot Golden Baseline median (9.98 stops DR, 5600K neutral, 100% roll-off).
   - Master_Baseline_Look.cube
     33x33x33 3D LUT for zero-configuration application on color grading tracks.

7. Stills/
   - Hero select frames exported in pristine, uncompressed PNG format.

Handed over by AESTHETIC Cinematography Intelligence Engine.
",
        title,
        source_clip_name,
        fps,
        takes.len()
    );
    files.push(("README_DELIVERABLES.txt".to_string(), readme.into_bytes()));

    // Build slices reference for PKZIP packager
    let file_slices: Vec<(&str, &[u8])> = files
        .iter()
        .map(|(name, data)| (name.as_str(), data.as_slice()))
        .collect();

    create_pkzip_archive(&file_slices)
}

/// Unpacks and exports the unified deliverables directly to an on-disk folder
/// and writes the companion .zip archive.
pub fn export_deliverables_directory(
    output_dir: &Path,
    title: &str,
    source_clip_name: &str,
    takes: &[ShotTake],
    fps: f64,
    hero_stills: Option<&[(String, &RgbImage)]>,
) -> Result<PathBuf, String> {
    let zip_bytes = build_unified_deliverables_package(title, source_clip_name, takes, fps, hero_stills)?;

    std::fs::create_dir_all(output_dir)
        .map_err(|e| format!("Failed to create deliverables directory {:?}: {}", output_dir, e))?;

    let clean_title = title.replace(['/', '\\', ':', '*', '?', '"', '<', '>', '|'], "_");
    let zip_filename = format!("AESTHETIC_Deliverables_{}.zip", clean_title);
    let zip_path = output_dir.join(&zip_filename);

    std::fs::write(&zip_path, &zip_bytes)
        .map_err(|e| format!("Failed to write deliverables zip to {:?}: {}", zip_path, e))?;

    // Also unpack loose deliverables for instant access
    let edl_dir = output_dir.join("EDL");
    let xml_dir = output_dir.join("XML");
    let scripts_dir = output_dir.join("Scripts");
    let reports_dir = output_dir.join("Reports");
    let grades_dir = output_dir.join("Grades");
    let cs_dir = output_dir.join("ContactSheet");

    let _ = std::fs::create_dir_all(&edl_dir);
    let _ = std::fs::create_dir_all(&xml_dir);
    let _ = std::fs::create_dir_all(&scripts_dir);
    let _ = std::fs::create_dir_all(&reports_dir);
    let _ = std::fs::create_dir_all(&grades_dir);
    let _ = std::fs::create_dir_all(&cs_dir);

    let _ = std::fs::write(
        edl_dir.join("AESTHETIC_Selects.edl"),
        generate_cmx3600_edl(title, source_clip_name, takes, fps),
    );
    let _ = std::fs::write(
        xml_dir.join("AESTHETIC_Timeline.xml"),
        generate_fcpxml(title, source_clip_name, takes, fps),
    );
    let _ = std::fs::write(
        scripts_dir.join("AESTHETIC_Resolve_Import.py"),
        generate_resolve_timeline_script(title, source_clip_name, takes, fps),
    );
    let _ = std::fs::write(
        reports_dir.join("AESTHETIC_Selects_Manifest.csv"),
        generate_csv_selects(source_clip_name, takes, fps),
    );
    let _ = std::fs::write(
        cs_dir.join("AESTHETIC_Contact_Sheet.html"),
        generate_contact_sheet_html(title, source_clip_name, takes, 1),
    );

    if let Some(hero_take) = takes.first() {
        let master_grade = compute_master_baseline_cdl_grade(hero_take, None, None, None);
        let cdl_xml = generate_asc_cdl_xml(&master_grade, title, "Golden_Baseline");
        let lut_cube = generate_3d_lut_cube(&master_grade, &format!("{}_Master_Grade", title), 33);
        let _ = std::fs::write(grades_dir.join("Master_Baseline_Look.cdl"), cdl_xml);
        let _ = std::fs::write(grades_dir.join("Master_Baseline_Look.cube"), lut_cube);
    }

    Ok(zip_path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pkzip_creation_and_signatures() {
        let files = [
            ("test.txt", "Hello World!".as_bytes()),
            ("sub/data.json", r#"{"status": "ok"}"#.as_bytes()),
        ];

        let zip = create_pkzip_archive(&files).expect("Zip creation must succeed");
        assert!(zip.len() > 100);

        // Verify Local Header Signature (0x04034b50 -> [0x50, 0x4b, 0x03, 0x04])
        assert_eq!(&zip[0..4], &[0x50, 0x4b, 0x03, 0x04]);

        // Verify End of Central Directory Signature (0x06054b50 -> [0x50, 0x4b, 0x05, 0x06])
        let eocd_idx = zip.len() - 22;
        assert_eq!(&zip[eocd_idx..eocd_idx + 4], &[0x50, 0x4b, 0x05, 0x06]);
    }

    #[test]
    fn test_build_unified_deliverables_package() {
        let takes = vec![ShotTake {
            take_id: "take_001".to_string(),
            scene_index: 1,
            start_sec: 10.0,
            end_sec: 15.0,
            duration_sec: 5.0,
            hero_timestamp_sec: 12.5,
            hero_frame_index: Some(300),
            scores: Default::default(),
            measured: Default::default(),
            craft: Default::default(),
            style: Default::default(),
            concerns: Vec::new(),
            golden_baseline: Vec::new(),
            rationale_summary: "Master Select Take".to_string(),
        }];

        let zip = build_unified_deliverables_package(
            "TEST_PROJECT",
            "TEST_CLIP.MOV",
            &takes,
            24.0,
            None,
        )
        .expect("Package build must succeed");

        assert!(zip.len() > 1000);
        assert_eq!(&zip[0..4], &[0x50, 0x4b, 0x03, 0x04]);
    }
}
