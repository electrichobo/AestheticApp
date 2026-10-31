# AESTHETIC — Development Handoff

## Repository & State
- **Repository**: electrichobo/AestheticApp @ `main`
- **Architecture**: Rust Core Engine (Ground-Up Rebuild)
- **Active Target**: Windows x64 (Live Production Environment)

---

## Current Status: M3 & M4 Complete → M5 In Progress
- Protocol initialized: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `START_HERE.md`, `STATUS.md`.
- Workspace crates complete: `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-cli`.
- 4-Output architecture operational: Tangible 0-100 scores, auto style discovery, raw 79 physics metrics, technical concerns.
- Golden Baseline store: Multi-threaded vector search, empirical quantile calibration, master DP fingerprint matching.
- Standalone CLI verified: 4K 79-metric pass executes in 1.70s (`target\release\aesthetic-cli.exe benchmark`).
- All 9 integration tests passing, zero clippy warnings, rustfmt compliant.

---

## Next Immediate Step (M5: Desktop UI & DirectML Inference)
1. **GPU Acceleration**: Request crate approval for DirectML / ONNX tensor execution on Windows.
2. **Desktop UI Integration**: Plan and scaffold high-performance UI shell with real-time waveform, RGB parade, and CIE 1931 scopes.
3. **Web Ingest Integration**: Wire `yt-dlp` stream extraction for web URLs (YouTube, Vimeo).

---

## Safety & Invariants
- Live production machine: never install software/services/Docker; no system changes.
- Never add a crate without explicit user approval.
- Keep `HANDOFF.md` under 50 lines; `AGENTS.md` under 12,000 characters.
- Commit/push only when requested by the user.
