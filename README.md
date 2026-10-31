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
