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

pub use baseline_store::{cosine_similarity, BaselineStore};
pub use export::{generate_cmx3600_edl, generate_csv_selects, seconds_to_smpte_timecode};
pub use inference::{DepthMap, ModelInferenceEngine};
pub use video::{extract_frame_rgb, extract_trimmed_clip, probe_video_metadata};

pub use pipeline::evaluate_candidate_frame;
pub use scene::{
    classify_transition, compute_frame_difference, detect_directional_wipe, TransitionType,
};
pub use window::{find_best_usable_window, FrameEvaluationSample};
