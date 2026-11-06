# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M20–M28 Complete + FFmpeg Inclusion Hardened
- **FFmpeg Inclusion & Multi-Tier Discovery**:
  - Implemented multi-tier binary resolution in `aesthetic_core::video`: custom env vars (`AESTHETIC_FFMPEG_PATH`, `FFMPEG_PATH`), CWD + ancestor hierarchy traversal, running executable adjacent directory (`target/release/ffmpeg.exe`, `target/debug/ffmpeg.exe`), and canonical workspace path fallback.
  - Added zero-dependency `build.rs` to `aesthetic-ui` and `aesthetic-cli` to automatically copy `tools/ffmpeg.exe` adjacent to built executables.
- **M24–M28**: Live Resolve Studio bridge, batch queue processing, smart showreel composer modal, and adaptive taste profile calibration.
- **Golden Baseline**: 1,112 real measured reference shots across 199 award-winning films (`manifest.json` v2.0.0-measured, 0 synthetic seeds).
- **Quality**: Workspace tests passing (27 tests), zero clippy warnings (`-D warnings`).

---

## Next Immediate Step
1. **Production Operation**: Launch `aesthetic-ui` or run batch analysis on production folders (`aesthetic-cli batch`).

---

## Safety & Invariants
- Live production machine: zero system alterations; no unapproved crates.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- User granted permission to commit/push when md files are updated/current.
