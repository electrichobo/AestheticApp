# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M13 (760-Shot Measured Golden Baseline & Cut-Aware Shot Segmentation)
- **100% Real Measured Golden Baseline (`n=760` across 135 Award-Winning Films)**:
  - Ingested all **55 matched award-winning feature films** on `M:\movies` (285 continuous video setups) plus **92 multi-shot high-resolution still collections** (475 uncompressed frames from `film-grab.com`, `shot.cafe`, and `frameset.app`) into `assets/baseline/`.
  - Purged all legacy synthetic `REF_` seed entries so `assets/baseline/` is **100% real pixel-measured cinema** (`Dynamic Range p10 = 7.33 / p50 = 9.73 / p90 = 11.65 stops`, `Highlight Roll-Off p10 = 97.15% / p50 = 100.0%`, `Laplacian Acutance p50 = 40.43`).
- **Cut-Aware 3-Frame Burst & Same-Setup Consolidation**:
  - `analyze_video_file` extracts 3-frame bursts (`0.25s` interval) at each candidate sample to step past hard cuts (`MAD > 26.0`) and consolidates adjacent samples from the same camera setup (`MAD < 10.5`) into a single optimal `1.5s–4.0s` hero window.
- **Mean-Centered Spatial + Craft Reference Matching**:
  - Upgraded `infer_embedding` to an aspect-ratio-invariant `32x36` spatial-chromatic grid and added `nearest_measured_reference_with_craft` (combining mean-centered Pearson spatial correlation with dynamic range, log-acutance, and key-to-fill craft proximity), eliminating positive-orthant hubness.
- **Lossless PNG Sidecars & Embedded Contact Sheets**:
  - Sidecars save `<take_id>.png` (`hero_frame_png`) alongside `<take_id>.json`; HTML contact sheets embed lossless PNG stills directly (`data:image/png;base64,...`).
- **Quality**: All 25 workspace tests passing, zero clippy warnings (`-D warnings`).

---

## Next Immediate Step
1. **Interactive Desktop UI Verification**: Launch `target\release\aesthetic-ui.exe` to inspect the 760-shot Golden Baseline in the desktop UI.
2. **Commit & Push**: Await user command to commit and push M13 deliverables.

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by user.
