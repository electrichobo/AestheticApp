# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M12 (Desktop UI, High-DPI Scopes & Golden Baseline Overhaul)
- **Golden Baseline Benchmark Thesis**: Primary evaluation compares candidate shots against the **184 Award-Winning Cinema Golden Baseline** (Oscar, ASC & BSC distribution quantiles, `n=176`). DP match is strictly a secondary ancillary tag.
- **High-DPI Continuous Phosphor Scopes**: 760x428 broadcast scopes sample active viewport pixels at 1:1 resolution with vertical scanline phosphor trace connection for smooth, non-pixelated waveform, RGB parade, vectorscope, spline histograms, and CIE 1931.
- **Calibrated Exposure Physics & Credits Filtering**: Scene-referred BT.1886 + EL-Zone dynamic range stops, spatial high-frequency luma/chroma SNR (`compute_spatial_snr`), and automatic `NON_PHOTOGRAPHIC_OR_CREDITS` filtering so black leader/end credits never outrank real cinematography.
- **Complete 58-Metric Contact Sheet & PNG Sidecars**: Both in-app and exported HTML/JSON sidecars include all 58 metrics across all 5 evaluation layers plus lossless `<take_id>.png` hero stills (`hero_frame_png`) and embedded contact-sheet PNGs.
- **Quality**: All 25 workspace tests passing, zero clippy warnings (`-D warnings`).

---

## Next Immediate Step
1. **Interactive Verification**: Launch `target\release\aesthetic-ui.exe` to inspect real media evaluation, popouts, and export workflows.
2. **Commit & Push**: Await user command to commit and push M12 UI deliverables.

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by user.
