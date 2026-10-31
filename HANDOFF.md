# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M6 (Editorial Deliverables & Golden Baseline Stills Ingest)
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-cli`, `aesthetic-ui`.
- 58 Master DP Signatures active in `BaselineStore` with dynamic empirical quantiles.
- 5 Broadcast Scopes Deck: Luma Waveform, RGB Parade, Vectorscope (57° I-line), Histograms, CIE 1931 xy Gamut.
- End-to-End Batch Pipeline & DirectML hardware acceleration verified in release builds.
- 16/16 tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (M6 Implementation)
1. **Still Image Ingestion for Golden Baseline**: Ingest `.png`/`.jpg`/`.tiff`/`.exr` reference stills into `BaselineStore`.
2. **Shot Sidecars & Top-$N$ Contact Sheet**: Export `jobs/<job_id>/metrics/<shot_id>.json` sidecars and HTML/PNG contact sheet collage.
3. **Native File & Folder Browser**: Add native file picker dialogs to `aesthetic-ui` for finished media & stills.
4. **NLE Timeline Round-Trip**: CMX 3600 EDL + FCPXML/Resolve XML exports.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
