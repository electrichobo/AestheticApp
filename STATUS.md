# AESTHETIC — Development Status

## Current Milestone: M24–M28 — Live Resolve IPC Bridge, Batch Queue, Smart Showreel Composer & UI Modal, Personal Taste Tuning
- **Phase**: Ground-Up Rebuild in Rust
- **Target**: Windows x64 (primary), Linux, macOS
- **Active Focus**: Live DaVinci Resolve Studio IPC bridge (`send_to_live_resolve`), multi-video directory queue (`analyze_folder_queue`), smart showreel duration & pacing optimizer (`compose_smart_showreel`), interactive desktop Smart Reel modal (`#composer-modal`), and personalized aesthetic profile tuning (`compute_personal_taste_profile`).

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
| **M12: Desktop UI, Scopes & Visual Æesthetic Overhaul** | Zero-scroll UI, decoded frame/thumbnail endpoints, broadcast scopes from active playhead, unified "Visual Æesthetic" window, capped 100% similarity, non-judgmental deltas, pop-out contact sheet with collapsible metrics trees & sidecar metadata, resizable floating panels, Import/Export dropdowns | ✅ Done | Polished broadcast-grade desktop shell with real image output and objective benchmarking |
| **M13: 760-Shot Measured Golden Baseline & Cut-Aware Segmentation** | Full 55-film media server ingest + 92 multi-shot web still galleries (`film-grab.com`, `shot.cafe`, `frameset.app`) = 760 real measured shots across 135 award films, cut-aware 3-frame burst & same-setup deduplication, mean-centered spatial+craft reference matching, lossless PNG sidecars | ✅ Done | 100% pixel-measured Golden Baseline (`n=760`, 0 synthetic seeds) verified against real test footage |
| **M14–M17: Continuity, Style-Cluster Quantiles, Forensics & Cached Rescore** | `ReelSequenceMetrics` (cross-scene WB/Kelvin/Luma continuity, visual fatigue, MMR reel diversity), Log/HDR transfer detection, within-style-cluster & motion baseline percentiles, subtitle/flicker/rolling-shutter forensics, and instant cached sidecar re-scoring (`aesthetic-cli rescore`) | ✅ Done | 26/26 workspace tests passing; cached 12-take rescore completes in ~240ms |
| **M18: Narrative & Aesthetic Reranker Heads, Log-Aware Gamut & Sequence Banner** | `hero_potency_score`, `three_second_impact_score`, `authorship_distinctiveness_score` in `PillarScores`, log-aware CIE 1931 gamut integration (`gamut_coverage_srgb`/`p3`) into `color_harmony`, and Sequence & Reel Continuity Intelligence banner in HTML contact sheets | ✅ Done | Full 61-metric contact sheet + sequence banner + JSON sidecar export verified |
| **M19: Complete 6-Head Rerankers, Motion Coherence, Palette Family & Feedback Learning** | `storytelling_score`, `cinematic_technique_score`, `memorability_score`, `palette_family`, `scene_type`, `shot_intent`, `motion_blur_angle_deg`, `motion_coherence_score`, Desktop UI Contact Sheet integration, and `SelectFeedbackEvent` preference learning (`assets/feedback/events.jsonl`) | ✅ Done | Complete metric taxonomy active across CLI, sidecars, HTML & Desktop UI |
| **M20: Cinematographic Rationale Engine & Full-Reference PSNR/SSIM QC Pack** | Deterministic local DP & Editorial rationale paragraph (`rationale_summary`) and consecutive frame-pair `psnr_db` & Wang-Bovik $8\times 8$ `ssim_score` (`compute_frame_pair_psnr_and_ssim`) | ✅ Done | Zero-API local rationale generation and full-reference burst QC integrated into sidecars & HTML |
| **M21: Interactive Desktop UI Curation Controls & Cached Sidecars Loader** | One-click `[★ Promote Hero]`, `[📌 Pin Select]`, and `[✕ Deprioritize]` buttons in Contact Sheet modal with live MMR re-ranking + `"Open Cached Sidecars Folder"` in Import menu | ✅ Done | Instant UI re-ranking and cached sidecar folder loading without video re-decoding |
| **M22: Direct DaVinci Resolve Timeline & Marker Bridge** | `generate_resolve_timeline_script` producing a `DaVinciResolveScript` `.py` script creating an `AESTHETIC_Hero_Selects` timeline with color-coded rationale & forensic markers (`--resolve` & UI export) | ✅ Done | Frame-accurate Resolve timeline assembly with Yellow/Blue/Red markers verified |
| **M23: Expanded 1,112-Shot Golden Baseline Across 199 Award-Winning Films** | Ingested 67 additional multi-shot still collections (402 full-res stills) from `film-grab.com`, expanding `assets/baseline/` to 1,112 real measured shots across 199 award-winning films | ✅ Done | `manifest.json` (`n=1112`, 199 films, 0 synthetic seeds) reconciled and verified |
| **M24: Direct Live DaVinci Resolve Studio IPC Bridge** | `send_to_live_resolve` executing one-click timeline and marker construction directly into running DaVinci Resolve Studio (`--live-resolve`, UI button, `/api/send_to_resolve`) | ✅ Done | Zero-terminal live Resolve Studio round-trip assembly |
| **M25: Batch Folder Video Queue & Progressive Sidecars** | `analyze_folder_queue` batch analyzing entire production directories (e.g. series seasons, dailies) with per-file sidecars & contact sheets (`batch <dir>`, UI folder queue) | ✅ Done | Automated multi-video processing across full episode folders |
| **M26: Smart Showreel Composer & Target Duration Assembly** | `compose_smart_showreel` optimization engine assembling curated reels to target durations (60s, 90s, 120s) with shot-scale alternating rhythm & CCT continuity | ✅ Done | Objective-driven showreel assembly (Commercial, Dramatic, Kinetic, Balanced) |
| **M27: Personal Taste Profile & Feedback Reranker Tuning** | `compute_personal_taste_profile` dynamically calibrating personal DP style affinities and reranker head weights from user curation feedback events (`/api/taste_profile`) | ✅ Done | Self-tuning aesthetic layer learning directly from cinematographer curation actions |
| **M28: Interactive Smart Showreel Composer Modal & Pacing Grid** | Desktop UI Smart Reel modal (`#composer-modal`), target duration optimizer (30s/60s/90s/120s), objective filtering, and alternating cut list readout (`/api/compose_showreel`) | ✅ Done | Instant visual showreel sequence generation directly in desktop shell |

---

## Completed in M24–M28 + Scopes Overhaul & FFmpeg Hardening
- **Vectorscope Broadcast Zoom & Inclusive Multi-Ethnic Skin Tone Cone** (`crates/aesthetic-metrics/src/scopes.rs`, `crates/aesthetic-ui/ui/app.js`):
  - Added 2.5× broadcast chroma gain so natural cinematic tones extend legibly outward across the graticule.
  - Implemented interactive canvas click-to-cycle vectorscope zoom: `1.0×`, `2.0×`, `2.5×`, and `4.0×`.
  - Expanded traditional single I-line into an inclusive **Skin Tone Cone** from 48° to 66° covering Fitzpatrick I–VI melanin & hemoglobin spectrums, with graduation markers along the 57° reference line.
- **Bulletproof FFmpeg Inclusion & Path Resolution** (`crates/aesthetic-core/src/video.rs`, `crates/aesthetic-ui/src/main.rs`, `crates/aesthetic-ui/ui/app.js`):
  - Made `find_binary` return clean, absolute canonicalized paths (Windows `\\?\` UNC prefix stripped).
  - Search order prioritizes executable-adjacent (`target/release/ffmpeg.exe`), running binary ancestor walk, hardcoded workspace root (`E:\Antigravity\aesthetic\tools\ffmpeg.exe`), and system PATH via `where.exe`.
  - Added automatic quote and whitespace stripping (`clean_user_path_str`) across backend routes (`/api/open_media`, `/api/analyze`, `/api/batch_folder`, `/api/rescore_sidecars`) and frontend prompt dialogs.
- **Multi-Threaded Server & In-Memory Frame Cache** (`crates/aesthetic-ui/src/main.rs`, `crates/aesthetic-core/src/export.rs`):
  - Replaced single-threaded blocking HTTP listener with per-connection worker threads (`thread::spawn`), preventing request queuing and browser connection timeouts.
  - Added `cached_frames` in-memory LRU-style cache, serving companion PNG thumbnails in 0.1ms without touching FFmpeg.
  - Recursive sidecar discovery discovers all JSON sidecars across arbitrary subfolder hierarchies in < 700ms.
  - Strictly isolated user sidecar exports from `assets/baseline/` (the Golden Baseline).
- **Workspace Code Audit & Verification**:
  - Full audit across `aesthetic-models`, `aesthetic-metrics`, `aesthetic-core`, `aesthetic-ui`, and `aesthetic-cli`.
  - All 27 unit and integration tests passing (`cargo test --workspace`); zero Clippy warnings (`cargo clippy --workspace -- -D warnings`).
  - Fresh release binaries built (`aesthetic-ui.exe`, `aesthetic-cli.exe`).
- **M28: Interactive Smart Showreel Composer Modal & Pacing Grid** (`crates/aesthetic-ui/ui/index.html`, `crates/aesthetic-ui/ui/app.js`, `crates/aesthetic-ui/src/main.rs`):
  - Added dedicated **"Smart Reel"** button to the Candidate Selects panel header.
  - Implemented the `#composer-modal` and `/api/compose_showreel` endpoint displaying target vs assembled duration, shot scale pacing, and tabular cut list order.
- **M24: Direct Live DaVinci Resolve Studio IPC Bridge** (`crates/aesthetic-core/src/export.rs`, `crates/aesthetic-ui/src/main.rs`, `crates/aesthetic-ui/ui/app.js`, `crates/aesthetic-cli/src/main.rs`):
  - Implemented `send_to_live_resolve` executing the Python Resolve bridge against the running DaVinci Resolve Studio scripting IPC socket.
  - Added **"Send to Live Resolve (Direct)"** in the UI Export menu and `--live-resolve` flag to `aesthetic-cli rescore`.
- **M25: Batch Folder Video Queue & Progressive Sidecars & Unified NLE Exports** (`crates/aesthetic-core/src/pipeline.rs`, `crates/aesthetic-core/src/export.rs`, `crates/aesthetic-ui/src/main.rs`, `crates/aesthetic-ui/ui/app.js`, `crates/aesthetic-cli/src/main.rs`):
  - Implemented `analyze_folder_queue` automatically discovering all supported video media files in a folder and sequentially analyzing, scoring, and outputting organized sidecars, contact sheets, per-file EDLs/XMLs, and unified season-wide `season_all_hero_selects.edl` and `season_all_hero_selects.xml`.
  - Added recursive sidecar discovery in `rescore_from_sidecars` to discover takes across full season folder trees or single episode folders with companion PNG pairing.
  - Added `AppState.cached_frames` in-memory image cache, serving cached sidecar thumbnails instantly (0.1ms) without spawning FFmpeg on directories, eliminating process flooding and crashes.
  - Enforced strict Golden Baseline protection invariant preventing user video sidecars from ever writing into `assets/baseline/`.
  - Added **"Batch Analyze Folder"** in UI Import menu and `aesthetic-cli batch <folder> [--out <dir>]`.
  - Updated `/api/export_edl`, `/api/export_fcpxml`, and `/api/export_csv` to attach active source video stems and trigger direct browser attachment downloads.
  - Added STA TopMost folder picker and browser `prompt(...)` fallback for "Open Cached Sidecars Folder".
- **M26: Smart Showreel Composer & Target Duration Assembly** (`crates/aesthetic-core/src/pipeline.rs`):
  - Implemented `compose_smart_showreel` optimization engine assembling curated reels to target durations (60s, 90s, 120s) balancing objective focus (Commercial Lighting, Dramatic Narrative, Action Kinetic, Balanced Hero), shot scale alternation rhythm, and color temperature continuity.
- **M27: Personal Taste Profile & Feedback Reranker Tuning** (`crates/aesthetic-core/src/pipeline.rs`, `crates/aesthetic-ui/src/main.rs`):
  - Implemented `compute_personal_taste_profile` dynamically calibrating personal style affinities and adapting the 6 narrative reranker weights based on user curation actions (`/api/taste_profile`).
  - Implemented `compute_personal_taste_profile` dynamically calibrating personal style affinities and adapting the 6 narrative reranker weights based on user curation actions (`/api/taste_profile`).

---

## Completed in M20–M23
- **M20: Local Cinematographic Rationale Engine & Full-Reference `PSNR`/`SSIM` QC Pack** (`crates/aesthetic-models/src/physics.rs`, `crates/aesthetic-models/src/window.rs`, `crates/aesthetic-metrics/src/exposure.rs`, `crates/aesthetic-core/src/pipeline.rs`, `crates/aesthetic-core/src/export.rs`):
  - Implemented `generate_cinematographic_rationale` generating a rich, empirical DP & Editorial rationale paragraph (`ShotTake.rationale_summary`) citing shot scale, intent, duration, motion classification, dynamic range stops, highlight roll-off, key-to-fill ratio, lighting key, palette family, CCT, depth planes, focus isolation, gaze poise, and nearest reference match.
  - Implemented `compute_frame_pair_psnr_and_ssim` measuring consecutive frame-pair `psnr_db` (dB) and $8\times 8$ block Wang-Bovik structural similarity `ssim_score` across 3-frame burst windows.
- **M21: Interactive Desktop UI Curation Controls & Cached Sidecar Folder Loader** (`crates/aesthetic-ui/src/main.rs`, `crates/aesthetic-ui/ui/index.html`, `crates/aesthetic-ui/ui/app.js`):
  - Added `[★ Promote Hero]`, `[📌 Pin Select]`, and `[✕ Deprioritize]` buttons to every Contact Sheet card in `aesthetic-ui`, immediately logging `SelectFeedbackEvent` and re-running `apply_reel_diversity_ranking` on the active analysis.
  - Added `"Open Cached Sidecars Folder"` (`#btn-open-sidecars` -> `/api/rescore_sidecars`) to load and re-score any cached JSON+PNG sidecar directory in ~240ms.
- **M22: Direct DaVinci Resolve Timeline & Marker Bridge** (`crates/aesthetic-core/src/export.rs`, `crates/aesthetic-ui/src/main.rs`, `crates/aesthetic-cli/src/main.rs`):
  - Implemented `generate_resolve_timeline_script` outputting a ready-to-run `DaVinciResolveScript` Python automation script that creates an `AESTHETIC_Hero_Selects` bin and timeline, appends the Top-$N$ usable windows at frame-accurate In/Out handles, and attaches color-coded Resolve markers (`Yellow` Hero #1, `Blue` Select, `Red` Forensic Advisory) containing the full `rationale_summary` and pillar/reranker scores.
  - Exposed via `"DaVinci Resolve Script (.py)"` in the UI Export menu (`/api/export_resolve_script`) and `--resolve <file.py>` in `aesthetic-cli rescore`.
- **M23: Expanded Golden Baseline to `1,112` Real Measured Shots Across `199` Award-Winning Films** (`assets/baseline/manifest.json`, `assets/baseline/shots.json`):
  - Downloaded and ingested 67 additional multi-shot still galleries (402 full-res frames) from `film-grab.com` covering remaining Awards Registry titles.
  - Reconciled `manifest.json` (`total_films = 199`, `total_reference_shots = 1112`, `0` synthetic seeds): `Dynamic Range p10 = 7.45 / p25 = 8.93 / p50 = 9.98 / p75 = 11.03 / p90 = 11.69 stops`, `Highlight Roll-Off p10 = 95.36% / p50 = 100.0%`, `Laplacian Acutance p10 = 11.38 / p50 = 48.39 / p90 = 247.68`.

---

## Completed in M14–M19
- **M19: Complete 6-Head Narrative Rerankers, Motion Coherence, Palette Family & Select Feedback Learning** (`crates/aesthetic-models/src/window.rs`, `crates/aesthetic-models/src/inferred.rs`, `crates/aesthetic-core/src/pipeline.rs`, `crates/aesthetic-core/src/export.rs`, `crates/aesthetic-ui/src/main.rs`, `crates/aesthetic-ui/ui/app.js`, `crates/aesthetic-cli/src/main.rs`):
  - Added `storytelling_score`, `cinematic_technique_score`, and `memorability_score` to `PillarScores`, completing all 6 narrative and aesthetic reranker heads.
  - Added `motion_blur_angle_deg` and `motion_coherence_score` to `MotionDynamics` and integrated directional motion trajectory coherence into `scores.temporal`.
  - Added `palette_family`, `scene_type`, and `shot_intent` classification to `DiscoveredStyle` and integrated `palette_family` intentionality into `color_harmony`.
  - Added `SelectFeedbackEvent`, `log_select_feedback_event`, and `compute_feedback_preference_boost` (`assets/feedback/events.jsonl`), exposed via `/api/feedback` and `aesthetic-cli feedback <take_id> <action>`.
  - Wired the Sequence & Reel Continuity Intelligence banner and all 6 Narrative & Aesthetic Reranker Heads into the live Desktop UI (`aesthetic-ui`) Contact Sheet modal.
- **M18: Narrative & Aesthetic Reranker Heads, Log-Aware Gamut Pillar & Sequence Continuity Banner** (`crates/aesthetic-models/src/window.rs`, `crates/aesthetic-core/src/pipeline.rs`, `crates/aesthetic-core/src/export.rs`, `crates/aesthetic-ui/src/main.rs`):
  - Added `hero_potency_score`, `three_second_impact_score`, and `authorship_distinctiveness_score` to `PillarScores` and JSON sidecars.
  - Integrated CIE 1931 `gamut_coverage_srgb` and `gamut_coverage_p3` into `color_harmony` with `detect_flat_log_encoding` protection so ungraded camera log plates are never penalized prior to LUT transformation.
  - Added the **Sequence & Reel Continuity Intelligence** summary banner and **Narrative & Aesthetic Reranker Heads** diagnostic tree to `generate_contact_sheet_html_with_frames`.
- **M14: Cross-Shot Sequence Continuity, Log-Encoding Detection & MMR Reel Diversity** (`crates/aesthetic-models/src/temporal.rs`, `crates/aesthetic-models/src/manifest.rs`, `crates/aesthetic-core/src/pipeline.rs`):
  - Implemented `ReelSequenceMetrics` measuring cross-scene white-balance standard deviation (`wb_cross_scene_std`), Kelvin CCT standard deviation (`color_temp_cross_scene_std`), mean luminance consistency (`exposure_consistency_std`), `coverage_consistency_score`, `grading_uniformity_score`, chronological cut-boundary `visual_fatigue_index`, and `reel_diversity_score`.
  - Added container `color_transfer` classification (`VideoSourceInfo::classify_transfer_curve`) and pixel-level flat-log plate detection (`detect_flat_log_encoding`), emitting non-punitive `LOG_ENCODED_SIGNAL` diagnostics.
  - Added Maximal Marginal Relevance (`apply_reel_diversity_ranking`) and Z-plane + catchlight + edge-density `shot_scale` classification (`Close-Up`, `Medium Close-Up`, `Medium`, `Wide`).
- **M15: Within-Style-Cluster & Motion Velocity Baseline Quantiles** (`crates/aesthetic-core/src/baseline_store.rs`):
  - `compare_to_golden_baseline_with_style` computes percentiles both against the full 760-shot award corpus and within the candidate's matched style-family cluster (`Within-Style DR`, `Within-Style Key:Fill`), plus optical flow velocity percentiles against the 285 measured video setups.
- **M16: Expanded Non-Punitive Forensic Diagnostics** (`crates/aesthetic-core/src/pipeline.rs`):
  - Added `detect_subtitle_or_lower_third_burnin` (`SUBTITLE_OR_LOWER_THIRD_BURNIN`), 3-frame burst `detect_burst_light_flicker` (`PRACTICAL_LIGHT_FLICKER`), and high-velocity shear `ROLLING_SHUTTER_SKEW_RISK`.
- **M17: Instant Cached Sidecar Re-Scoring** (`crates/aesthetic-core/src/export.rs`, `crates/aesthetic-cli/src/main.rs`):
  - Added `rescore_from_sidecars` and CLI command `aesthetic-cli rescore <sidecars_dir> [--contact-sheet <file.html>]`, re-evaluating and re-ranking cached JSON+PNG sidecars against the active Golden Baseline in ~240ms without re-decoding video.

---

## Completed in M13
- **100% Real Pixel-Measured Golden Baseline (`n=760` across 135 Award-Winning Films)** (`assets/baseline/manifest.json`, `assets/baseline/shots.json`, `crates/aesthetic-core/src/baseline_store.rs`):
  - Completed full `ingest-server` extraction across all 55 matched award-winning feature films on `M:\movies` (285 continuous decoded video setups).
  - Extracted and ingested 92 multi-shot high-resolution uncompressed still collections (475 real frames, 5–12 distinct shots per film) from `film-grab.com`, `shot.cafe`, and `frameset.app`.
  - Purged all synthetic `REF_` seed entries and reconciled `manifest.json` (`version = "2.0.0-measured"`): `Dynamic Range p10 = 7.33 / p25 = 8.62 / p50 = 9.73 / p75 = 10.85 / p90 = 11.65 stops`, `Highlight Roll-Off p10 = 97.15% / p50 = 100.0%`, `Laplacian Acutance p10 = 10.58 / p50 = 40.43 / p90 = 198.47`.
- **Cut-Aware 3-Frame Burst & Same-Setup Consolidation** (`crates/aesthetic-core/src/pipeline.rs`):
  - `analyze_video_file` extracts a 3-frame burst (`0.25s` interval) at each candidate sample point, steps past hard cuts (`MAD > 26.0`), and merges consecutive samples from the same camera setup (`MAD < 10.5`) into a single optimal `1.5s–4.0s` usable window.
- **Mean-Centered Spatial + Craft Reference Matching** (`crates/aesthetic-core/src/inference.rs`, `crates/aesthetic-core/src/baseline_store.rs`, `crates/aesthetic-core/src/pipeline.rs`):
  - Upgraded `infer_embedding` to a resolution-invariant `32x36` spatial-chromatic grid and implemented `nearest_measured_reference_with_craft` combining mean-centered Pearson spatial correlation with dynamic range, log-acutance, and key-to-fill craft proximity, eliminating positive-orthant hubness.
- **Lossless PNG Sidecars & Embedded Contact Sheets** (`crates/aesthetic-core/src/export.rs`, `crates/aesthetic-core/src/pipeline.rs`):
  - `export_shot_sidecars_with_frames` writes `<take_id>.png` alongside `<take_id>.json` (`"hero_frame_png"`).
  - `generate_contact_sheet_html_with_frames` embeds lossless PNG stills directly (`data:image/png;base64,...`).

---

## Completed in M12
- **Zero Horizontal Scrolling & Modernized Layout** (`crates/aesthetic-ui/ui/app.css`, `ui/index.html`):
  - Enforced strict `overflow-x: hidden !important` on `html`, `body`, `.app-container`, and `.workspace-grid`. Adaptive grid column distribution prevents horizontal overflow across standard desktop resolutions.
- **True Frame & Thumbnail Decoders** (`crates/aesthetic-ui/src/main.rs`, `ui/app.js`):
  - `/api/frame?time={t}`: Decodes and serves real JPEG frames at the given timestamp for the main picture viewport.
  - `/api/thumbnail?time={t}`: Downscales frames to 320x180 JPEG thumbnails for candidate selects cards and contact sheets.
  - `#viewport-frame-img`: Displays real frame output in the picture viewport; overlays seamlessly with EL Zone and diagnostics.
  - Candidate selects cards display real thumbnails with rank, score, SMPTE timecodes, duration, and claimed tags.
- **Broadcast Scopes Overhaul** (`crates/aesthetic-ui/ui/app.js`, `crates/aesthetic-ui/src/main.rs`):
  - High-DPI (`760x428`) scopes sample pixels directly from the active viewport frame at 1:1 column resolution with vertical scanline phosphor trace connection (emulating DaVinci Resolve / Tektronix OLED/CRT scopes) plus 380-column bilinear backend fallback.
  - Smooth, non-pixelated rendering: authentic green phosphor waveform with white-hot core bloom, 3-pane RGB parade, high-density vectorscope with 25%/50%/75%/100% saturation rings, 57° skin tone I-line, and Rec.709 target boxes, Gaussian-smoothed quadratic spline histograms, and CIE 1931 chromaticity diagram (Rec.709 & Rec.2020 gamuts).
- **Golden Baseline Award-Winning Cinema Benchmarking** (`crates/aesthetic-ui/src/main.rs`, `ui/index.html`, `ui/app.js`, `crates/aesthetic-core/src/baseline_store.rs`):
  - Anchored primary benchmark comparison to the **Award-Winning Cinema Golden Baseline (184 Oscar, ASC & BSC Reference Films)** across Dynamic Range, Highlight Roll-Off, MTF50 Optical Acutance, Key-to-Fill Ratio, Split-Toning Separation, Gaze Poise, and Eye Catchlight Specular.
  - Relegated individual cinematographer similarity to a strictly secondary ancillary stylistic note (`Ancillary DP Affinity`), keeping the core evaluation focused on empirical award-cinema distributions.
  - Enforced strict $\le 100\%$ alignment cap and objective, non-judgmental descriptive deltas.
  - Commented out prescriptive "Cinematographic Improvement Actions" per mandate to quantify, not criticize.
- **Authentic Still-Image Evaluation & Real Measured Physics** (`crates/aesthetic-ui/src/main.rs`, `crates/aesthetic-core/src/pipeline.rs`):
  - Direct still-image support (`.png`, `.jpg`, `.tiff`, `.webp`, `.bmp`) in `/api/open_media`, `/api/analyze`, and `get_frame_for_time` via `image::open`.
  - Replaced synthetic sine-wave fallback and empty `Default::default()` demo structs with 3 photorealistic lit reference setups evaluated end-to-end by `evaluate_candidate_frame` + `enrich_take`.
- **Modernized Menus & Delivery Formats** (`crates/aesthetic-ui/ui/index.html`, `ui/app.js`, `src/main.rs`):
  - **Import Dropdown**: Open Media File, Import Web URL, Bulk Import (Media Server Ingest), with descriptive tooltips.
  - **Export Dropdown**: FCPXML (.xml), CMX 3600 EDL (.edl), CSV Selects (.csv), Contact Sheet (HTML), Contact Sheet (PNG), Hero Shots Only (PNG), with descriptive tooltips.
  - Added `/api/export_contact_sheet_png` and `/api/export_hero_png` endpoints.
- **Relocated Pop-Out Contact Sheet & Complete 58-Metric Tree** (`crates/aesthetic-ui/ui/index.html`, `ui/app.css`, `ui/app.js`, `crates/aesthetic-core/src/export.rs`):
  - Added dedicated Contact Sheet subbar directly below Candidate Selects header with `[⤢ Contact Sheet]` button.
  - Both the in-app Contact Sheet modal and exported HTML/JSON sidecars render **every single measured metric** (58 metrics across Exposure, False Color IRE Zones, EL Zones 0–X, Optics/MTF, Colorimetry/Gamut, Model-Inferred Craft/Lighting/Focus/Staging, Temporal/Optical Flow Motion Dynamics, Golden Baseline Distribution Percentiles, and Forensic Flags).
- **Floating Resizable Pop-Out Panels**:
  - Pop-out buttons `[⤢]` on Viewport, Scopes, and Visual Æesthetic open floating, resizable containers with draggable headers and dock-back controls.
- **Testing & Toolchain**:
  - 24/24 workspace tests passing. Zero clippy warnings (`-D warnings`). Release binaries verified.

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
