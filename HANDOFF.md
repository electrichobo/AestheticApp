# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M7 (Depth-Conditioned Focus & Volumetric Lighting Complete)
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-cli`, `aesthetic-ui`.
- Depth-Conditioned Focus: `compute_depth_conditioned_focus` evaluates subject-plane MTF sharpness vs background bokeh roll-off ratio.
- Volumetric Lighting: Inferred 3D key light azimuth, elevation angle, and key-to-fill modeling ratio from spatial highlight/shadow distribution.
- Editorial Deliverables: Top-$N$ visual contact sheets, JSON sidecars, FCPXML, CMX 3600 EDL, still/video baseline ingestion, native OS dialogs.
- 18/18 tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (M7 Style-Family Clusters & ACES Gamut)
1. **Style-Family Clusters**: Segment 58 master baseline into distinct style families (Noir, Naturalism, Pastel, Technicolor, Vérité).
2. **ACES / Linear Gamut Volume**: Measure harmonic complementary split-toning in perceptual color space.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
