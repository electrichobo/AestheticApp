# AESTHETIC — Development Status

## Current Milestone: M7 — Advanced Cinematographic Intelligence
- **Phase**: Ground-Up Rebuild in Rust
- **Target**: Windows x64 (primary), Linux, macOS
- **Active Focus**: Depth-conditioned focus (bokeh MTF), volumetric lighting geometry, ACES split-toning, style-family manifold geodesics.

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
| **M6: Editorial Deliverables & Stills Ingest** | JSON Shot Sidecars, Top-$N$ Breakout & Visual Contact Sheet, Native File Browser, Still Images Baseline Ingest, NLE XML/EDL Round-Trip | ✅ Done | Stills ingest, HTML contact sheets, JSON sidecars, FCPXML & native OS picker |
| **M7: Advanced Cinematographic Intelligence** | Depth-Conditioned Z-Plane Focus (Bokeh MTF), Volumetric Key-Fill & Catchlight Geometry, Split-Toning in ACES/Linear Space, Gaze-Anchored Cinematic Poise, Style-Family Manifold Geodesics | 🔄 In Progress | Learned subjective heads & perceptual optical modeling |

---

## Completed in M6
- **Still Image Baseline Ingestion** (`crates/aesthetic-core/src/baseline_store.rs`):
  - Ingests reference cinema still frames (`.png`, `.jpg`, `.tiff`, `.exr`, `.webp`, `.bmp`) individually or by entire directories.
  - Automatically computes 79 objective physics metrics, vision embeddings, appends to baseline corpus, and dynamically recalibrates empirical quantiles.
- **Editorial Deliverables & Top-$N$ Breakout** (`crates/aesthetic-core/src/export.rs`):
  - **FCPXML Timeline Export**: Final Cut Pro and DaVinci Resolve readable timeline project with source timecode cuts, hero frame markers, and score metadata notes.
  - **Visual HTML Contact Sheet**: Responsive dark-themed grid breakout showcasing top $N$ selects with timecodes, composite score badges, score breakdown bars, style tags, and Master DP banners.
  - **JSON Shot Sidecars**: Exports structured sidecar files at `<dir>/metrics/<take_id>.json` containing full 79 raw measurements, classifications, and scores for zero-redundancy re-scoring.
- **Native OS File & Directory Browser** (`crates/aesthetic-ui/src/main.rs`, `ui/app.js`):
  - Cross-platform native file and folder open dialogs wired into UI buttons ("+ Open Media", "+ Baseline Media") replacing manual path inputs.
  - One-click export buttons in UI header for Contact Sheet, FCPXML, EDL, and CSV.
- **CLI Commands Extended** (`crates/aesthetic-cli/src/main.rs`):
  - `analyze`: `--top <N>`, `--edl <file>`, `--csv <file>`, `--xml <file>`, `--contact-sheet <file>`, `--sidecars <dir>`, `--clips <dir>`.
  - `ingest-baseline`: accepts video files, still images, and directories of stills.
- **Testing & Quality Assurance**:
  - 17/17 tests passing across the workspace. Zero clippy warnings with `-D warnings`. `cargo fmt --check` passes cleanly.

---

## Completed in M7 (So Far)
- **Depth-Conditioned Focus & Bokeh Quality** (`crates/aesthetic-core/src/inference.rs`):
  - `compute_depth_conditioned_focus`: Evaluates high-frequency Laplacian sharpness specifically along the subject depth plane while measuring the smoothness of the background bokeh plane.
  - Generates the `bokeh_separation_ratio`, accurately rewarding shallow depth-of-field cinematography ($f/1.2$, $f/1.4$) without falsely penalizing intentional optical defocus.
- **Volumetric Lighting Geometry** (`crates/aesthetic-core/src/inference.rs`):
  - `compute_volumetric_lighting`: Infers 3D key-light azimuth angle (-90° to +90° horizontal key placement) and elevation angle (10° to 85° top-down modeling) from highlight vs shadow spatial distributions.
  - Automatically calculates physical key-to-fill contrast ratios across candidate frames.
- **Harmonic Complementary Split-Toning** (`crates/aesthetic-metrics/src/color.rs`):
  - `split_toning_separation_deg`: Chromatic angle between highlight and shadow vectors in $Y C_b C_r$ space. Detects and scores complementary color schemes (e.g. orange/teal separation at 140°–180°).
  - `harmonic_palette_score`: Composite palette score rewarding harmonic split-toning balance and controlled color entropy.
- **6 Canonical Style-Family Clusters** (`crates/aesthetic-models/src/baseline.rs`, `crates/aesthetic-core/src/baseline_store.rs`):
  - Dynamic classification across *Chiaroscuro Noir*, *Prestige Naturalism*, *Expressive Color*, *High-Key Symmetrical*, *Documentary Vérité*, and *Atmospheric Immersion*.
  - Surface style-family tags in `DiscoveredStyle`, `MasterMatchResult`, HTML contact sheet, and UI.
- **Testing**:
  - 19/19 tests passing across workspace, zero clippy warnings, rustfmt compliant.
