# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M5 (Broadcast Scopes & Desktop UI Complete)
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-cli`, `aesthetic-ui`.
- 5 Broadcast Scopes: Luma Waveform (100 IRE), RGB Parade, Circular Vectorscope (Cb-Cr + I-line), Channel Histograms, CIE 1931 xy Gamut.
- Desktop UI shell: Embedded TCP/HTTP server + HTML5 Canvas frontend launched in native Edge App Mode (zero C-compiler/dlltool friction).
- Web ingest: Remote URL probing & streaming via `yt-dlp`.
- Standalone CLI verified: 4K 79-metric pass executes in 1.70s.
- All 10 integration tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (M5: GPU Inference & Video Pipeline)
1. **GPU Acceleration**: Request crate approval for DirectML / ONNX tensor execution across NVIDIA, AMD/ATI, Intel on Windows.
2. **Video Pipeline Wire-up**: Connect file dialog & timeline scrubbing to video frame extraction and live scope broadcast.
3. **Selects & Reel Export**: CMX 3600 EDL, CSV selects list, and trimmed video clip export with configurable handles.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
