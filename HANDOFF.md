# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M5 (Broadcast Scopes, Export, Desktop UI & DirectML Complete)
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-cli`, `aesthetic-ui`.
- 5 Broadcast Scopes: Luma Waveform (100 IRE), RGB Parade, Circular Vectorscope (Cb-Cr + I-line), Channel Histograms, CIE 1931 xy Gamut.
- Hardware Acceleration: Option A (`ort` with DirectML dynamic loading) approved and integrated for NVIDIA, AMD/ATI, Intel GPUs.
- Selects & Editorial Export: CMX 3600 EDL generator with SMPTE timecode and CSV selects manifest.
- Frame Demux & Trim: Pipe-based `extract_frame_rgb` and handle-aware lossless clip trimming.
- Desktop UI shell: Embedded TCP/HTTP server + HTML5 Canvas frontend launched in native Edge App Mode (zero C-compiler/dlltool friction).
- Web ingest: Remote URL probing & streaming via `yt-dlp`.
- Standalone CLI verified: 4K 79-metric pass executes in 1.70s.
- All 12 integration tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (M5: UI Timeline Scrubbing & Inference Wiring)
1. **Video Pipeline Wire-up**: Connect file dialog & timeline scrubbing to video frame extraction and live scope broadcast in `aesthetic-ui`.
2. **Craft Layer Model Execution**: Wire ONNX model session runners for Depth-Anything-V2 and SigLIP vision embeddings via DirectML.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
