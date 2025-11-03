# AESTHETIC

AESTHETIC is a local, cross‑platform application that finds and ranks the best shots from video, then exports hero frames and hero scenes. It scores candidates across three pillars: Technical, Creative, and Subjective. It supports a user‑trained Golden Baseline so the system learns what great looks like for you or your studio. The Web UI is the primary and only interface. It runs locally and can be wrapped in a desktop shell. No servers.

> Status: scaffold + planning. We intentionally rebuilt the plan to keep things clean and transparent. This README tracks the live plan, current state, and milestones.

---

## Vision

The vision for AESTHETIC is to create the definitive tool for automated cinematic analysis. It aims to bridge the gap between objective, technical quality and subjective, creative intent.

Instead of just detecting shots, AESTHETIC understands and ranks them. It provides a quantifiable, data-driven system for identifying "hero shots," enabling creators, editors, and archivists to instantly find the most powerful and well-crafted moments in any video, based on a standard they can define themselves.

**Core Goals**

**Implement a Granular, Multi-Pillar Scoring Engine:**  
To move beyond simple "good" or "bad" ratings. The goal is to score every shot against a comprehensive matrix broken down by both cinematic category (Exposure, Lighting, Composition, Color, Movement) and analytical pillar (Technical, Creative, Subjective), as put forth in AESTHETIC_Metric.md

**Quantify the 'Technical':**  
To provide objective, reproducible, and verifiable metrics for every shot (e.g., histogram statistics, optical flow smoothness, clipping percentages, color palette entropy). This establishes a firm, data-driven baseline of quality.

**Build a 'Trainable' Creative Standard:**  
To empower users to define their own aesthetic. By training a persistent "Golden Baseline" from reference stills or videos, the 'Creative' pillar becomes a bespoke tool that scores new footage based on its adherence to a user's or studio's specific "house style."

**Provide a Transparent & Interactive GUI:**  
To create a user-friendly interface that makes the entire complex analysis process transparent. Users must be able to see verbose logs, adjust parameters (like shot sensitivity), inspect per-shot scopes (histograms, vectorscopes), and understand why a shot received the score it did.

---

## Table of contents

- [Vision](#vision)  
- [Key outcomes](#key-outcomes)  
- [Product surface](#product-surface)  
- [Current state](#current-state)  
- [Features](#features)  
- [Architecture overview](#architecture-overview)  
- [Repository layout](#repository-layout)  
- [Requirements](#requirements)  
- [Setup](#setup)  
- [Configuration](#configuration)  
- [Usage](#usage)  
- [Scoring pillars](#scoring-pillars)  
- [Selection strategy](#selection-strategy)  
- [Roadmap](#roadmap)  
- [Milestones](#milestones)  
- [Quality bar](#quality-bar)  
- [Contributing](#contributing)  
- [FAQ](#faq)  
- [License](#license)

---



### Design principles

- Deterministic by seed  
- Always write something even when heavy features are unavailable  
- Modular agents with simple contracts and JSON sidecars  
- Heavy work in subprocess workers with timeouts and graceful fallbacks  
- Cross-platform CLI and API with a first-class web UI

---

## Key outcomes

- Find per‑scene and global winners that are useful to an editor or DP
- Explain why each frame was selected with numeric evidence and a short rationale
- Run locally with deterministic results 
- Trainable Golden baseline profiles so taste can adapt over time

---

## Current state

- Web UI scaffold present as `aesthetic/webui/index.html`
- Metrics specification lives in `AESTHETIC_Metric.md` (complete)
- Bootstrap CLI planned for local processing
- No servers. Any wrapper uses a local webview and local IPC only
- FFmpeg should be available on PATH

TBD items  
- First runnable server with job queue, uploads, SSE progress  
- Worker stub that runs ingest, scenes, sampling, metrics, selection, export  
- Golden baseline storage and training endpoints

---

## Features


- Planning documents: README and AESTHETIC_Metric.md
- Web UI layout with tabs, logs, and scopes surface

- Scene detection and frame sampling
- Cheap technical metrics
- Optional CLIP embeddings
- Per‑scene ranking and global selection with diversity and dedupe
- Sidecars, run manifest, and hero‑scenes export
- Scopes: waveform, histogram, RGB parade, vectorscope
- Golden Baseline training and weighting

---

## Development Roadmap

P0. repo and config

 Repo initialized with license and codeowners
 README.md reflects the current vision verbatim
 AESTHETIC_Metric.md linked as source of truth
 config.yaml starter committed with safe defaults
 .env.example for local paths and feature flags
 requirements.txt and requirements-optional.txt (GPU, CLIP)
 Pre-commit hooks for lint, format, basic static checks

P1. core scaffolding

 aesthetic/core/ package with __init__.py
 Deterministic seeding util and run ID generator
 Logger with file and console sinks
 Simple error model with graceful degrade and reasons
 Path helpers for uploads, jobs, artifacts, exports
 Run manifest schema defined and versioned

P2. ingest and scenes

 FFprobe metadata read (fps, size, duration, SAR)
 Content change scene detection with threshold, downscale
 Min scene length, merge short scenes, edge handling
 Scene list persisted to jobs/<id>/scenes.json
 Unit tests with short fixtures

P3. candidate sampling

 Per scene sampling with jitter and min gap
 per_scene_candidates and per_scene_keep_pct honored
 Extracted frames cached to disk
 Candidate index written to candidates.json

P4. metrics engine v1

 Technical metrics implemented per AESTHETIC_Metric.md
 Fast path CPU only implementations for all required metrics
 Metrics sidecar per candidate metrics/<frame>.json
 Pillar combiner for Technical, Creative, Subjective with weights
 Category roll-up to Exposure, Lighting, Composition, Color, Movement, Quality, Narrative
 Total score computed by category weights
 Metrics timing and error capture

P5. creative pillar bootstrap

 Golden Baseline store data/baseline/baseline.json
 Trainer that ingests stills and averages granular values
 Creative score uses delta to baseline with tunable curves
 Baseline read and write guarded by schema version

P6. subjective pillar bootstrap

 Rule based MOS seeds for clarity, emotional response
 Configurable weights
 Input hooks for future learned models

P7. selection and dedupe

 Per scene ranking with fixed keep count or keep percent
 Global pool formed across scenes
 Overcluster with k-medoids or cheap proxy
 Facility location objective for final picks
 Dedupe by cosine and perceptual hash
 At least top_k guaranteed even when degraded
 shots.json and manifest.json finalized

P8. exports

 Hero frames written with score prefix and sidecars
 Optional hero scenes export via FFmpeg trim list
 Contact sheet generation
 outputs/ is clean and predictable
 Export summary appended to manifest

P9. local web UI

 Single page aesthetic/webui/index.html is the user interface
 UI loads config, starts jobs, shows progress and logs
 Per shot cards with category breakdown and scopes
 Adjustable shot sensitivity and weights
 File upload for video and golden stills
 Download links for manifest, shots, frames, exports
 No external server. UI talks to local Python process only

P10. local bridge for UI

 Lightweight local bridge using Python standard libs or a tiny web stack
 Endpoints: create job, job status, log stream, upload, baseline train, artifacts list
 CORS and file size limits configured
 All writes scoped to data/ and outputs/

P11. performance and stability

 Bounded CPU and memory via config
 Optional GPU path for CLIP and heavy ops
 Subprocess worker with timeout and retry
 Frame cache reuse across runs
 Progress events per stage with timing

P12. testing and samples

 Unit tests for metrics math
 Golden small videos and stills under samples/
 Determinism tests with fixed seed
 Regression test that verifies same winners across runs

P13. UX polish

 Clear empty states and recoverable errors
 Verbose log pane with copy to clipboard
 Tooltips for metrics and categories
 Keyboard nav on shot cards and scopes toggle
 Dark theme verified on SDR displays

P14. docs and help

 README install and quickstart verified on Windows and macOS
 Metrics reference points to AESTHETIC_Metric.md
 Troubleshooting guide for FFmpeg and GPU
 Change log started at 0.1.0
 Issue templates for bug and feature

P15. versioning and packaging

 Semantic version tags
 __version__ in package and manifest
 PyInstaller or Briefcase recipe for a local app wrapper
 Portable build that bundles minimal Python where possible
 Build script that stamps version and git SHA

P16. pre-release gate

 All P0 to P15 checked
 Run on three short films and one long feature reel
 Manual spot check correlation to human picks
 Performance within target on CPU-only
 No crash with GPU missing or busy

P17. launch v0.1.0

 Tag and attach builds
 Release notes with known limits
 Sample walkthrough video or GIF
 Backlog moved to GitHub Projects
---

## Architecture overview

Pipeline as local modules:

```
Ingest -> Scenes -> Candidates -> Metrics -> Per-scene picks -> Global selection -> Export -> Manifest
```

- Every stage reads a simple dict and returns a simple dict
- Everything important is JSON‑serializable and logged
- Heavy work can run in a subprocess with a timeout and clean fallback
- Web UI is local only. A desktop wrapper can call the CLI via IPC

---

## Milestones

- M0: Repo scaffold, config example, UI layout checked in
- M1: Minimal pipeline writes frames and manifest from a short clip
- M2: Scene detection and candidate sampling stable on test set
- M3: Technical metrics and per‑scene selection complete
- M4: Global selection, diversity, and dedupe validated
- M5: Golden Baseline training and scoring integrated
- M6: Hero‑scenes export and contact sheet
- M7: Packaging and wrapper for local Web UI

---

## Quality bar

acceptance criteria per milestone

Minimal runnable
  Input video produces scenes, candidates, metrics, and at least top_k hero frames
  Manifest explains every decision and lists sidecars
Metrics v1
  All Technical metrics in AESTHETIC_Metric.md implemented and unit tested
Creative baseline
  Training from stills updates baseline and shifts Creative scores in a visible way
Selection
  Winners show diversity across scenes with dedupe enforced
UI
  Start job, see progress, inspect cards, download artifacts. No external server required
Export
  Frames and optional hero scenes playable. Contact sheet matches winners

---

## Known Risks To Track

  FFmpeg availability and codec variance
  Very high resolution sources causing memory spikes
  Scene detection thresholds on animation or hard cuts with flashes
  GPU models and drivers on mixed hardware

## Repository layout

```
.
aesthetic/
├─ webui/                     # local Web UI (primary interface)
│  └─ index.html              # Tailwind UI with tabs and local hooks
├─ app/                       # local processing pipeline
│  ├─ __init__.py
│  ├─ app.py                  # CLI entry: run pipeline, write outputs
│  ├─ config.py               # load config.yaml
│  ├─ log.py                  # logger factory
│  ├─ paths.py                # path helpers
│  ├─ scenes.py               # scene detection
│  ├─ sample.py               # candidate sampling
│  ├─ metrics.py              # cheap technical metrics
│  ├─ select.py               # per‑scene and global selection, dedupe
│  ├─ export.py               # frames, hero video, sidecars, manifest
│  └─ baseline.py             # golden baseline training and load
├─ data/                      # runtime data
│  ├─ uploads/                # incoming videos and stills
│  ├─ jobs/<id>/              # per job artifacts
│  │  ├─ manifest.json
│  │  ├─ shots.json
│  │  └─ heroes.mp4
│  └─ baseline/               # golden baseline store
│     └─ baseline.json
├─ scripts/                   # dev tools
│  └─ scaffold.ps1            # create folders and placeholders (local use)
├─ config.yaml.example        # starter config
├─ README.md
└─ AESTHETIC_Metric.md
```

---

## Requirements

- Python 3.12  
- FFmpeg installed and available on PATH

Python packages, first wave:
- opencv-python  
- numpy  
- pillow  
- tqdm  
- pyyaml  
- scikit-image  
- scipy  

Optional heavy:
- PyTorch CUDA builds  
- open-clip-torch


## Scoring pillars

- **Technical:** exposure, clipping, sharpness proxy, motion, composition proxies, and color statistics  
- **Creative:** stylistic adherence against reference profiles derived from Golden Samples  
- **Subjective:** human response models. starts with rule-based MOS, upgrades to learned models

The complete metrics inventory lives in `AESTHETIC_Metric.md`.

---


## Contributing

This project is being actively designed. Open issues with clear steps. Pull requests should include tests when possible and must keep determinism and always-write behavior intact. Read `AESTHETIC_Metric.md` for coverage and `server/models` for data contracts.

---

## FAQ

**Where is the metrics spec**  
`AESTHETIC_Metric.md` in the repo root.

**Does it require a GPU**  
No. GPU acceleration is optional. CLIP and heavy metrics can run on CPU.

---

## License

TBD
