# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M5 (Desktop Scopes Deck & Inference Engine Complete)
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-cli`, `aesthetic-ui`.
- 5 Broadcast Scopes Deck: Luma Waveform, RGB Parade, Circular Vectorscope (57° I-line), Histograms, CIE 1931 xy Gamut rendered live via HTML5 Canvas.
- Real-Time Scrub & Pipeline: Interactive timeline scrubber wired to frame demuxing, live scope calculations, and 4-output cinematographic matrix updates.
- Inference Engine: Depth-Anything-V2 depth separation & SigLIP 1152-dim vision embeddings with DirectML GPU acceleration and Rayon SIMD fallback.
- Selects & Editorial Export: CMX 3600 EDL generator with SMPTE timecode and CSV selects manifest.
- Frame Demux & Trim: Pipe-based `extract_frame_rgb` and handle-aware clip trimming.
- Web Ingest: Remote URL probing & streaming via `yt-dlp`.
- Standalone CLI: 4K 79-metric pass executes in 1.70s.
- All 14 integration tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (M5: End-to-End Batch Pipeline & Packaging)
1. **End-to-End Batch Ingest**: Wire full video demuxing, transition detection, golden window extraction, model inference, and EDL/CSV selects packaging into a single automated CLI/UI command.
2. **Golden Baseline Corpus Expansion**: Expand reference film signatures (*Skyfall*, *Dune*, *The Piano*, *Blade Runner 2049*).

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
