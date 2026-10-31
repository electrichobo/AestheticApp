//! Golden Baseline Vector & Craft Store
//!
//! Stores reference embeddings and empirical craft distributions for award-winning
//! cinema. Supports multi-threaded cosine similarity search and master DP matching.

use aesthetic_models::baseline::{
    BaselineCorpusManifest, CinematographerSignature, MasterMatchResult, MetricQuantiles,
    ReferenceShot,
};
use rayon::prelude::*;
use std::fs::{self, File};
use std::io::{BufReader, BufWriter};
use std::path::Path;

/// Compute cosine similarity between two float vectors (scaled 0.0 - 100.0).
pub fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() || a.is_empty() {
        return 0.0;
    }

    let mut dot = 0.0f32;
    let mut norm_a = 0.0f32;
    let mut norm_b = 0.0f32;

    for (x, y) in a.iter().zip(b.iter()) {
        dot += x * y;
        norm_a += x * x;
        norm_b += y * y;
    }

    let denom = norm_a.sqrt() * norm_b.sqrt();
    if denom > 1e-6 {
        // Map [-1.0, 1.0] to [0.0, 100.0]
        let cos = (dot / denom).clamp(-1.0, 1.0);
        ((cos + 1.0) * 50.0).clamp(0.0, 100.0)
    } else {
        0.0
    }
}

/// The local Golden Baseline corpus store.
#[derive(Debug, Clone, Default)]
pub struct BaselineStore {
    pub manifest: BaselineCorpusManifest,
    pub reference_shots: Vec<ReferenceShot>,
    pub master_signatures: Vec<CinematographerSignature>,
}

impl BaselineStore {
    /// Create a new empty baseline store.
    pub fn new() -> Self {
        Self::default()
    }

    /// Add a reference shot to the baseline corpus.
    pub fn add_reference_shot(&mut self, shot: ReferenceShot) {
        self.reference_shots.push(shot);
        self.manifest.total_reference_shots = self.reference_shots.len();
    }

    /// Register a master cinematographer signature.
    pub fn register_signature(&mut self, sig: CinematographerSignature) {
        self.master_signatures.push(sig);
    }

    /// Multi-threaded search for the top-K most visually similar reference shots.
    pub fn search_nearest(
        &self,
        candidate_embedding: &[f32],
        top_k: usize,
    ) -> Vec<(&ReferenceShot, f32)> {
        if self.reference_shots.is_empty() || candidate_embedding.is_empty() {
            return Vec::new();
        }

        let mut scored: Vec<(&ReferenceShot, f32)> = self
            .reference_shots
            .par_iter()
            .map(|shot| {
                let sim = cosine_similarity(candidate_embedding, &shot.embedding);
                (shot, sim)
            })
            .collect();

        // Sort descending by similarity
        scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        scored.truncate(top_k);
        scored
    }

    /// Match candidate shot against master cinematographer signatures and return natural craft explanation.
    pub fn match_master_cinematographer(
        &self,
        candidate_embedding: &[f32],
        candidate_key_fill: f32,
    ) -> Option<MasterMatchResult> {
        if self.master_signatures.is_empty() || candidate_embedding.is_empty() {
            return None;
        }

        let best = self
            .master_signatures
            .iter()
            .map(|sig| {
                let visual_sim = cosine_similarity(candidate_embedding, &sig.centroid_embedding);
                // Bonus if key-fill ratio matches typical master habits within 20%
                let kf_diff = (candidate_key_fill - sig.average_key_fill).abs();
                let kf_bonus = if kf_diff < 1.0 { 5.0 } else { 0.0 };
                let combined_sim = (visual_sim + kf_bonus).min(100.0);
                (sig, combined_sim)
            })
            .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal))?;

        let sig = best.0;
        let sim = best.1;
        let ref_film = sig
            .representative_films
            .first()
            .cloned()
            .unwrap_or_else(|| "Reference Film".to_string());

        let explanation = format!(
            "Framing and lighting geometry mirror {}'s signature in {} ({:.1}% match).",
            sig.dp_name, ref_film, sim
        );

        Some(MasterMatchResult {
            dp_name: sig.dp_name.clone(),
            reference_film: ref_film,
            visual_similarity: sim,
            craft_explanation: explanation,
        })
    }

    /// Recompute empirical distribution quantiles across all reference shots.
    pub fn recompute_quantiles(&mut self) {
        if self.reference_shots.is_empty() {
            return;
        }

        let mut dr_values: Vec<f32> = self
            .reference_shots
            .iter()
            .map(|s| s.dynamic_range_stops)
            .collect();
        let mut rolloff_values: Vec<f32> = self
            .reference_shots
            .iter()
            .map(|s| s.highlight_rolloff)
            .collect();
        let mut sharp_values: Vec<f32> = self
            .reference_shots
            .iter()
            .map(|s| s.sharpness_laplacian)
            .collect();

        self.manifest.dynamic_range_quantiles = compute_quantiles(&mut dr_values);
        self.manifest.highlight_rolloff_quantiles = compute_quantiles(&mut rolloff_values);
        self.manifest.sharpness_quantiles = compute_quantiles(&mut sharp_values);
    }

    /// Save baseline store to disk.
    pub fn save_to_dir(&self, dir: &Path) -> Result<(), String> {
        fs::create_dir_all(dir).map_err(|e| format!("Failed to create baseline dir: {}", e))?;

        let manifest_path = dir.join("manifest.json");
        let shots_path = dir.join("shots.json");
        let sigs_path = dir.join("signatures.json");

        let f_manifest = File::create(manifest_path).map_err(|e| e.to_string())?;
        serde_json::to_writer_pretty(BufWriter::new(f_manifest), &self.manifest)
            .map_err(|e| e.to_string())?;

        let f_shots = File::create(shots_path).map_err(|e| e.to_string())?;
        serde_json::to_writer(BufWriter::new(f_shots), &self.reference_shots)
            .map_err(|e| e.to_string())?;

        let f_sigs = File::create(sigs_path).map_err(|e| e.to_string())?;
        serde_json::to_writer_pretty(BufWriter::new(f_sigs), &self.master_signatures)
            .map_err(|e| e.to_string())?;

        Ok(())
    }

    /// Load baseline store from disk.
    pub fn load_from_dir(dir: &Path) -> Result<Self, String> {
        let manifest_path = dir.join("manifest.json");
        let shots_path = dir.join("shots.json");
        let sigs_path = dir.join("signatures.json");

        if !manifest_path.exists() {
            return Err("Manifest file not found".to_string());
        }

        let f_manifest = File::open(manifest_path).map_err(|e| e.to_string())?;
        let manifest: BaselineCorpusManifest =
            serde_json::from_reader(BufReader::new(f_manifest)).map_err(|e| e.to_string())?;

        let reference_shots: Vec<ReferenceShot> = if shots_path.exists() {
            let f_shots = File::open(shots_path).map_err(|e| e.to_string())?;
            serde_json::from_reader(BufReader::new(f_shots)).unwrap_or_default()
        } else {
            Vec::new()
        };

        let master_signatures: Vec<CinematographerSignature> = if sigs_path.exists() {
            let f_sigs = File::open(sigs_path).map_err(|e| e.to_string())?;
            serde_json::from_reader(BufReader::new(f_sigs)).unwrap_or_default()
        } else {
            Vec::new()
        };

        Ok(Self {
            manifest,
            reference_shots,
            master_signatures,
        })
    }
}

/// Helper to compute empirical quantiles from a mutable slice of floats.
fn compute_quantiles(vals: &mut [f32]) -> MetricQuantiles {
    if vals.is_empty() {
        return MetricQuantiles::default();
    }

    vals.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let len = vals.len();

    let get_p = |pct: f32| -> f32 {
        let idx = ((len as f32) * pct).round() as usize;
        vals[idx.min(len - 1)]
    };

    MetricQuantiles {
        min: vals[0],
        p10: get_p(0.10),
        p25: get_p(0.25),
        p50: get_p(0.50),
        p75: get_p(0.75),
        p90: get_p(0.90),
        max: vals[len - 1],
    }
}
