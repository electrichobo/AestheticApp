//! AESTHETIC Models
//!
//! Core data contracts for the AESTHETIC video intelligence engine.
//! Models are organized cleanly across the 5 evaluation layers:
//! 1. Objective Physics (pure mathematical measurements)
//! 2. Model-Inferred Craft (deep perceptual inference)
//! 3. Subjective & Aesthetic (perceptual and baseline affinity)
//! 4. Temporal & Editorial (usable window duration, pace, cut-points)
//! 5. Forensic Diagnostics (non-punitive capture warning flags)

pub mod baseline;
pub mod forensics;
pub mod inferred;
pub mod manifest;
pub mod physics;
pub mod subjective;
pub mod temporal;
pub mod window;

pub use baseline::{BaselineCorpusManifest, IngestedReferenceFilm, MetricQuantiles};
pub use forensics::{DiagnosticFlag, DiagnosticSeverity, ForensicDiagnostics};
pub use inferred::{
    FocusOptics, LightingGeometry, ModelInferredCraft, MotionDynamics, StagingEyeline,
};
pub use manifest::{AnalysisRunMetadata, VideoSourceInfo};
pub use physics::{ColorPhysics, ExposurePhysics, ObjectivePhysics, OpticalPhysics};
pub use subjective::{CreativeAesthetic, StyleFamilyCluster};
pub use temporal::{TakeEditorial, UsableWindow};

use serde::{Deserialize, Serialize};

/// Comprehensive metrics evaluation for a single frame.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct FrameMetricsBundle {
    pub frame_index: u64,
    pub timestamp_sec: f64,
    pub physics: ObjectivePhysics,
    pub inferred: ModelInferredCraft,
    pub subjective: CreativeAesthetic,
    pub temporal: TakeEditorial,
    pub forensics: ForensicDiagnostics,
}
