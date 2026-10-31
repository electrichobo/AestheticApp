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
| **M7: Advanced Cinematographic Intelligence** | Depth-Conditioned Z-Plane Focus (Bokeh MTF), Volumetric Key-Fill & Catchlight Geometry, Split-Toning in ACES/Linear Space, Gaze-Anchored Cinematic Poise, Style-Family Manifold Geodesics | ✅ Done | Subject/bokeh MTF, catchlights, gaze vectors, looking room, ACES split-toning & 6 style clusters |

---

## Completed in M7
- **Depth-Conditioned Focus & Bokeh Quality** (`crates/aesthetic-core/src/inference.rs`):
  - `compute_depth_conditioned_focus`: Evaluates high-frequency Laplacian sharpness specifically along the subject depth plane while measuring the smoothness of the background bokeh plane.
  - Generates the `bokeh_separation_ratio`, accurately rewarding shallow depth-of-field cinematography ($f/1.2$, $f/1.4$) without falsely penalizing intentional optical defocus.
- **Volumetric Lighting & Catchlight Geometry** (`crates/aesthetic-core/src/inference.rs`):
  - `compute_volumetric_lighting`: Infers 3D key-light azimuth angle (-90° to +90° horizontal key placement) and elevation angle (10° to 85° top-down modeling) from highlight vs shadow spatial distributions.
  - Automatically calculates physical key-to-fill contrast ratios across candidate frames.
  - Detects specular catchlight micro-peaks in upper 70% facial envelope, measuring `catchlight_intensity` to evaluate lifelike reflections in the subject's eyes.
- **Gaze-Anchored Cinematic Poise & Looking Room** (`crates/aesthetic-core/src/inference.rs`):
  - `infer_gaze_and_staging`: Evaluates subject centroid $(C_x, C_y)$ from foreground depth clusters, directional gaze vectors $(G_x, G_y)$ from facial luminance/chrominance gradient asymmetry, looking room score (rewarding breathing space in the look direction, penalizing short-siding), eyeline vertical elevation on rule-of-thirds ($y \approx 0.333$), and composite `gaze_poise_score`.
- **Harmonic Complementary Split-Toning** (`crates/aesthetic-metrics/src/color.rs`):
  - `split_toning_separation_deg`: Chromatic angle between highlight and shadow vectors in $Y C_b C_r$ space. Detects and scores complementary color schemes (e.g. orange/teal separation at 140°–180°).
  - `harmonic_palette_score`: Composite palette score rewarding harmonic split-toning balance and controlled color entropy.
- **6 Canonical Style-Family Clusters** (`crates/aesthetic-models/src/baseline.rs`, `crates/aesthetic-core/src/baseline_store.rs`):
  - Dynamic classification across *Chiaroscuro Noir*, *Prestige Naturalism*, *Expressive Color*, *High-Key Symmetrical*, *Documentary Vérité*, and *Atmospheric Immersion*.
  - Surface style-family tags in `DiscoveredStyle`, `MasterMatchResult`, HTML contact sheet, and UI.
- **Holistic 3-Pillar Scoring Fusion** (`crates/aesthetic-core/src/pipeline.rs`):
  - Dynamically synthesizes objective technical measurements, deep craft inference (depth separation, silhouette clarity, gaze poise, looking room, volumetric key-to-fill, catchlight presence, color harmony, and master DP manifold distance), and temporal continuity.
- **Testing**:
  - 21/21 tests passing across workspace, zero clippy warnings, rustfmt compliant.
