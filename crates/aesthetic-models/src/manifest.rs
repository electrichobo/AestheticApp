//! Run Manifest and Analysis Metadata

use crate::window::ShotTake;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct VideoSourceInfo {
    pub file_path: String,
    pub duration_sec: f64,
    pub frame_rate: f64,
    pub width: u32,
    pub height: u32,
    pub codec: String,
    pub color_primaries: Option<String>,
    pub transfer_characteristic: Option<String>,
}

impl VideoSourceInfo {
    /// Inspects container transfer characteristic metadata for camera log or HDR curves.
    pub fn classify_transfer_curve(&self) -> (bool, String) {
        if let Some(ref trc) = self.transfer_characteristic {
            let lower = trc.trim().to_lowercase();
            if lower.contains("smpte2084") || lower.contains("pq") {
                return (true, "PQ (SMPTE ST.2084 HDR)".to_string());
            }
            if lower.contains("arib-std-b67") || lower.contains("hlg") {
                return (true, "HLG (Hybrid Log-Gamma HDR)".to_string());
            }
            if lower.contains("log")
                || lower.contains("slog")
                || lower.contains("logc")
                || lower.contains("vlog")
                || lower.contains("bmdfilm")
            {
                return (true, format!("Camera Log ({})", trc));
            }
            if !lower.is_empty() && lower != "unknown" {
                return (false, format!("Display-Referred ({})", trc));
            }
        }
        (false, "Rec.709 Display-Referred".to_string())
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AnalysisRunMetadata {
    pub run_id: String,
    pub timestamp_utc: String,
    pub engine_version: String,
    pub baseline_version: String,
    pub source: VideoSourceInfo,
    pub total_takes: usize,
    pub selected_takes: Vec<ShotTake>,
}
