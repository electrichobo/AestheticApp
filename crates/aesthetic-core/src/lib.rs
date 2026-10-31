//! AESTHETIC Core Engine
//!
//! Video ingest, cut detection, usable window analysis, and
//! end-to-end evaluation pipeline.

pub mod pipeline;
pub mod scene;
pub mod video;
pub mod window;

pub use pipeline::evaluate_candidate_frame;
pub use scene::{
    classify_transition, compute_frame_difference, detect_directional_wipe, TransitionType,
};
pub use window::{find_best_usable_window, FrameEvaluationSample};
