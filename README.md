# AESTHETIC

AESTHETIC is a local, cross-platform application that finds and ranks the best shots in a video against a standard of cinematic excellence derived from award-winning cinematography. It scores every shot across three pillars — Technical, Creative, and Subjective — using a Golden Baseline built from Oscar-winning and ASC-awarded reference material. The Web UI is the primary interface. It runs entirely locally with no servers.

> Status: Phase 0 complete. Foundation stable. Pipeline implementation in progress.

---

## Vision

AESTHETIC is designed to be the definitive tool for automated cinematic shot analysis. It does not ask what looks good to you — it measures how close a shot comes to what the industry has already agreed is excellent.

Instead of just detecting cuts, AESTHETIC understands and ranks shots. It provides a quantifiable, data-driven system for identifying the most cinematically powerful moments in any video, scored against a reference corpus of award-winning work.

**Core goals**

**Implement a granular, multi-pillar scoring engine**
Score every shot against a comprehensive matrix broken down by cinematic category (Exposure, Lighting, Composition, Color, Movement, Image Quality, Narrative) and analytical pillar (Technical, Creative, Subjective), as specified in `AESTHETIC_Metric.md`.

**Quantify the technical**
Provide objective, reproducible, and verifiable metrics for every shot — histogram statistics, optical flow smoothness, clipping percentages, color palette entropy, sharpness proxies, and more. This establishes a firm, data-driven foundation of quality.

**Score against cinematic excellence**
The Golden Baseline is not a personal taste profile. It is a curated, versioned corpus of stills and frames from Oscar-winning and ASC-awarded cinematography. The Creative pillar scores new footage by measuring its proximity to this corpus in embedding space — how closely does this shot resemble work the industry has already judged as great.

**Leverage AI vision models**
CLIP embeddings power the Creative pillar similarity scoring. MiDaS provides depth estimation. YOLO handles subject and face detection. A vision-language model generates the human-readable rationale explaining why each shot scored the way it did. All model inference results are cached in per-frame sidecars so re-scoring is fast.

**Provide a transparent and interactive GUI**
The interface makes the entire analysis process visible. Verbose logs, per-shot score breakdowns, visual scopes (histogram, waveform, RGB parade, vectorscope), and plain-language rationale for every selected shot.

---

## Table of contents

- [Vision](#vision)
- [Key outcomes](#key-outcomes)
- [Example use cases](#example-use-cases)
- [Current state](#current-state)
- [Features](#features)
- [Architecture overview](#architecture-overview)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Setup](#setup)
- [Configuration](#configuration)
- [Scoring pillars](#scoring-pillars)
- [Scoring categories](#scoring-categories)
- [Selection strategy](#selection-strategy)
- [Golden Baseline](#golden-baseline)
- [Roadmap](#roadmap)
- [Milestones](#milestones)
- [Quality bar](#quality-bar)
- [Known risks](#known-risks)
- [Contributing](#contributing)
- [FAQ](#faq)
- [License](#license)

---

## Design principles

- Deterministic by seed
- Always write something even when heavy features are unavailable
- Modular agents with simple contracts and JSON sidecars
- Heavy work in subprocess workers with timeouts and graceful fallbacks
- One canonical API surface — `aesthetic/bridge/api.py`
- Score shots as durations, not individual frames

---

## Key outcomes

- Rank every shot in a submitted video against a standard of award-winning cinematography
- Explain why each shot scored the way it did with numeric evidence and plain-language rationale
- Export a selects package an editor can work from directly: hero clips, contact sheet, scored manifest
- Run locally with deterministic, reproducible results
- Produce outputs that surface shots, not just frames — accurate in/out timecodes are the primary deliverable

---

## Example use cases

**Showreel assembly**
Submit a DP's body of work. AESTHETIC flags and ranks the shots that score closest to cinematic excellence, producing a shortlist the editor uses as the foundation for a showreel. Removes subjectivity and tedium from the selects process.

**Production dailies review**
Submit a day's footage. Get back the best shots from each scene ranked by composite score, with per-category breakdowns showing exactly where each shot is strong or weak.

**Archive and cataloguing**
Submit archival or library footage. Surface the most cinematically valuable moments for licensing, preservation priority, or highlight reels.

---

## Current state

- `aesthetic/bridge/api.py` — canonical API, all UI calls route here
- `aesthetic/app.py` — thin pywebview boot shell only
- `aesthetic/webui/index.html` — Web UI scaffold with tabs for Analysis, Scoring Matrix, Log, and Golden Baseline
- `aesthetic/baseline.py` — fully implemented `BaselineStore` with versioned golden promotion, staging/augment buffers, and online statistics
- `aesthetic/config/__init__.py` — config loading and all path constants
- `aesthetic/agents/` — all six pipeline agents stubbed, implementation in progress
- `aesthetic/models/` — data contracts stubbed, implementation in progress
- `AESTHETIC_Metric.md` — complete metrics specification

Pipeline agents not yet implemented:
- Ingest (ffprobe metadata)
- Scene detection
- Candidate sampling
- Metrics engine
- Selection and dedupe
- Export

---

## Features

**Implemented**
- Web UI with Analysis, Scoring Matrix, Log, and Golden Baseline tabs
- Job creation and mock analysis flow (end-to-end UI testable)
- Manifest export to disk
- `BaselineStore` — versioned golden baseline with staging, augment, and promotion model
- Config loading from `config/config.yaml`
- Deterministic mock scoring seeded from config

**Planned**
- ffprobe ingest and scene detection
- Per-scene candidate frame sampling with seeded jitter
- Full metrics engine (all categories in `AESTHETIC_Metric.md`)
- CLIP embedding per frame for Creative pillar similarity scoring
- MiDaS depth estimation
- YOLO subject and face detection
- NIMA / LAION aesthetic predictor for Subjective pillar
- VLM rationale generation per selected shot
- Shot-level score aggregation (temporal variance aware)
- Global selection with facility location diversity objective
- Perceptual hash and cosine deduplication
- Hero clip export via FFmpeg trim list
- Contact sheet generation
- Visual scopes per shot card (histogram, waveform, RGB parade, vectorscope)
- SSE progress events for pipeline stages
- Golden Baseline corpus ingestion UI

---

## Architecture overview

Pipeline as local modules:

```
Ingest -> Scenes -> Candidates -> Metrics -> Model Inference -> Shot Aggregation -> Selection -> Export -> Manifest
```

- Every stage reads a validated model and returns a validated model
- Everything important is JSON-serializable and written to a per-job sidecar
- Model inference results (CLIP embeddings, depth maps, detection results) are cached — re-scoring never re-runs inference
- Heavy work runs in a subprocess worker with timeout and graceful fallback
- Web UI is local only — pywebview window talks directly to `bridge/api.py` via JS bridge
- No HTTP server, no external services, no network required

---

## Repository layout

```
AestheticApp/
├── aesthetic/
│   ├── agents/                   # one module per pipeline stage
│   │   ├── __init__.py
│   │   ├── ingest.py             # ffprobe metadata → VideoMeta
│   │   ├── scenes.py             # scene detection → scenes.json
│   │   ├── sampling.py           # candidate frame extraction → candidates.json
│   │   ├── metrics.py            # per-frame metrics → FrameMetrics sidecars
│   │   ├── selection.py          # global ranking, diversity, dedupe → shots.json
│   │   └── export.py             # hero clips, contact sheet, manifest
│   ├── bridge/
│   │   ├── __init__.py
│   │   └── api.py                # canonical API surface (pywebview JS bridge)
│   ├── config/
│   │   ├── __init__.py           # path constants and config loader
│   │   └── config.yaml           # runtime configuration
│   ├── data/                     # runtime data (gitignored)
│   │   ├── uploads/              # incoming video and reference stills
│   │   ├── jobs/                 # per-job artifacts
│   │   │   └── <job_id>/
│   │   │       ├── manifest.json
│   │   │       ├── scenes.json
│   │   │       ├── candidates.json
│   │   │       ├── shots.json
│   │   │       ├── frames/       # extracted candidate frames
│   │   │       └── metrics/      # per-frame FrameMetrics sidecars
│   │   └── baseline/             # Golden Baseline store
│   │       ├── staging.json
│   │       ├── augment.json
│   │       └── golden/
│   │           ├── active.json
│   │           └── v0001.json
│   ├── models/
│   │   ├── __init__.py
│   │   ├── job.py                # Job, VideoMeta, Shot models
│   │   └── scores.py             # FrameMetrics, ShotScore, Manifest models
│   ├── storage/
│   │   ├── __init__.py
│   │   └── fs.py                 # path helpers
│   ├── webui/
│   │   ├── __init__.py
│   │   └── index.html            # single-page Web UI
│   ├── __init__.py
│   ├── app.py                    # pywebview boot shell (thin wrapper only)
│   └── baseline.py               # BaselineStore implementation
├── outputs/                      # exported deliverables (gitignored)
│   └── <job_id>/
│       ├── <stem>_<job_id>_manifest.json
│       ├── frames/               # hero frames with score prefix
│       ├── clips/                # hero scene clips
│       └── contact_sheet.jpg
├── AESTHETIC_Metric.md           # complete metrics specification
├── README.md
└── requirements.txt
```

---

## Requirements

- Python 3.12
- FFmpeg on PATH (required for scene detection, sampling, and export)

**Python packages — core**
- pywebview
- opencv-python
- numpy
- pillow
- tqdm
- pyyaml
- scikit-image
- scipy

**Python packages — AI vision (optional, GPU-accelerated where available)**
- open-clip-torch (CLIP embeddings for Creative pillar)
- torch (required by CLIP and optional MiDaS)
- timm (required by MiDaS)
- ultralytics (YOLO for subject and face detection)

**External API (optional)**
- Anthropic or OpenAI API key for VLM rationale generation (called per selected shot only, not per frame)

---

## Setup

```bash
git clone https://github.com/electrichobo/AestheticApp.git
cd AestheticApp
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python -m aesthetic.app
```

---

## Configuration

`aesthetic/config/config.yaml` controls all runtime behaviour:

```yaml
io:
  outputs_dir: "data/outputs"
  baseline_path: "data/baseline.json"

runtime:
  seed: 42
  cpu_guard_pct: 85
  gpu_guard_pct: 90

extract:
  per_scene_candidates: 9
  per_scene_keep_pct: 0.4
  min_scene_len_frames: 12

weights:
  technical: 0.50
  creative:  0.30
  subjective: 0.20

features:
  qc_pack_enabled: false      # enables VMAF/PSNR/SSIM when reference exists
  clip_enabled: true          # CLIP embedding for Creative pillar
  vlm_rationale_enabled: false # VLM API call for shot rationale text
  gpu_enabled: false          # GPU acceleration for model inference
```

---

## Scoring pillars

Every shot is scored across three pillars. The pillars are combined using the weights in `config.yaml`.

**Technical**
Objective, math-based metrics. Reproducible and verifiable. Measures whether the shot is executed correctly — exposure, focus, stability, color accuracy, image quality.

**Creative**
Similarity to the Golden Baseline corpus in CLIP embedding space. Measures how closely the shot resembles award-winning cinematography. Intentional stylistic deviation is handled through tunable delta curves — a controlled underexposure scores differently from an accidental one.

**Subjective**
Industry taste proxy. Combines the implicit subjective judgments encoded in the Golden Baseline corpus (what Academy and ASC voters responded to emotionally and artistically) with signals from aesthetic predictor models (NIMA, LAION). Weighted to allow variance in creative preference without abandoning the objective standard. Cinematography is an art, not a mathematical proof.

---

## Scoring categories

Each pillar score is broken down by category. Full metric specifications are in `AESTHETIC_Metric.md`.

| Category | Key metrics |
|---|---|
| Exposure | Histogram distribution, clipping, SNR, PSNR, SSIM, temporal consistency |
| Lighting | Dynamic range, key-fill ratio, color temperature, shadow detail/noise, hard vs soft transition |
| Composition | Rule of thirds, face placement, center of mass, negative space, depth separation, occupancy maps, shot scale |
| Camera Movement | Optical flow, smoothness, stabilization, motion blur, movement type, trajectory |
| Color | WB deviation, saturation, palette entropy, skin tone ΔE, chroma noise, grading uniformity |
| Image Quality | Sharpness (MTF proxy), lens distortion, vignetting, chromatic aberration, compression artifacts |
| Narrative & Aesthetic | Saliency consistency, visual storytelling effectiveness, compelling degree MOS |

**Additional metrics under evaluation**
- Shot rhythm: pacing relative to surrounding shots, cut point quality, temporal arc
- Focus and depth: focus plane consistency, bokeh quality proxy, depth of field intentionality
- Subject rendering: skin texture retention, eye catchlight detection, subject separation
- Noise character: grain character (film vs digital), noise spatial frequency
- Lens character: flare character (anamorphic vs spherical), format/aspect ratio detection
- Scene classification: interior/exterior, day/night, scene type — used to improve Creative pillar like-for-like comparison

---

## Selection strategy

1. Per-scene ranking by total score — apply `per_scene_keep_pct` to form a shortlist per scene
2. Global pool formed from all per-scene winners
3. Deduplication by perceptual hash
4. Diversity constraint via cosine similarity on metric vectors — prevents clustering around a single setup
5. Facility location objective (or k-medoids proxy) for final selection — maximises both quality and coverage
6. `top_k` guaranteed even when degraded

Output: `shots.json` listing selected shots with scores, timecodes, and deduplication evidence.

---

## Golden Baseline

The Golden Baseline is an objective cinematic excellence standard, not a personal taste profile.

It is built from reference stills and frames extracted from Oscar-winning films and ASC-awarded cinematography. It is curated once and versioned — not trained per-user at runtime. New award cycles can be added via the augment buffer without rebuilding from scratch.

**How it works**
1. Reference stills are processed through the same metrics pipeline as candidate frames
2. CLIP embeddings are generated per still and stored in the `BaselineStore`
3. At scoring time, each candidate frame is embedded and its cosine similarity against the baseline corpus is computed
4. The Creative pillar score reflects proximity to the nearest cluster of reference material
5. The active golden version hash is stamped into every manifest for reproducibility

**Baseline states**
- `staging.json` — buffer for new reference material before promotion
- `augment.json` — additive buffer applied on top of an existing golden
- `golden/v000N.json` — versioned, immutable golden snapshots
- `golden/active.json` — pointer to the currently active version

---

## Roadmap

See the full interactive checklist in `AESTHETIC_roadmap.md`.

**Phase 0** — Foundation cleanup ✅
**Phase 1** — Data contracts and models
**Phase 2** — Ingest and scene detection
**Phase 3** — Candidate frame sampling
**Phase 4** — Metrics engine
**Phase 5** — Shot score aggregation
**Phase 6** — AI vision model integration
**Phase 7** — Golden Baseline corpus build
**Phase 8** — Global selection
**Phase 9** — Export deliverables
**Phase 10** — UI pipeline integration
**Phase 11** — Hardening and tests
**Phase 12** — Packaging and release

---

## Milestones

- M0: Repo scaffold, config, UI layout, BaselineStore — ✅ complete
- M1: Minimal pipeline — short clip produces scenes, candidates, metrics, shots, manifest
- M2: Scene detection and sampling stable on test set
- M3: Technical metrics and per-scene selection complete
- M4: Global selection, diversity, and dedupe validated
- M5: Golden Baseline corpus built, Creative and Subjective pillars scoring
- M6: Hero clip export, contact sheet, full manifest
- M7: Packaging — self-contained local app for Windows and macOS

---

## Quality bar

| Milestone | Acceptance criteria |
|---|---|
| M1 | Input video produces scenes.json, candidates.json, metrics sidecars, shots.json, manifest.json |
| M2 | Deterministic output — same video + seed = identical results every run |
| M3 | All Technical metrics in AESTHETIC_Metric.md implemented and unit tested |
| M4 | Selected shots show diversity across scenes with dedupe enforced |
| M5 | Scoring a reference still against the baseline it came from returns a high Creative score |
| M6 | Hero clips are playable. Contact sheet matches shots.json. Manifest is human-readable |
| M7 | One-file install. No Python required. Runs on CPU-only hardware |

---

## Known risks

- FFmpeg availability and codec variance across platforms
- High resolution sources causing memory spikes during frame extraction
- Scene detection threshold tuning on animation, hard flash cuts, or long static shots
- GPU driver and CUDA version variance on mixed hardware
- VLM API latency and cost at scale (mitigated by calling per selected shot only)
- Golden Baseline corpus licensing — reference stills must be cleared for this use

---

## Contributing

Read `AESTHETIC_Metric.md` for the complete metrics specification before contributing to the pipeline.

- Keep stage contracts JSON-serializable and versioned
- Prefer small modules per stage over monolithic pipeline files
- Document every artifact emitted by a stage (path, schema, fallback behaviour)
- Preserve deterministic behaviour — explicit seeds and stable sorting everywhere
- All baseline operations must route through `BaselineStore` in `baseline.py`
- All UI API calls must route through `aesthetic/bridge/api.py`
- Pull requests must include tests for any new metric or pipeline stage

---

## FAQ

**Where is the metrics specification?**
`AESTHETIC_Metric.md` in the repo root.

**Does it require a GPU?**
No. GPU acceleration is optional. CLIP and all model inference can run on CPU, more slowly.

**Does it require an internet connection?**
No. The VLM rationale feature makes an optional API call, but all other processing is fully local.

**What is the Golden Baseline?**
A curated, versioned corpus of stills from award-winning cinematography. It is the reference standard all submitted shots are scored against. It is not trained per-user.

**Why are shots scored as durations rather than individual frames?**
Because a shot is a temporal unit. A frame that looks great in isolation but is surrounded by motion blur and instability is not a great shot. The scoring engine aggregates frame-level metrics across the shot duration, with temporal variance as an explicit signal.

---

## License

TBD