# AESTHETIC

AESTHETIC is a local desktop application that finds and ranks the best shots in a video against a standard of cinematic excellence derived from Oscar-winning and ASC-awarded cinematography. You give it a video. It gives you back the shots most worth keeping, explained and ready for an editor to use.

It runs entirely on your machine. No servers. No cloud. No subscription.

> Current status: core pipeline complete through Phase 10. Scoring intelligence improvements in progress.

---

## What it actually does

You submit a video file or a web URL. AESTHETIC breaks the video into scenes, samples candidate frames from each, measures everything measurable about every frame, compares those measurements against a corpus of award-winning cinematography, and selects the best shots. It then exports a contact sheet, timecoded clips, an EDL for your NLE, and a CSV — everything an editor needs to start building a selects package or showreel without sitting through the whole tape.

The pipeline in plain English:

1. **Ingest** — read the video's metadata via ffprobe (duration, fps, resolution, codec)
2. **Scene detection** — step through frames detecting cuts using pixel diff + quadrant comparison + SSIM. Multi-signal so it catches reverse angles and coverage changes, not just hard cuts
3. **Sample** — extract N candidate frames from each scene with seeded jitter so sampling is deterministic and even
4. **Measure** — compute every metric in `AESTHETIC_Metric.md` for every candidate frame across seven categories: exposure, lighting, composition, movement, color, image quality, narrative
5. **Infer** — run CLIP to generate an embedding for each frame, MiDaS for depth, YOLO for subject detection
6. **Classify** — determine shot scale, movement type, scene type, and shot intent using the inference results
7. **Aggregate** — collapse per-frame measurements into a single score per shot. Temporal variance is an explicit signal — a shot inconsistent across its duration scores lower
8. **Score against baseline** — compare each shot's CLIP embedding against the Golden Baseline corpus via cosine similarity. This is the Creative pillar score
9. **Select** — rank shots by combined score, filter title cards and graphics, apply duration weighting, run facility location selection to maximise both quality and diversity
10. **Export** — hero frames, trimmed clips, contact sheet, EDL with correct SMPTE timecodes, CSV timecode list, full manifest JSON

---

## The Golden Baseline

This is the heart of the system. A curated, versioned corpus of frames and stills from Oscar-winning and ASC-awarded cinematography. Every candidate shot is compared against it. A high Creative pillar score means the shot resembles something the industry has already judged as excellent.

It is not personal taste. It is not trainable per-user. It is an objective standard derived from the best work in the field.

The baseline lives in `aesthetic/data/baseline/`. It is versioned — every time you add new material a new version is created and old ones are kept. Every analysis manifest records which baseline version produced its results so scores are always reproducible.

Build and expand the baseline from the Advanced section of the UI:
- **Train (new)** — ingest a folder of reference stills to create an initial baseline
- **Augment** — add new stills to an existing baseline without replacing it
- **Browse Reference Video** — ingest a full reference film. Runs the complete pipeline on it to extract frames with full metrics including motion data. Always augments, never replaces

All reference material passes a QC filter before ingestion — aspect ratio check, subtitle detection, non-cinematic content detection, and upscale detection. Anything that looks like a title card, watermark, or artificially processed image is rejected before it can pollute the corpus.

---

## The scoring pillars

**Technical (50% default)** — objective pixel math. Measures whether the shot was executed correctly. Sharpness, exposure, noise, motion stability, color accuracy.

**Creative (30% default)** — cosine similarity against the Golden Baseline in CLIP embedding space. Measures how closely this shot resembles award-winning work. Intentional stylistic deviation is handled by tunable delta curves.

**Subjective (20% default)** — what the industry has collectively responded to emotionally and artistically, as encoded in the baseline corpus. This is the pillar that allows cinematography to be an art form. A technically perfect shot that is emotionally empty should not score the same as one that is both technically sound and aesthetically powerful.

All weights are configurable in `config.yaml`.

---

## What gets exported

After every analysis job, the output folder contains:

- **`frames/`** — hero frames named with score prefix so they sort by quality in Explorer
- **`clips/`** — trimmed hero scene clips via ffmpeg stream copy with accurate in/out timecodes
- **`contact_sheet.jpg`** — tiled overview of all selected shots with rank, score, and timecode annotations
- **`<stem>_<job_id>.edl`** — CMX 3600 EDL using your actual source frame rate with correct drop-frame handling for 29.97/59.94. Importable into Premiere, Resolve, and Avid
- **`<stem>_selects.csv`** — timecode list with all scores and classifications per shot
- **`<stem>_<job_id>_manifest.json`** — full run record: every decision explained, baseline version hash, config snapshot, pipeline timing

---

## Shot classification

Every selected shot is classified for:

- **Shot scale** — extreme close through extreme wide. YOLO person detection size with CLIP zero-shot and rule-based fallbacks
- **Movement type** — static / pan / tilt / dolly / handheld / drone. From optical flow signals
- **Scene type** — interior day / interior night / exterior day / exterior night. CLIP zero-shot
- **Shot intent** — intimate / establishing / action / dialogue / transitional. CLIP zero-shot

Classifications are stamped on every shot in the manifest, EDL comments, and CSV. They also feed the pillar interaction logic and narrative diversity constraints in selection.

---

## Architecture

```
Video file or URL
    │
    ▼
Ingest → Scene Detection → Candidate Sampling → Metrics Engine
    │
    ▼
AI Inference (CLIP + MiDaS + YOLO) → Shot Classification
    │
    ▼
Shot Aggregation → Baseline Similarity Scoring
    │
    ▼
Selection (rank → dedupe → duration filter → non-cinematic filter → facility location)
    │
    ▼
Export (frames + clips + contact sheet + EDL + CSV + manifest)
```

Every stage reads a validated Pydantic model and returns one. Everything important is JSON-serialised to a per-job sidecar. Re-scoring after a baseline update reuses cached sidecars — inference does not re-run.

---

## Repository layout

```
AestheticApp/
├── aesthetic/
│   ├── agents/
│   │   ├── ingest.py            # ffprobe → VideoMeta
│   │   ├── scenes.py            # multi-signal scene detection
│   │   ├── sampling.py          # candidate frame extraction
│   │   ├── metrics.py           # per-frame metrics engine (7 categories)
│   │   ├── inference.py         # CLIP + MiDaS + YOLO + VLM
│   │   ├── classifier.py        # shot scale / movement / scene / intent
│   │   ├── aggregation.py       # frame → shot score collapse
│   │   ├── selection.py         # ranking + diversity + dedupe + duration
│   │   ├── export.py            # frames + clips + EDL + CSV + manifest
│   │   └── baseline_trainer.py  # corpus ingestion from stills and video
│   ├── bridge/
│   │   └── api.py               # canonical pywebview JS bridge
│   ├── config/
│   │   └── config.yaml          # all runtime settings
│   ├── data/                    # runtime data (gitignored)
│   │   ├── baseline/
│   │   │   ├── embeddings/      # per-still CLIP embedding files
│   │   │   └── golden/          # versioned golden snapshots
│   │   └── jobs/<job_id>/
│   │       ├── frames/          # candidate frames
│   │       ├── metrics/         # FrameMetrics JSON sidecars
│   │       ├── depth/           # MiDaS depth maps
│   │       ├── scenes.json
│   │       ├── candidates.json
│   │       ├── shots.json
│   │       └── manifest.json
│   ├── models/
│   │   ├── job.py               # VideoMeta, Job, Scene, Shot, CandidateFrame
│   │   └── scores.py            # FrameMetrics, ShotScore, CategoryScore, Manifest
│   ├── webui/
│   │   └── index.html           # single-page UI
│   ├── app.py                   # pywebview boot shell only
│   └── baseline.py              # BaselineStore — versioned corpus management
├── outputs/                     # exported deliverables (gitignored)
├── AESTHETIC_Metric.md          # complete metrics specification
├── README.md
└── requirements.txt
```

---

## Requirements

- Python 3.12
- FFmpeg on PATH
- NVIDIA GPU recommended — CPU-only works but is slower

```bash
# Install torch with CUDA first (RTX 30xx series / CUDA 12.8):
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 --no-cache-dir

# Then everything else:
pip install -r requirements.txt --no-cache-dir
```

---

## Setup

```bash
git clone https://github.com/electrichobo/AestheticApp.git
cd AestheticApp
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 --no-cache-dir
pip install -r requirements.txt --no-cache-dir
python -m aesthetic.app
```

---

## Configuration

Key settings in `aesthetic/config/config.yaml`:

```yaml
scenes:
  threshold: 22.0              # MAD threshold — lower = more cuts detected
  min_scene_len_frames: 12

extract:
  per_scene_candidates: 9

selection:
  top_k: 10
  min_shot_duration_sec: 2.0   # score penalty below this
  soft_min_duration_sec: 1.0   # hard exclude below this

weights:
  technical:  0.50
  creative:   0.30
  subjective: 0.20

features:
  clip_enabled: true
  midas_enabled: true
  yolo_enabled: true
  vlm_rationale_enabled: false
  gpu_enabled: true
```

---

## What is still coming

**Scoring intelligence (in progress)**
- Pillar interaction logic — a creatively excellent but technically imperfect shot should outrank a technically average shot that is also creatively average
- Baseline stratification — cluster the corpus by visual style so Creative scores compare like-for-like
- Narrative diversity constraints — ensure final picks span shot scales and intent types

**Editor feedback (planned)**
- Thumbs up/down on shot cards, persisted across sessions, resettable

**UX improvements (planned)**
- Richer contact sheet annotations — scale icon, movement type, strongest category per tile
- Baseline corpus browser — see what the Golden Baseline actually looks like visually
- Run comparison — compare two analysis runs side by side

---

## FAQ

**What is the Golden Baseline?**
A curated corpus of frames from Oscar and ASC award-winning films. The reference standard everything is scored against. Not personal taste — objective cinematic excellence.

**Does it require a GPU?**
No. Everything runs on CPU. A GPU makes it significantly faster.

**Does it need internet?**
Not for analysis. The VLM rationale feature (optional) calls an external API. Web URL ingestion uses yt-dlp which needs internet to download the video.

**Why shots and not frames?**
A shot is a duration with an in-point and out-point — what an editor actually needs. Hero frames are thumbnails only.

**Can I submit a full feature film?**
Yes. Processing time on a GPU is significant — plan for 30-60 minutes per feature. For baseline training this is a one-time cost.

**Where are the metrics?**
`AESTHETIC_Metric.md` in the repo root.

---

## Contributing

- All baseline reads/writes go through `BaselineStore` in `baseline.py`
- All UI calls go through `aesthetic/bridge/api.py`
- Every pipeline stage produces a validated Pydantic model
- Deterministic everywhere — explicit seeds, stable sorting
- Keep stage contracts JSON-serialisable and versioned

---

## License

TBD