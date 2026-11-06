# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M14–M17 (Sequence Continuity, Style-Cluster Quantiles, Forensics & Cached Rescore)
- **100% Real Measured Golden Baseline (`n=760` across 135 Award-Winning Films)**:
  - `assets/baseline/` (`version = "2.0.0-measured"`) holds 285 decoded continuous video setups from 55 award films on `M:\movies` + 475 multi-shot high-res stills across 92 collections from `film-grab.com`, `shot.cafe`, and `frameset.app`.
- **M14: Cross-Shot Sequence Continuity, Log-Encoding Detection & MMR Reel Diversity**:
  - Added `ReelSequenceMetrics` (`wb_cross_scene_std`, `color_temp_cross_scene_std`, `exposure_consistency_std`, `coverage_consistency_score`, `grading_uniformity_score`, `visual_fatigue_index`, `reel_diversity_score`, `transfer_curve_label`).
  - Added container + pixel-level camera log/HDR detection (`LOG_ENCODED_SIGNAL`) and Maximal Marginal Relevance (`apply_reel_diversity_ranking`) to prevent recurring setups from crowding Top-$N$ selects.
- **M15: Within-Style-Cluster & Motion Velocity Baseline Quantiles**:
  - `compare_to_golden_baseline_with_style` evaluates global award-cinema percentiles plus within-style-cluster percentiles (`Within-Style DR`, `Within-Style Key:Fill`) and measured optical flow velocity percentiles.
- **M16 & M17: Non-Punitive Forensics & Instant Cached Sidecar Re-Scoring**:
  - Added `SUBTITLE_OR_LOWER_THIRD_BURNIN`, `PRACTICAL_LIGHT_FLICKER`, and `ROLLING_SHUTTER_SKEW_RISK` detectors plus `rescore_from_sidecars` (`aesthetic-cli rescore <dir>`, ~240ms for 12 takes).
- **Quality**: All 26 workspace tests passing, zero clippy warnings (`-D warnings`).

---

## Next Immediate Step
1. **Commit & Push**: Await user command to commit and push M14–M17 deliverables.
2. **Interactive UI & DaVinci Resolve Bridge**: Inspect sequence continuity in `aesthetic-ui` or push selects to DaVinci Resolve.

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by user.
