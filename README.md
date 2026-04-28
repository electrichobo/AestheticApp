# AESTHETIC

AESTHETIC is a local desktop application for cinematographers and editors. It analyses raw footage, finds the strongest shots and short sequences, and exports hero stills, hero clips, contact sheets, EDLs, and scoring data — everything needed to build a selects package or showreel without sitting through the whole tape.

It runs entirely on your machine. No servers. No cloud. No subscription.

---

## What it does

You give it a video file. AESTHETIC breaks it into shots, measures everything measurable about every frame across seven scoring categories, compares those measurements against a corpus of award-winning cinematography, and selects the best shots. It then produces:

- A ranked contact sheet with thumbnails, scores, and timecodes
- Hero frames named with score prefix so they sort by quality in Explorer
- Trimmed hero clips via ffmpeg (opt-in)
- A CMX 3600 EDL importable into Premiere, Resolve, and Avid
- A timecoded CSV selects list
- A full run manifest JSON with every decision recorded

The pipeline in plain language:

1. **Ingest** — ffprobe reads video metadata: duration, fps, resolution, codec, colour space (primaries, transfer characteristic, matrix), log-encoding detection
2. **Scene detection** — multi-signal cut detection using pixel diff, quadrant comparison, SSIM, and optional CLIP embedding distance. Catches hard cuts, reverse angles, and coverage changes
3. **Sample** — extract candidate frames from each scene with seeded jitter for deterministic, even coverage
4. **Measure** — compute all metrics across seven categories per frame: exposure, lighting, composition, movement, colour, image quality, narrative
5. **Infer** — run CLIP/SigLIP for embeddings, MiDaS DPT_Hybrid for real depth maps, YOLO for subject detection and skin tone sampling
6. **Classify** — determine shot scale, movement type, scene type, and shot intent using inference results and multi-prompt CLIP zero-shot with rules-based fallback
7. **Aggregate** — collapse per-frame measurements into a single shot score. All computed metrics feed into scores — nothing is measured and ignored
8. **Score against baseline** — compare CLIP embeddings against the Golden Baseline corpus. This is the Creative pillar score. Also computes ΔE2000 colour accuracy vs D65 and vs the baseline colour distribution
9. **Select** — rank by combined score, deduplicate near-identical frames, apply duration weighting, run facility-location diversity selection
10. **Export** — frames, clips, contact sheet, EDL, CSV, manifest

---

## Scoring pillars

**Technical (50% default)** — objective pixel measurements. Every computed metric feeds into the score — exposure mean, tonal skew, SNR luma and chroma, PSNR, SSIM, dynamic range, key/fill ratio, rule of thirds, visual centre of mass, symmetry, depth separation (from real MiDaS depth maps), negative space, headroom, lead room, face placement (face-count weighted), optical flow consistency, jerkiness, motion blur range, trajectory smoothness, sharpness (Laplacian + edge density + MTF proxy), lens distortion, chromatic aberration, all four compression artifact types, texture retention, white balance deviation, saturation, palette entropy, colour accuracy ΔE2000.

**Creative (30% default)** — cosine similarity against the Golden Baseline corpus in embedding space. Measures how closely a shot resembles award-winning cinematography. Also computes ΔE2000 vs the baseline colour distribution to assess colour consistency with the reference corpus.

**Subjective (20% default)** — a narrative proxy combining saliency consistency and composite aesthetic appeal. The learned layer for human preference — hero-frame potency, memorability, and impact — is in active development and will replace this proxy as training data accumulates from user feedback.

All weights are configurable in `config.yaml`.

---

## The Golden Baseline

A curated, versioned corpus of frames and stills from Oscar-winning and ASC-awarded cinematography. Every candidate shot is compared against it. A high Creative pillar score means the shot resembles something the industry has already judged as excellent.

The baseline is a craft prior — a reference standard for what polished, high-level cinematography often looks like — not the sole arbiter of quality. Final ranking combines baseline similarity, technical measurements, diversity logic, and user feedback.

The baseline lives in `%LOCALAPPDATA%\AESTHETIC\data\baseline\` on Windows and the platform equivalent on macOS/Linux. It is versioned — every augmentation creates a new version, old ones are kept. Every analysis manifest records which baseline version produced its results so scores are always reproducible.

Build and expand the baseline from the Baseline section of the UI:
- **Train** — ingest a folder of reference stills to create or replace the baseline
- **Augment** — add new stills to an existing baseline without replacing it
- **Browse Reference Video** — ingest a full reference film frame-by-frame

All reference material passes a QC filter before ingestion: resolution check, widescreen aspect ratio check, subtitle/watermark detection, and non-cinematic content detection (solid-colour title cards and graphics).

---

## Shot classification

Every selected shot is classified for:

- **Shot scale** — extreme close through extreme wide, from YOLO detection size with CLIP zero-shot fallback
- **Movement type** — static / pan / tilt / dolly / handheld / unknown — prioritises metrics-engine result computed on consecutive frame pairs, then smoothness/stabilization signals, then optical flow consistency ratio
- **Scene type** — interior day / interior night / exterior day / exterior night — multi-prompt CLIP zero-shot with voting-based rules fallback using colour temperature, dynamic range, and saturation signals
- **Shot intent** — intimate / establishing / action / dialogue / transitional — CLIP zero-shot

Classifications feed the pillar interaction logic and narrative diversity constraints in selection.

---

## Colour analysis

When a shot's detail panel is expanded in the Matrix tab:

- **ΔE2000 vs D65** — perceptual colour distance from neutral daylight. Below 2 is imperceptible; above 10 is a strong colour cast
- **ΔE2000 vs Baseline** — how close this shot's colour is to the mean colour of the Golden Baseline corpus
- **Skin tone ΔE** — when YOLO detects a person, samples Lab values from the face region and computes ΔE2000 against Macbeth-derived skin tone references. Useful for detecting WB inconsistency across a shoot
- **CIE 1931 chromaticity diagram** — proper BGR→linear RGB→XYZ D65→xy conversion. Shows dominant colour clusters against sRGB, DCI-P3, and Rec.2020 gamut triangles with pixel-coverage-weighted dot sizes
- **Gamut coverage** — percentage of frame pixels inside each gamut triangle

If log-encoded footage is detected (S-Log, C-Log, Log-C, V-Log, PQ, HLG), a warning is shown in the log that ΔE values may not be meaningful without a display LUT applied first.

---

## Architecture

```
Video file or URL
    │
    ▼
Ingest (ffprobe + colour space detection)
    │
    ▼
Scene Detection (MAD + quadrant diff + SSIM + optional CLIP distance)
    │
    ▼
Candidate Sampling (seeded, deterministic)
    │
    ▼
Metrics Engine (7 categories, 50+ measurements, parallel CPU/GPU)
    │
    ▼
AI Inference
  ├─ CLIP/SigLIP embeddings (best available model auto-selected)
  ├─ MiDaS DPT_Hybrid depth maps (1 per scene, promotes to composition score)
  └─ YOLO detection + skin tone Lab sampling
    │
    ▼
Shot Classification (scale / movement / scene type / intent)
    │
    ▼
Aggregation (all metrics → CategoryScore per pillar)
    │
    ▼
Baseline Similarity + ΔE Colour Analysis + Gamut Coverage
    │
    ▼
Selection (rank → dedupe → duration filter → facility-location diversity)
    │
    ▼
Export (frames + clips + contact sheet + EDL + CSV + manifest)
```

Every stage reads a validated Pydantic model and returns one. Everything important is JSON-serialised to a per-job sidecar. Re-scoring after a baseline update reuses cached sidecars — inference does not re-run.

---

## Model selection

AESTHETIC auto-selects the best available vision model at startup. No configuration needed:

| Priority | Model | Dim | Notes |
|---|---|---|---|
| 1 | SigLIP ViT-SO400M-14-384 | 1152 | Best zero-shot accuracy |
| 2 | SigLIP ViT-SO400M-14 | 1152 | |
| 3 | CLIP ViT-L-14-336 | 768 | High-res input |
| 4 | CLIP ViT-L-14 | 768 | Reliable fallback |
| 5 | CLIP ViT-B-32 | 512 | Last resort |

GPU detection is also automatic: CUDA (any NVIDIA GPU) → MPS (Apple Silicon) → CPU. No specific GPU is assumed or required.

**Note:** embedding dimensions differ between model families. If you change models after training a baseline, the stored embeddings will be dimension-incompatible. Rebuild the baseline after any model family change.

---

## Repository layout

```
AestheticApp/
├── aesthetic/
│   ├── agents/
│   │   ├── model_utils.py       # model selection + device detection (single source of truth)
│   │   ├── ingest.py            # ffprobe → VideoMeta (incl. colour space)
│   │   ├── scenes.py            # multi-signal scene/cut detection
│   │   ├── sampling.py          # candidate frame extraction
│   │   ├── metrics.py           # per-frame metrics engine (50+ measurements)
│   │   ├── inference.py         # CLIP/SigLIP + MiDaS DPT_Hybrid + YOLO + skin tone
│   │   ├── classifier.py        # scale / movement / scene type / intent classification
│   │   ├── aggregation.py       # frame → shot score collapse + gamut data collection
│   │   ├── scoring.py           # three-pillar harmonised scorer
│   │   ├── selection.py         # ranking + facility-location diversity + dedupe
│   │   ├── export.py            # frames + clips + EDL + CSV + manifest
│   │   ├── baseline_trainer.py  # corpus ingestion from stills and video
│   │   └── stratification.py    # baseline clustering
│   ├── bridge/
│   │   └── api.py               # pywebview JS↔Python bridge
│   ├── config/
│   │   └── config.yaml          # all runtime settings
│   ├── models/
│   │   ├── job.py               # VideoMeta, Job, Scene, Shot, CandidateFrame
│   │   └── scores.py            # FrameMetrics, ShotScore, CategoryScore, Manifest
│   ├── webui/
│   │   └── index.html           # single-page UI (Results, Matrix, Log, Baseline, Corpus, Compare)
│   ├── app.py                   # pywebview boot shell
│   └── baseline.py              # BaselineStore — versioned corpus management
├── AESTHETIC_Metric.md          # complete metrics specification
├── README.md
└── requirements.txt
```

---

## Requirements

- Python 3.12
- FFmpeg on PATH
- Any CUDA GPU, Apple Silicon (MPS), or CPU

```bash
# NVIDIA GPU (any CUDA-capable card):
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 --no-cache-dir

# CPU only / Apple Silicon:
pip install torch torchvision --no-cache-dir

# Then everything else:
pip install -r requirements.txt --no-cache-dir
```

---

## Setup

```bash
git clone https://github.com/electrichobo/AestheticApp.git
cd AestheticApp
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 --no-cache-dir
pip install -r requirements.txt --no-cache-dir
python -m aesthetic.app
```

On first run, model weights download automatically and are cached in `~/.cache/torch/hub/` and the open_clip cache. Subsequent runs load from cache.

---

## Configuration

Key settings in `aesthetic/config/config.yaml`:

```yaml
scenes:
  threshold: 22.0              # MAD threshold — lower = more scene cuts detected
  min_scene_len_frames: 12

extract:
  per_scene_candidates: 9

selection:
  top_k: 10
  min_shot_duration_sec: 2.0
  soft_min_duration_sec: 1.0
  enforce_narrative_diversity: true

weights:
  technical:  0.50
  creative:   0.30
  subjective: 0.20

features:
  gpu_enabled:   true    # auto-detects CUDA → MPS → CPU, any GPU works
  clip_enabled:  true
  midas_enabled: true    # DPT_Hybrid, runs once per scene
  yolo_enabled:  true
```

---

## UI tabs

| Tab | Purpose |
|---|---|
| **Results** | Contact sheet — thumbnail left, scores right, category bars, T/C/S pillars, feedback buttons |
| **Matrix** | Full scoring table with T/C/S breakdown per category. Click any shot row to expand raw metric averages with plain-language descriptions, ΔE colour analysis, and CIE 1931 gamut chart |
| **Log** | Live pipeline progress |
| **Baseline** | Train, augment, and inspect the Golden Baseline corpus |
| **Corpus** | Browse baseline embeddings and statistics |
| **Compare** | Side-by-side run comparison |

---

## Exports

After every analysis job:

| File | Description |
|---|---|
| `frames/` | Hero frames, score-prefixed for sort order |
| `clips/` | Trimmed hero clips (opt-in checkbox above Find Best Shots) |
| `contact_sheet.jpg` | Tiled overview with rank, score, timecode |
| `*.edl` | CMX 3600 EDL — correct SMPTE timecodes, drop-frame aware, imports into Premiere / Resolve / Avid |
| `*_selects.csv` | Timecoded selects list with all scores and classifications |
| `*_manifest.json` | Full run record: decisions, baseline version, config snapshot, pipeline timing |

---

## FAQ

**Does it require a specific GPU?**
No. Any CUDA-capable NVIDIA GPU works. Apple Silicon MPS is also supported. CPU-only works but is slower.

**Does it need internet?**
Not for analysis. First run downloads model weights which are then cached locally. The optional VLM rationale feature calls an external API. Web URL ingestion uses yt-dlp which requires internet to download the video.

**I changed from ViT-B-32 to a larger model. Why are baseline scores empty?**
The new model produces embeddings with a different dimension. Delete the existing embeddings and retrain the baseline with the new model.

**What is log-encoded footage?**
Footage shot in a log gamma curve (S-Log, C-Log, Log-C, BRAW, etc.) where pixel values are not display-referred. AESTHETIC detects this from ffprobe metadata and warns you that ΔE colour accuracy values may not be meaningful without a display LUT applied first. All other metrics remain valid.

**Can I submit a full feature film?**
Yes. Processing time on a GPU is significant — plan for 30–60 minutes per feature. For baseline training this is a one-time cost.

**Where are the full metrics definitions?**
`AESTHETIC_Metric.md` in the repo root.

---

## Roadmap

### Phase 1 — Foundation *(next)*
- Feedback event schema and local persistence (thumbs up / neutral / down → pairwise preference log)
- Feature export pipeline for model training from cached metrics and embeddings
- Two-stage ranking: cheap broad sweep on all candidates, deep rerank on top 25% shortlist

### Phase 2 — Learned ranking
- Lightweight reranker (LightGBM / small MLP) trained on frozen features and feedback-derived pairwise preferences
- Hero clip extraction: best 2–6 second window per shot, +4 second buffer each side, scene-boundary aware
- Runtime mode presets: Fast / Balanced / Precision with device-aware model routing

### Phase 3 — Scene and sequence intelligence
- Scene cluster grouper: groups adjacent shots by embedding similarity, palette, subject continuity, scene-type labels
- Sequence scoring: crescendo detection, entrance quality, pairability, reel rhythm contribution
- Transition classifier: lightweight learned refinement on top of existing cut detector (hard cut / dissolve / fade / false positive)

### Phase 4 — Pillar expansion
- Technical: subject separation score, compression survivability, motion readability, focus stability, stronger artifact penalties
- Creative: style-family similarity (7 families: prestige naturalism, commercial, gritty handheld, fashion/editorial, music video, documentary vérité, horror/neo-noir), lighting signature, lensing character, colour-story coherence
- Subjective (learned): hero-frame potency, three-second impact, memorability, authorship/distinctiveness, reel diversity contribution

### Phase 5 — UX and explainability
- Progressive results display (preliminary rankings first, refined rankings after shortlist rerank)
- UI explainability: why a shot ranked highly, which sequence it belongs to, what style family it was scored against
- Annotation tool for transition classifier training data

---

## Contributing

- All baseline reads/writes go through `BaselineStore` in `baseline.py`
- All UI calls go through `aesthetic/bridge/api.py`
- All model/device selection goes through `aesthetic/agents/model_utils.py`
- Every pipeline stage produces a validated Pydantic model
- Deterministic everywhere — explicit seeds, stable sorting
- Keep stage contracts JSON-serialisable and versioned

---

## License

TBD