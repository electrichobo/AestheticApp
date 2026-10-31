# AESTHETIC — Development Status

## Current Milestone: M5 — Desktop UI Shell & Model Inference
- **Phase**: Ground-Up Rebuild in Rust
- **Target**: Windows x64 (primary), Linux, macOS
- **Active Focus**: Desktop UI shell architecture, interactive scopes integration, DirectML vision models.

---

## Milestone Roadmap

| Milestone | Scope | Status | Notes |
| :--- | :--- | :---: | :--- |
| **M0: Protocol & Clean Rebuild** | Protocol initialization, AGENTS.md, HANDOFF.md, purge legacy Python code | ✅ Done | Clean Rust Cargo workspace established |
| **M1: Data Models & Objective Metrics** | `aesthetic-models`, `aesthetic-metrics` (SIMD/rayon exposure, optics, color physics) | ✅ Done | Pure Rust math verified with passing unit tests |
| **M2: Temporal Engine & Windowing** | `aesthetic-core` video probe, transition cut detection, 1.5s-4.0s window optimizer, active matte detection | ✅ Done | 4-Output architecture implemented & tested |
| **M3: Baseline Vector Store & DP Match** | `BaselineStore` vector similarity, master DP fingerprint matching, empirical quantile calibration | ✅ Done | Deakins, Fraser, Dryburgh craft signatures implemented |
| **M4: CLI Driver & Benchmark Harness** | `aesthetic-cli`, 4K SIMD physics benchmark (1.70s 4K pass), demo take evaluation | ✅ Done | Standalone executable verified in debug and release |
| **M5: Desktop UI & Web Ingest** | Web video ingest (yt-dlp), broadcast scopes engine (Waveform, RGB Parade), Desktop UI shell | 🔄 In Progress | Scopes and web ingest complete; UI shell in progress |

---

## Completed in M5 (So Far)
- Built **Broadcast Scopes Suite** (`crates/aesthetic-metrics/src/scopes.rs`):
  - 100-IRE Luma Waveform with square-root density modeling for authentic analog CRT/phosphor glow.
  - 3-channel RGB Parade with isolated color channel density columns.
  - Circular Vectorscope with YUV Cb-Cr polar distribution, graticule bounds, and 57° skin-tone I-line.
  - 256-bucket Channel Histograms (Luma, R, G, B) with peak-normalized curves.
  - CIE 1931 xy Chromaticity Gamut Map with sRGB, DCI-P3, and Rec.2020 triangle overlays.
- Built **Editorial & Selects Export Engine** (`crates/aesthetic-core/src/export.rs`):
  - SMPTE timecode calculation (`seconds_to_smpte_timecode`).
  - CMX 3600 EDL generator with event indexing, source/record timecodes, and metadata tags for DaVinci Resolve, Premiere Pro, and Avid.
  - CSV Selects manifest for spreadsheet and database ingestion.
- Built **Frame Demux & Lossless Sub-clip Extraction** (`crates/aesthetic-core/src/video.rs`):
  - Zero-copy ffmpeg pipe frame extraction (`extract_frame_rgb`).
  - Stream-copy clip trimming with handle clamping (`extract_trimmed_clip`).
- Integrated **Hardware Acceleration Engine** (`crates/aesthetic-core`):
  - Option A approved: `ort` v2.0 with Microsoft DirectML execution provider.
  - Configured with pure dynamic loading (`load-dynamic`) to ensure zero C-compiler/dlltool friction on Windows GNU toolchains while unlocking NVIDIA, AMD/ATI, and Intel GPU acceleration.
- Built **Desktop UI Shell & Interactive Scopes Deck** (`crates/aesthetic-ui/`):
  - Pure Rust embedded HTTP server + static HTML5/CSS/Canvas frontend.
  - Native Edge App Mode chromeless window (`msedge.exe --app=...`) with sub-millisecond scope rendering.
  - Interactive timeline scrubber with live playhead feedback, streaming 5 scopes (Waveform, Parade, Vectorscope, Histogram, CIE 1931) and updating 4-output matrix in real-time.
  - Full support for opening local files (`/api/open_media`), probing remote URLs (`/api/web_probe`), and downloading CMX 3600 EDL and CSV manifests.
- Built **Web Video Ingest Engine** (`crates/aesthetic-core/src/web_ingest.rs`):
  - Direct URL probing and streaming/download via `yt-dlp` sidecar for YouTube, Vimeo, and web streams.
- Comprehensive testing: **12/12 tests passing** across workspace. Zero clippy warnings.
