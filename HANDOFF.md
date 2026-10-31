# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M7 (Advanced Cinematographic Intelligence Complete)
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-cli`, `aesthetic-ui`.
- Depth-Conditioned Focus: `compute_depth_conditioned_focus` evaluates subject-plane MTF sharpness vs background bokeh roll-off ratio.
- Volumetric Lighting & Catchlights: 3D key azimuth, elevation, key-to-fill ratio, and facial specular catchlight detection.
- Gaze-Anchored Staging & Poise: Subject centroid, directional gaze vector, looking room (lead room), thirds alignment, and composite poise score.
- Harmonic Split-Toning: Perceptual chromatic separation angle (140°-180° complementary balance) and palette harmony scoring.
- Style-Family Clusters: 6 canonical aesthetic clusters (Chiaroscuro Noir, Prestige Naturalism, Expressive Color, High-Key Symmetrical, Documentary Vérité, Atmospheric Immersion).
- Editorial Deliverables: Top-$N$ visual contact sheets, JSON sidecars, FCPXML, CMX 3600 EDL, still/video baseline ingestion, native OS dialogs.
- 21/21 tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (Production Packaging & DirectML Acceleration)
1. **DirectML Acceleration Option**: Profile DirectML on Windows vs Rayon SIMD CPU on 4K/8K media.
2. **End-to-End Media Ingest Test**: Run sample video and still directory through `aesthetic-cli analyze` and inspect exported selects.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
