# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M14–M19 (Complete Metric Taxonomy, Reranker Heads & Feedback Learning)
- **100% Real Measured Golden Baseline (`n=760` across 135 Award-Winning Films)**:
  - `assets/baseline/` (`version = "2.0.0-measured"`) holds 285 decoded continuous video setups from 55 award films on `M:\movies` + 475 multi-shot high-res stills across 92 collections from `film-grab.com`, `shot.cafe`, and `frameset.app`.
- **M14–M17: Sequence Continuity, Style Quantiles, Forensics & Instant Cached Rescore**:
  - Added `ReelSequenceMetrics` (`wb_cross_scene_std`, `color_temp_cross_scene_std`, `exposure_consistency_std`, `coverage_consistency_score`, `grading_uniformity_score`, `visual_fatigue_index`, `reel_diversity_score`, `transfer_curve_label`).
  - Added container + pixel-level camera log/HDR detection (`LOG_ENCODED_SIGNAL`) and Maximal Marginal Relevance (`apply_reel_diversity_ranking`).
  - Added `compare_to_golden_baseline_with_style` (within-style-cluster DR & Key:Fill percentiles + motion velocity), non-punitive forensics (`SUBTITLE_OR_LOWER_THIRD_BURNIN`, `PRACTICAL_LIGHT_FLICKER`, `ROLLING_SHUTTER_SKEW_RISK`), and `rescore_from_sidecars` (`aesthetic-cli rescore <dir>`, ~240ms).
- **M18 & M19: Full 6-Head Narrative Rerankers, Motion Coherence, Palette Family & Feedback Learning**:
  - Added all 6 narrative reranker heads (`hero_potency_score`, `three_second_impact_score`, `authorship_distinctiveness_score`, `storytelling_score`, `cinematic_technique_score`, `memorability_score`) to `PillarScores`.
  - Integrated log-aware CIE 1931 gamut coverage (`gamut_coverage_srgb`/`p3`), `palette_family`, `scene_type`, `shot_intent`, and `motion_coherence_score` (`motion_blur_angle_deg`) into pillar scoring and Desktop UI / HTML contact sheets.
  - Added `SelectFeedbackEvent` preference logger (`log_select_feedback_event`, `compute_feedback_preference_boost`, `/api/feedback`, `aesthetic-cli feedback`).
- **Quality**: All workspace tests passing, zero clippy warnings (`-D warnings`).

---

## Next Immediate Step
1. **Interactive Desktop UI & DaVinci Resolve Bridge**: Inspect sequence continuity, 6 narrative reranker heads, and select feedback learning in `aesthetic-ui` or push selects to DaVinci Resolve.

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by user.
