# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M6 (Editorial Deliverables & Golden Baseline Stills Ingest Complete)
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-cli`, `aesthetic-ui`.
- Still Image Baseline Ingestion: `ingest_reference_still` and `ingest_reference_directory` for `.png`, `.jpg`, `.tiff`, `.exr`.
- Editorial Deliverables: JSON shot sidecars (`<dir>/metrics/*.json`), Top-$N$ visual HTML contact sheet, FCPXML and CMX 3600 EDL timeline exports.
- Native File/Folder Browser: Native OS file/directory dialogs wired into `aesthetic-ui`.
- 17/17 tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (M7 Depth-Conditioned Focus & Style Geodesics)
1. **Depth-Conditioned Focus**: Sharpness evaluation conditioned on subject depth plane vs background bokeh roll-off.
2. **Volumetric Lighting**: Key-to-fill modeling ratio and specular catchlight geometry.
3. **Style-Family Clusters**: Segment baseline into style families for within-genre grading comparison.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
