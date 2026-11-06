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

pub use baseline_store::{
    cosine_similarity, find_primary_video_file, parse_movie_folder_name,
    scan_and_ingest_media_server, BaselineStore, IngestSummary, ServerIngestReport,
};
pub use export::{
    export_shot_sidecars, export_shot_sidecars_with_frames, generate_cmx3600_edl,
    generate_contact_sheet_html, generate_contact_sheet_html_with_frames, generate_csv_selects,
    generate_fcpxml, rescore_from_sidecars, seconds_to_smpte_timecode,
};
pub use inference::{DepthMap, ModelInferenceEngine};
pub use video::{extract_frame_rgb, extract_trimmed_clip, probe_video_metadata};

pub use pipeline::{
    analyze_video_file, apply_reel_diversity_ranking, compute_feedback_preference_boost,
    compute_reel_sequence_metrics, detect_burst_light_flicker, detect_flat_log_encoding,
    detect_subtitle_or_lower_third_burnin, enrich_take, evaluate_candidate_frame,
    log_select_feedback_event, BatchAnalysisResult, BatchOptions,
};
pub use scene::{
    classify_transition, compute_frame_difference, detect_directional_wipe, TransitionType,
};
pub use window::{find_best_usable_window, FrameEvaluationSample};
