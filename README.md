# AESTHETIC

AESTHETIC is a local desktop application and high-performance video intelligence engine designed for cinematographers and editors. It analyzes finished media (completed reels, films, and portfolio work), discovers and ranks the top $N$ candidate shots and continuous usable sequences, and exports hero stills, contact sheets, CMX 3600 EDLs, XML timeline round-trips, and scoring diagnostics — comparing work against a Golden Baseline of award-winning cinema to show creators where and how they can improve using empirical data.

It runs entirely locally on your machine: no external servers, no cloud APIs, zero subscription overhead.

---

## Mission & Architecture

AESTHETIC is built from the ground up as a **Rust Core Engine** prioritizing:
1. **Showreel & Portfolio Curation**: Saving cinematographers and editors dozens of hours of watching through their entire catalogue of finished work to assemble the strongest hero selects.
2. **Deterministic Empirical Data**: Replacing subjective guesswork with 79 exact mathematical and visual measurements across exposure zones, true dynamic range stops, MTF spatial frequencies, and color gamuts.
3. **Continuous Usable-Window Intelligence**: Filtering out camera whips, settle wobbles, and rack-focus hunting to evaluate sustained 1.5s–4.0s takes with peak narrative poise.
4. **Computational Speed & Hardware Acceleration**: Multi-threaded SIMD pixel pipelines with DirectML GPU acceleration (NVIDIA, AMD/ATI, Intel on Windows; Metal/Vulkan on macOS/Linux).
5. **Cross-Platform Target**: Standalone binaries for Windows x64, macOS, and Linux.

---

## Documentation & Governance

| Document | Purpose |
| :--- | :--- |
| [AGENTS.md](AGENTS.md) | Agent takeover protocol, live machine safety rules, and workspace invariants |
| [START_HERE.md](START_HERE.md) | Developer quickstart, Cargo workflow, and build instructions |
| [STATUS.md](STATUS.md) | Active milestone tracker and rebuild roadmap |
| [HANDOFF.md](HANDOFF.md) | Current session state and immediate next step baton |
| [docs/AESTHETIC_Metrics.md](docs/AESTHETIC_Metrics.md) | Complete mathematical specification for all 79 metric calculations |

---

## Rebuild Roadmap & Progress

| Milestone | Scope | Status | Notes |
| :--- | :--- | :---: | :--- |
| **M0: Protocol & Rebuild Setup** | Repository protocol initialization, legacy Python purge, clean Rust workspace | ✅ Done | Clean Rust Cargo workspace established |
| **M1: Data Models & Objective Metrics** | `aesthetic-models`, `aesthetic-metrics` (SIMD exposure, color, focus, sharpness) | ✅ Done | Pure Rust math verified with passing unit tests |
| **M2: Temporal Engine & Usable Windows** | `aesthetic-core` video demux, cut classification, continuous take evaluation | ✅ Done | 4-Output architecture implemented & tested |
| **M3: Baseline Vector Store & DP Match** | `BaselineStore` vector similarity, master DP fingerprint matching, empirical calibration | ✅ Done | 58 Master DP craft signatures active |
| **M4: Headless CLI & Benchmark Harness** | `aesthetic-cli`, 4K SIMD physics benchmark (1.70s 4K pass), demo take evaluation | ✅ Done | Standalone executable verified in debug and release |
| **M5: Desktop UI, Scopes & Release** | 5 Broadcast Scopes, CMX 3600 EDL/CSV Export, Desktop UI Shell, DirectML Acceleration | ✅ Done | Release binaries verified (`aesthetic-cli`, `aesthetic-ui`) |
| **M6: Editorial Deliverables & Stills Ingest** | JSON Shot Sidecars, Top-$N$ Breakout & Visual Contact Sheet, Native File Browser, Still Images Baseline Ingest, NLE XML/EDL Round-Trip | ✅ Done | Sidecars, contact sheet collage, still ingest & native open dialogs |
| **M7: Advanced Cinematographic Intelligence** | Depth-Conditioned Z-Plane Focus (Bokeh MTF), Volumetric Key-Fill & Catchlight Geometry, Split-Toning in ACES/Linear Space, Gaze-Anchored Cinematic Poise, Style-Family Manifold Geodesics | ✅ Done | Learned subjective heads & perceptual optical modeling |
| **M8: Scoring Matrix & DP Comparison UI** | Side-by-Side Master DP Diagnostic Table, Empirical Improvement Action Cards, Port Binding Configuration, Craft Benchmark Integration | ✅ Done | Desktop UI diagnostic table, dynamic improvement recommendations & 4K craft benchmarks |
| **M9: EL Zone & Pretrained Baseline** | Ed Lachman, ASC EL Zone 10-stop calibrated false color, 174 pretrained master shots across 58 films, Stage 1/2 UI groundwork | ✅ Done | Industry standard stop false color and out-of-the-box pre-trained baseline corpus |
| **M10: Showreel Assembly & Forensic Overlays** | Stage 1 candidate selects bin, interactive In/Out handle trimming, Stage 2 real-time diagnostic viewport modes (EL Zone, Peaking, 3D Light, Eyeline/Gaze) | ✅ Done | Dynamic showreel assembly & forensic camera intelligence active in UI |
| **M11: Awards Registry & Media Server Ingestion** | 184 Oscar, ASC, BSC & Landmark titles registry, shot-boundary segmentation (cut-isolated setups), single-pass burst extraction, media server scanner with deduplication & GUI force toggle, optical flow motion dynamics recorded in baseline | ✅ Done | Scanning `M:\movies` matching 55 award films with continuous setup extraction, motion dynamics & GUI controls |
| **M12: Desktop UI, Scopes & Visual Æesthetic Overhaul** | Zero-scroll UI, decoded frame/thumbnail endpoints, broadcast scopes from active playhead, unified "Visual Æesthetic" window, capped 100% similarity, non-judgmental deltas, pop-out contact sheet with collapsible metrics trees & sidecar metadata | ✅ Done | Polished broadcast-grade desktop shell with real image output and objective benchmarking |
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

## The Three Scoring Pillars & 79 Metrics

Every shot is evaluated across three core pillars combined to produce the final composite score:
- **Technical (50% default)**: Objective, reproducible pixel measurements (sharpness, clipping, noise, optical aberrations, dynamic range).
- **Creative (30% default)**: Vector similarity distance to the Golden Baseline corpus of 58 master cinematographers and style clusters.
- **Subjective (20% default)**: Human preference, focal saliency concentration, and composite aesthetic appeal.

### Metric Distribution (79 Mathematical Metrics)
1. **Exposure & Dynamic Range (16 metrics)**: Zones 0–IX (10 zone % bins), Mean, Median, Std, Skew, Kurtosis, Highlight Clipping %, Shadow Clipping %, Zone V 18% Gray Deviation, SNR Luma, SNR Chroma, PSNR, SSIM, Exposure Intent Score.
2. **Lighting & Contrast (14 metrics)**: Dynamic Range Stops ($p_{98}-p_2$), Key-to-Fill Ratio, 4 Quadrant Luminance (TL, TR, BL, BR), Kelvin Temperature, Temperature Deviation $\Delta$, Shadow Detail, Shadow Noise, Penumbra Hardness Gradient, Motivation Azimuth, Directional Contrast.
3. **Composition & Staging (13 metrics)**: Rule of Thirds Horizontal (2), Rule of Thirds Vertical (2), Center of Mass X, Center of Mass Y, Negative Space %, Depth Separation Z, Occupancy %, Symmetry Index, Headroom %, Lead Room %, Face Thirds Proximity.
4. **Camera Movement & Motion (11 metrics)**: Optical Flow Mean X, Mean Y, Magnitude, Flow Velocity Std, Jerkiness, Smoothness, Micro-Jitter, Motion Blur Energy, Blur Angle, Sharpness Retention on Move, Trajectory Curvature.
5. **Colour & Skin Tones (12 metrics)**: Lab $L^*$ Mean, $a^*$ Mean, $b^*$ Mean, Chroma Mean, Chroma Uniformity, Hue Shannon Entropy, $\Delta E_{2000}$ vs D65 Neutral, $\Delta E_{2000}$ vs DP Baseline, Skin Tone $\Delta E_{2000}$ (vs Fair, Medium, Deep Macbeth references), Chroma Noise, Banding Index, Gamut Coverage Area (sRGB, DCI-P3, Rec.2020).
6. **Optical & Image Quality (13 metrics)**: Laplacian Variance, Edge Density %, MTF FFT Bands 1–5 (5 spatial frequency ratios), High-Frequency Texture Mask, Lens Curvature Hough Radius, Corner Vignetting Stops, Chromatic Aberration Fringe Width, Glare Wash %, Compression Blocking DCT.
