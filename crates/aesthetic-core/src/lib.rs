//! AESTHETIC Core Engine
//!
//! Video ingest, cut detection, usable window analysis, and
//! end-to-end evaluation pipeline.

pub mod baseline_store;
pub mod export;
pub mod inference;
pub mod pipeline;
pub mod scene;
pub mod video;
pub mod web_ingest;
pub mod window;

pub use baseline_store::{cosine_similarity, BaselineStore, IngestSummary};
pub use export::{
    export_shot_sidecars, generate_cmx3600_edl, generate_contact_sheet_html, generate_csv_selects,
    generate_fcpxml, seconds_to_smpte_timecode,
};
pub use inference::{DepthMap, ModelInferenceEngine};
pub use video::{extract_frame_rgb, extract_trimmed_clip, probe_video_metadata};

pub use pipeline::{
    analyze_video_file, evaluate_candidate_frame, BatchAnalysisResult, BatchOptions,
};
pub use scene::{
    classify_transition, compute_frame_difference, detect_directional_wipe, TransitionType,
};
pub use window::{find_best_usable_window, FrameEvaluationSample};
