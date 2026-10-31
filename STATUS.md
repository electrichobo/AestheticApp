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
- Built **Desktop UI Shell** (`crates/aesthetic-ui/`):
  - Pure Rust embedded HTTP server + static HTML5/CSS/Canvas frontend.
  - Zero C-compiler / dlltool linking issues on Windows GNU toolchain.
  - Native Edge App Mode chromeless window (`msedge.exe --app=...`) with sub-millisecond scope rendering.
- Built **Web Video Ingest Engine** (`crates/aesthetic-core/src/web_ingest.rs`):
  - Direct URL probing and streaming/download via `yt-dlp` sidecar for YouTube, Vimeo, and web streams.
- Comprehensive testing: **10/10 tests passing** across workspace. Zero clippy warnings.
