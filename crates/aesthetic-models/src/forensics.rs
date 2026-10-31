//! Layer 5: Forensic Diagnostics Models
//!
//! Non-punitive technical flags and capture defect detection.
//! These metrics surface technical warnings to editors and DPs without
//! unfairly depressing artistic or creative scores.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum DiagnosticSeverity {
    Info,
    Warning,
    Critical,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DiagnosticFlag {
    pub code: String,
    pub title: String,
    pub description: String,
    pub severity: DiagnosticSeverity,
    pub timestamp_sec: f64,
    pub affected_region: Option<[f32; 4]>, // Normalized bbox [x, y, w, h]
}

/// Diagnostic metadata and artifact checks.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct ForensicDiagnostics {
    pub flags: Vec<DiagnosticFlag>,
    pub sensor_dust_detected: bool,
    pub dead_pixel_count: u32,
    pub flickering_practical_detected: bool,
    pub rolling_shutter_wobble_score: f32,
    pub clipping_persistence_sec: f32,
    pub moire_susceptibility_score: f32,
}
