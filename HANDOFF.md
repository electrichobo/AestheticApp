# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M5 (Desktop Scopes Deck & Timeline Scrubbing Complete)
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-cli`, `aesthetic-ui`.
- 5 Broadcast Scopes Deck: Luma Waveform, RGB Parade, Circular Vectorscope (57° I-line), Histograms, CIE 1931 xy Gamut rendered live via HTML5 Canvas.
- Real-Time Scrub & Pipeline: Interactive timeline scrubber wired to frame demuxing, live scope calculations, and 4-output cinematographic matrix updates.
- Hardware Acceleration: Option A (`ort` DirectML dynamic loading) integrated for NVIDIA, AMD/ATI, Intel GPUs.
- Selects & Editorial Export: CMX 3600 EDL generator with SMPTE timecode and CSV selects manifest.
- Frame Demux & Trim: Pipe-based `extract_frame_rgb` and handle-aware clip trimming.
- Web Ingest: Remote URL probing & streaming via `yt-dlp`.
- Standalone CLI: 4K 79-metric pass executes in 1.70s.
- All 12 integration tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (M5: Depth & Style Embedding Inference Session)
1. **Model Session Runner**: Create ONNX session runner in `aesthetic-core` loading Depth-Anything-V2 (depth map) and SigLIP (1152-dim visual embeddings) with DirectML execution provider.
2. **End-to-End Batch Pipeline**: Connect video demuxing, golden window extraction, model inference, and EDL export in the UI and CLI.

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
