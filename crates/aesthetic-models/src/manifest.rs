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
