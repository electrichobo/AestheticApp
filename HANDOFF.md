# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M24–M27 Complete & Verified
- **M24–M28: Live Resolve Bridge, Batch Queue, Smart Showreel Modal & Personal Tuning**:
  - `send_to_live_resolve` executing one-click timeline and marker assembly into active Resolve projects (`--live-resolve`, UI button, `/api/send_to_resolve`).
  - `analyze_folder_queue` batch processing entire production folders (e.g. episodic web series, dailies) with per-file sidecars & contact sheets (`batch <dir>`, UI folder queue, `/api/batch_folder`).
  - `compose_smart_showreel` & Desktop UI Smart Reel modal (`#composer-modal`, `/api/compose_showreel`) assembling curated reels to target durations (30s/60s/90s/120s) with shot-scale alternating rhythm & CCT continuity across 4 objective profiles.
  - `compute_personal_taste_profile` dynamically calibrating cinematographer style affinities and adaptive narrative reranker weights directly from user curation feedback events (`/api/taste_profile`).
- **Golden Baseline**: 1,112 real measured reference shots across 199 award-winning films (`manifest.json` v2.0.0-measured, 0 synthetic seeds).
- **Quality**: Workspace tests passing, zero clippy warnings (`-D warnings`).

---

## Next Immediate Step
1. **Production Operation**: Launch `aesthetic-ui` or run batch analysis on remaining project folders (`aesthetic-cli batch`).

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by user.
