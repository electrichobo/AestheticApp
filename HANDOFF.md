# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M7 (Style Families, Split-Toning & Volumetric Lighting Complete)
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-cli`, `aesthetic-ui`.
- Depth-Conditioned Focus: `compute_depth_conditioned_focus` evaluates subject-plane MTF sharpness vs background bokeh roll-off ratio.
- Volumetric Lighting: Inferred 3D key light azimuth, elevation angle, and key-to-fill modeling ratio from spatial highlight/shadow distribution.
- Harmonic Split-Toning: Perceptual chromatic separation angle (140°-180° complementary balance) and palette harmony scoring.
- Style-Family Clusters: 6 canonical aesthetic clusters (Chiaroscuro Noir, Prestige Naturalism, Expressive Color, High-Key Symmetrical, Documentary Vérité, Atmospheric Immersion).
- Editorial Deliverables: Top-$N$ visual contact sheets, JSON sidecars, FCPXML, CMX 3600 EDL, still/video baseline ingestion, native OS dialogs.
- 19/19 tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (M7 Release Builds & End-to-End Verification)
1. **Commit & Push M7 Progress**: Commit uncommitted changes per user request.
2. **Release Build Verification**: Build optimized binaries (`cargo build --release -p aesthetic-cli -p aesthetic-ui`).
3. **End-to-End Media Test**: Verify CLI analysis against real reference media with contact sheet, FCPXML, and JSON sidecars.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
