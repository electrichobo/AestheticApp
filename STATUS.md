# AESTHETIC — Development Status

## Current Milestone: M11 — Cinematography Awards Registry & Media Server Ingestion
- **Phase**: Ground-Up Rebuild in Rust
- **Target**: Windows x64 (primary), Linux, macOS
- **Active Focus**: 184 Oscar, ASC, and BSC award-winning & landmark films (1995–2025+), continuous shot-boundary segmentation (cut-isolated setups), and Unraid network media server scanner (`M:\movies`).

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
| **M8: Scoring Matrix & DP Comparison UI** | Side-by-Side Master DP Diagnostic Table, Empirical Improvement Action Cards, Port Binding Configuration, Craft Benchmark Integration | ✅ Done | Desktop UI diagnostic table, dynamic improvement recommendations & 4K craft benchmarks |
| **M9: EL Zone & Pretrained Baseline** | Ed Lachman, ASC EL Zone 10-stop calibrated false color, 174 pretrained master shots across 58 films, Stage 1/2 UI groundwork | ✅ Done | Industry standard stop false color and out-of-the-box pre-trained baseline corpus |
| **M10: Showreel Assembly & Forensic Overlays** | Stage 1 candidate selects bin, interactive In/Out handle trimming, Stage 2 real-time diagnostic viewport modes (EL Zone, Peaking, 3D Light, Eyeline/Gaze) | ✅ Done | Dynamic showreel assembly & forensic camera intelligence active in UI |
| **M11: Awards Registry & Media Server Ingestion** | 184 Oscar, ASC, BSC & Landmark titles registry, shot-boundary segmentation (cut-isolated setups), single-pass burst extraction, media server scanner with deduplication & GUI force toggle, optical flow motion dynamics | ✅ Done | Scanning `M:\movies` matching 55 award films with continuous setup extraction, motion dynamics & GUI controls |

---

## Completed in M11
- **Cinematography Awards Registry (1995 – 2025+)** (`crates/aesthetic-models/src/awards.rs`):
  - Catalog of 184 award-recognized and landmark films covering Best Cinematography Oscar, ASC, and BSC winners/nominees plus historical masterworks.
  - Robust fuzzy title and year matching function (`find_award_match`) accounting for punctuation, case, and subtitle variances.
  - Exposed via CLI `aesthetic-cli awards-list`.
- **Continuous Shot Segmentation & Optical Flow** (`crates/aesthetic-core/src/inference.rs`, `crates/aesthetic-core/src/baseline_store.rs`, `crates/aesthetic-core/src/video.rs`):
  - `extract_frames_burst`: Single-pass frame burst extraction with in-memory PPM parsing supporting both 8-bit SDR and 16-bit HDR (`rgb48be` big-endian). Reduces network seeks from 3 round-trips to 1 per candidate timestamp.
  - `compute_motion_dynamics`: Multi-threaded block matching computing true optical flow velocity, velocity standard deviation, camera-to-subject motion ratio, micro-jitter, and judder risk.
  - `ingest_reference_film_shots`: Detects edit boundaries and transition cuts, discarding transition frames and isolating clean continuous camera setups with sliding search window.
  - Optical flow motion dynamics (`motion_optical_flow`, `camera_motion_ratio`) calculated and stored directly on `ReferenceShot` baseline vectors.
- **Network Media Server Scanner & Deduplication** (`crates/aesthetic-cli/src/main.rs`, `crates/aesthetic-core/src/baseline_store.rs`):
  - `aesthetic-cli ingest-server <dir>`: Scans library folders (e.g. `M:\movies`), matches award titles, parses primary video files, and executes shot-separated ingestion into `BaselineStore`.
  - Automatic Deduplication: Detects and skips already-ingested films in `assets/baseline/manifest.json`. Added `--force` flag to re-extract on demand.
  - Verified live against `M:\movies`: matched 55 award films and successfully ingested reference camera setups across 4K HEVC and master film scans into `assets/baseline/`.
- **Desktop UI Server Ingest Controls** (`crates/aesthetic-ui/ui/index.html`, `ui/app.js`, `src/main.rs`):
  - Added `+ Server Ingest` button in the header and interactive modal with library path, batch limits, and a **"Force Re-Ingest" checkbox** to bypass deduplication on demand.
  - `/api/ingest_server` endpoint executes scanning in the core engine and returns live JSON status.
- **Testing**:
  - 24/24 tests passing across workspace, zero clippy warnings, rustfmt compliant.

---

## Completed in M10
- **Stage 1: In-App Showreel Assembly** (`crates/aesthetic-ui/ui/app.css`, `ui/app.js`):
  - Dynamic candidate selects bin populated from `/api/selects` with hero select tags, candidate badges, defect alerts, and matched Master DP style signatures.
  - Interactive scrubbing: clicking any candidate take immediately scrubs timeline to hero timestamp and snaps In/Out markers to optimal window bounds.
  - Drag-and-trim In/Out timeline handles (`#in-handle`, `#out-handle`) with real-time SMPTE timecode window readout and duration tracking.
  - Media ingest flow: file browser triggering background `/api/analyze` video intelligence pass.
  - One-click export packaging for CMX 3600 EDL, FCPXML, CSV selects, and HTML contact sheets.
- **Stage 2: Real-Time Forensic Overlays & EL Zone** (`crates/aesthetic-ui/ui/app.css`, `ui/app.js`):
  - Five-state viewport diagnostic mode selector: `Picture`, `EL Zone`, `Peaking`, `3D Light`, `Eyeline & Gaze`.
  - Ed Lachman, ASC EL Zone false color heatmap overlaid directly on video player with 11-chip photographic stops legend bar docked at viewport bottom.
  - Depth-conditioned focus peaking overlay highlighting sharp in-focus planes.
  - Dynamic 3D Volumetric Light compass: renders key-light azimuth angle ray, elevation arc, key-to-fill ratio badge, and specular catchlight reflection index.
  - Dynamic Eyeline & Directional Gaze HUD: renders rule-of-thirds golden composition grid, subject eye anchor reticle, directional gaze arrow vector, and looking room poise score.
- **Verification**:
  - 22/22 tests passing across workspace, zero clippy warnings, rustfmt compliant.
  - Verified `/`, `/logo_wide.png`, `/api/selects`, `/api/frame_el_zone`, `/api/frame_peaking`, and `/api/evaluate` endpoints returning 200 OK.

---

## Completed in M9
- **Ed Lachman, ASC EL Zone System** (`crates/aesthetic-models/src/physics.rs`, `crates/aesthetic-metrics/src/exposure.rs`):
  - Calibrated 10-zone false color heatmap based on 18% Middle Gray (Zone V = 0 EV).
  - Stop calculations for Rec.709 gamma transfer function: Zones 0 through X (black, deep purple, medium blue, cyan, olive green, neutral gray, light khaki, yellow, orange, red, magenta).
  - Distribution breakdown tracked across `ExposurePhysics.el_zones`.
- **Pretrained Shipped Baseline Corpus** (`crates/aesthetic-core/src/baseline_store.rs`):
  - Automatic ingestion of 174 reference shots across 58 award-winning films during initialization.
  - Pre-calibrates empirical dynamic range, roll-off, key-to-fill, and color harmony quantiles so the application ships fully calibrated out of the box.
- **Brand Assets & Diagnostic Toolbar** (`crates/aesthetic-ui/src/main.rs`, `crates/aesthetic-ui/ui/index.html`):
  - Integrated wide branding header and viewport diagnostic toolbar buttons (Picture, EL Zone, Peaking, 3D Light, Eyeline & Gaze).
  - Embedded EL Zone stop legend bar.
- **Testing**:
  - 22/22 tests passing across workspace, zero clippy warnings, rustfmt compliant.

---

## Completed in M8
- **Master DP Side-by-Side Diagnostic Comparison** (`crates/aesthetic-ui/ui/index.html`, `ui/app.js`, `src/main.rs`):
  - Real-time side-by-side comparison table between the current take and matched Master DP target baseline.
  - Compares Dynamic Range stops, Highlight Roll-Off %, Key-to-Fill Contrast, Split-Toning chromatic angle, Gaze Staging Poise, and Eye Catchlight presence.
- **Forensic Improvement Action Cards** (`crates/aesthetic-ui/src/main.rs`, `ui/app.js`):
  - Generates concrete, empirical recommendations across Lighting, Latitude, Highlight Diffusion, Eyeline Staging, Catchlights, and Color Harmony.
- **Benchmark & Architecture Profiling** (`crates/aesthetic-cli/src/main.rs`):
  - Reports inference architecture (Rayon SIMD CPU vs DirectML GPU).
  - Benchmarks 4K frame physics (1.73s), 4K monocular depth & craft inference (45ms), and 5,000-shot vector search (1.31ms).
- **Testing**:
  - 21/21 tests passing across workspace, zero clippy warnings, rustfmt compliant.

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
