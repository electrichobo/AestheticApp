//! Golden Baseline Data Contracts
//!
//! Stores reference corpus metadata, master cinematographer clusters,
//! and empirical distribution quantiles used to calibrate raw measurements
//! into tangible 0.0 - 100.0 percentile scores.

use serde::{Deserialize, Serialize};

/// Quantiles representing the empirical distribution of a metric across reference films.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct MetricQuantiles {
    pub min: f32,
    pub p10: f32,
    pub p25: f32,
    pub p50: f32,
    pub p75: f32,
    pub p90: f32,
    pub max: f32,
}

impl MetricQuantiles {
    /// Compute a calibrated 0.0 - 100.0 percentile score from a raw measurement.
    pub fn compute_percentile_score(&self, value: f32) -> f32 {
        if value <= self.min {
            return 0.0;
        }
        if value >= self.max {
            return 100.0;
        }

        if value <= self.p10 {
            10.0 * (value - self.min) / (self.p10 - self.min).max(1e-4)
        } else if value <= self.p25 {
            10.0 + 15.0 * (value - self.p10) / (self.p25 - self.p10).max(1e-4)
        } else if value <= self.p50 {
            25.0 + 25.0 * (value - self.p25) / (self.p50 - self.p25).max(1e-4)
        } else if value <= self.p75 {
            50.0 + 25.0 * (value - self.p50) / (self.p75 - self.p50).max(1e-4)
        } else if value <= self.p90 {
            75.0 + 15.0 * (value - self.p75) / (self.p90 - self.p75).max(1e-4)
        } else {
            90.0 + 10.0 * (value - self.p90) / (self.max - self.p90).max(1e-4)
        }
        .clamp(0.0, 100.0)
    }
}

/// Metadata for a film ingested into the Golden Baseline corpus.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct IngestedReferenceFilm {
    pub title: String,
    pub cinematographer: String,
    pub director: Option<String>,
    pub year: u32,
    pub aspect_ratio: String,
    pub shot_count: usize,
    pub average_dynamic_range: f32,
}

/// A single reference shot stored in the Golden Baseline corpus.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReferenceShot {
    pub shot_id: String,
    pub film_title: String,
    pub cinematographer: String,
    pub timestamp_sec: f64,
    /// 1152-dimensional SigLIP or vision embedding vector
    pub embedding: Vec<f32>,
    pub dynamic_range_stops: f32,
    pub highlight_rolloff: f32,
    pub sharpness_laplacian: f32,
    pub key_fill_ratio: f32,
    pub style_label: String,
}

/// A cluster representing a master cinematographer's visual signature.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CinematographerSignature {
    pub dp_name: String,
    pub representative_films: Vec<String>,
    pub centroid_embedding: Vec<f32>,
    pub average_key_fill: f32,
    pub preferred_lighting_key: String,
    pub preferred_motion_style: String,
}

/// The result of matching a candidate shot against master cinematographer signatures.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MasterMatchResult {
    pub dp_name: String,
    pub reference_film: String,
    pub visual_similarity: f32, // 0.0 - 100.0
    pub craft_explanation: String,
}

/// Overall baseline corpus manifest and distribution state.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct BaselineCorpusManifest {
    pub version: String,
    pub total_films: usize,
    pub total_reference_shots: usize,
    pub films: Vec<IngestedReferenceFilm>,
    pub dynamic_range_quantiles: MetricQuantiles,
    pub highlight_rolloff_quantiles: MetricQuantiles,
    pub sharpness_quantiles: MetricQuantiles,
    pub mtf_quantiles: MetricQuantiles,
    pub baseline_similarity_quantiles: MetricQuantiles,
}
