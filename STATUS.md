# AESTHETIC — Development Status

## Current Milestone: M6 — Editorial Deliverables & Golden Baseline Stills Ingest
- **Phase**: Ground-Up Rebuild in Rust
- **Target**: Windows x64 (primary), Linux, macOS
- **Active Focus**: JSON shot sidecars, Top-$N$ visual contact sheets, native browsable file dialogs, still image baseline ingestion, NLE XML/EDL round-trip.

---

## Milestone Roadmap

| Milestone | Scope | Status | Notes |
| :--- | :--- | :---: | :--- |
| **M0: Protocol & Clean Rebuild** | Protocol initialization, AGENTS.md, HANDOFF.md, purge legacy Python code | ✅ Done | Clean Rust Cargo workspace established |
| **M1: Data Models & Objective Metrics** | `aesthetic-models`, `aesthetic-metrics` (SIMD/rayon exposure, optics, color physics) | ✅ Done | Pure Rust math verified with passing unit tests |
| **M2: Temporal Engine & Windowing** | `aesthetic-core` video probe, transition cut detection, 1.5s-4.0s window optimizer, active matte detection | ✅ Done | 4-Output architecture implemented & tested |
| **M3: Baseline Vector Store & DP Match** | `BaselineStore` vector similarity, master DP fingerprint matching, empirical quantile calibration | ✅ Done | 58 Master DP craft signatures active |
| **M4: CLI Driver & Benchmark Harness** | `aesthetic-cli`, 4K SIMD physics benchmark (1.70s 4K pass), demo take evaluation | ✅ Done | Standalone executable verified in debug and release |
| **M5: Desktop UI, Scopes & Release** | 5 Broadcast Scopes, CMX 3600 EDL/CSV Export, Desktop UI Shell, DirectML Acceleration | ✅ Done | Release binaries verified (`aesthetic-cli`, `aesthetic-ui`) |
| **M6: Editorial Deliverables & Stills Ingest** | JSON Shot Sidecars, Top-$N$ Breakout & Visual Contact Sheet, Native File Browser, Still Images Baseline Ingest, NLE XML/EDL Round-Trip | 🔄 In Progress | Delivering core showreel and curation workflows |
| **M7: Advanced Cinematographic Intelligence** | Depth-Conditioned Z-Plane Focus (Bokeh MTF), Volumetric Key-Fill & Catchlight Geometry, Split-Toning in ACES/Linear Space, Gaze-Anchored Cinematic Poise, Style-Family Manifold Geodesics | 🔮 Planned | Learned subjective heads & perceptual optical modeling |

---

## Completed in M5
- **5-Scope Broadcast Deck** (`crates/aesthetic-metrics/src/scopes.rs`):
  - 100-IRE Luma Waveform with square-root density phosphor modeling.
  - 3-channel isolated RGB Parade.
  - Circular Vectorscope with YUV Cb-Cr polar distribution and 57° skin-tone I-line.
  - 256-bucket Channel Histograms (Luma, R, G, B) with peak-normalized curves.
  - CIE 1931 xy Chromaticity Gamut Map with sRGB, DCI-P3, and Rec.2020 triangle overlays.
- **Editorial & Selects Export Engine** (`crates/aesthetic-core/src/export.rs`):
  - SMPTE timecode calculation (`seconds_to_smpte_timecode`).
  - CMX 3600 EDL generator with event indexing and source/record timecodes.
  - CSV Selects manifest for spreadsheet and database ingestion.
- **Hardware Acceleration Engine** (`crates/aesthetic-core`):
  - Option A approved: `ort` v2.0 with Microsoft DirectML execution provider.
  - Pure dynamic loading (`load-dynamic`) ensuring zero GNU/C-linking friction and vendor-agnostic GPU acceleration (NVIDIA, AMD/ATI, Intel).
- **Desktop UI Shell** (`crates/aesthetic-ui/`):
  - Pure Rust embedded HTTP server + static HTML5/CSS/Canvas frontend.
  - Native Edge App Mode chromeless window (`msedge.exe --app=...`) with sub-millisecond scope rendering.
  - Interactive timeline scrubber with live playhead feedback, streaming 5 scopes and updating 4-output matrix in real-time.
- **58 Master Cinematographer Signatures** (`crates/aesthetic-core/src/baseline_store.rs`):
  - Calibrated visual signatures covering 58 legendary masters across all lighting paradigms and visual families.
- **Automated Baseline Ingest & Recalibration** (`crates/aesthetic-core/src/baseline_store.rs`):
  - `ingest_reference_film` and CLI `aesthetic-cli ingest-baseline <file>`: Ingests reference cinema films, runs 79-metric physics and vision embeddings, and continuously recalibrates empirical quantiles across the entire corpus.
- **Optimized Release Packaging**:
  - `aesthetic-cli.exe` (7.4MB) and `aesthetic-ui.exe` (7.5MB) verified with 1.70s 4K physics pass and 1.30ms vector search across 5,000 shots.
- **Comprehensive Testing**:
  - 16/16 tests passing, zero clippy warnings, rustfmt compliant.

---

## Active Focus (M6: Editorial Deliverables & Golden Baseline Stills Ingest)
1. **Shot Sidecars**: Structured JSON sidecar persistence at `jobs/<job_id>/metrics/<shot_id>.json` caching all 79 metrics and model embeddings.
2. **Top-$N$ Contact Sheet & Hero Stills**: Exportable HTML contact sheet and high-resolution PNG collage grid showcasing top $N$ selects with score badges and master DP matches.
3. **Still Image Ingestion for Golden Baseline**: Direct ingestion of `.png`, `.jpg`, `.tiff`, and `.exr` stills to expand reference cinema profiles without needing full video files.
4. **Native Cross-Platform File & Folder Browser**: Native open dialogs on Windows, macOS, and Linux for seamless media browsing.
5. **NLE Timeline Round-Trip**: CMX 3600 EDL + FCPXML / DaVinci Resolve timeline export.
