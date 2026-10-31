//! Usable Window Finder & Temporal Optimizer
//!
//! Locates optimal continuous 1.5s - 4.0s usable windows within longer takes,
//! evaluating quality persistence, settle stability, and handle clamps.

use aesthetic_models::temporal::UsableWindow;

#[derive(Debug, Clone)]
pub struct FrameEvaluationSample {
    pub timestamp_sec: f64,
    pub quality_score: f32,
    pub stability_score: f32,
    pub is_settled: bool,
}

/// Optimizes and extracts the best continuous window from a take's frame samples.
pub fn find_best_usable_window(
    samples: &[FrameEvaluationSample],
    min_duration_sec: f64,
    max_duration_sec: f64,
    handle_sec: f64,
    cut_start_sec: f64,
    cut_end_sec: f64,
) -> Option<UsableWindow> {
    if samples.len() < 2 {
        return None;
    }

    let mut best_score = -1.0f32;
    let mut best_window: Option<UsableWindow> = None;

    // Sliding window over sampled frames
    for i in 0..samples.len() {
        let t_start = samples[i].timestamp_sec;

        for j in (i + 1)..samples.len() {
            let t_end = samples[j].timestamp_sec;
            let dur = t_end - t_start;

            if dur < min_duration_sec {
                continue;
            }
            if dur > max_duration_sec {
                break;
            }

            // Compute average quality and stability across this window
            let window_slice = &samples[i..=j];
            let count = window_slice.len() as f32;
            let avg_quality: f32 =
                window_slice.iter().map(|s| s.quality_score).sum::<f32>() / count;
            let avg_stability: f32 =
                window_slice.iter().map(|s| s.stability_score).sum::<f32>() / count;

            // Prefer settled footage and reward sustained duration slightly
            let settle_bonus = if window_slice.last().map(|s| s.is_settled).unwrap_or(false) {
                5.0
            } else {
                0.0
            };
            let duration_bonus =
                ((dur - min_duration_sec) / (max_duration_sec - min_duration_sec) * 5.0) as f32;

            let window_score =
                (avg_quality * 0.7 + avg_stability * 0.3 + settle_bonus + duration_bonus)
                    .clamp(0.0, 100.0);

            if window_score > best_score {
                best_score = window_score;

                // Handles clamped to hard cut boundaries
                let rec_in = (t_start - handle_sec).max(cut_start_sec);
                let rec_out = (t_end + handle_sec).min(cut_end_sec);

                best_window = Some(UsableWindow {
                    start_sec: t_start,
                    end_sec: t_end,
                    duration_sec: dur,
                    window_score,
                    stability_score: avg_stability,
                    recommended_in_sec: rec_in,
                    recommended_out_sec: rec_out,
                });
            }
        }
    }

    best_window
}
