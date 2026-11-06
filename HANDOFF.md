# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M20–M23 Complete & Self-Audited (`1,112` Measured Shots / `199` Films)
- **100% Real Measured Golden Baseline (`n=1,112` across `199` Award-Winning Films)**:
  - `assets/baseline/` (`version = "2.0.0-measured"`) holds 285 decoded continuous video setups from 55 award films on `M:\movies` + 827 multi-shot high-res stills across 159 collections from `film-grab.com`, `shot.cafe`, and `frameset.app` (`DR p50 = 9.98 stops`, `Roll-Off p50 = 100.0%`, `Laplacian p50 = 48.39`).
- **M14–M19: Sequence Continuity, Style Quantiles, Forensics, Cached Rescore & 6 Reranker Heads**:
  - `ReelSequenceMetrics` (cross-scene WB/Kelvin/Luma continuity, visual fatigue, MMR reel diversity, Log/HDR transfer detection).
  - Within-style-cluster DR & Key:Fill percentiles + motion velocity quantiles (`compare_to_golden_baseline_with_style`), non-punitive forensics (`SUBTITLE_OR_LOWER_THIRD_BURNIN`, `PRACTICAL_LIGHT_FLICKER`, `ROLLING_SHUTTER_SKEW_RISK`), and instant cached sidecar re-scoring (`rescore_from_sidecars`).
  - All 6 Narrative & Aesthetic reranker heads (`hero_potency_score`, `three_second_impact_score`, `authorship_distinctiveness_score`, `storytelling_score`, `cinematic_technique_score`, `memorability_score`) + `SelectFeedbackEvent` preference learning.
- **M20–M23: DP Rationale Engine, PSNR/SSIM QC Pack, UI Curation Controls & DaVinci Resolve Bridge**:
  - Added deterministic DP/Editorial `rationale_summary` and full-reference `psnr_db` / `ssim_score` (`compute_frame_pair_psnr_and_ssim`).
  - Added one-click UI curation buttons (`Promote Hero`, `Pin Select`, `Deprioritize`), instant Cached Sidecars folder loader (`/api/rescore_sidecars`), and DaVinci Resolve Python timeline/marker script bridge (`generate_resolve_timeline_script`, `/api/export_resolve_script`, `--resolve`).
- **Quality**: All 26 workspace tests passing, zero clippy warnings (`-D warnings`).

---

## Next Immediate Step
1. **Production Operation**: Launch `aesthetic-ui` or `aesthetic-cli` on new productions or import generated `.py` / `.fcpxml` timelines directly into DaVinci Resolve.

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by user.
