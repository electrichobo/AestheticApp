# AESTHETIC — Development Handoff

## Repository
- GitHub: https://github.com/electrichobo/AestheticApp
- Local: `E:\AestheticApp\`
- Python 3.12, venv at `E:\AestheticApp\.venv\`
- GPU: RTX 3090, CUDA 13.1 (torch cu128 build)

## What AESTHETIC Is
Local desktop app (Python + pywebview/WebView2) that analyzes video files and ranks shots against a Golden Baseline of award-winning cinematography. Scores shots across Technical, Creative, and Subjective pillars. Primary use case: DP showreel assembly, dailies review, portfolio selection. No servers, fully local. Windows x64.

---

## Current Git State
Latest commit: `f8d22cc` — Suppress all console windows: runtime hook patches Popen globally; TF env vars before DeepFace

### Recent commits (most relevant)
```
f8d22cc Suppress all console windows: runtime hook patches Popen globally
da47f8e Fix PowerShell windows: CREATE_NO_WINDOW; scope layout Luma|Parade|CIE left, text right
0e0412d Fix scopes layout: 160x160 inline with CIE, fixed pixel size
681b3d7 Fix: pywebview built-in file dialog; blob video preview; scopes grid layout
336b582 Remove debug console; add baseline seed on first run; console=False in spec
247e345 Fix JS SyntaxError: replace backslash regex with split/join
f2e36e6 Clean app.py: http_server=True, raw file path for pywebview bridge
```

---

## Architecture

```
Ingest → Scenes → Candidates → Metrics → Stage1 Inference (SigLIP+YOLO) →
Stage1 Aggregate → Shortlist (top 25%) → Stage2 Inference (MiDaS on shortlist) →
Full Aggregate → Classification → Scoring → Scene Clustering → Selection → Export → Manifest
```

## File Structure
```
aesthetic/
├── agents/
│   ├── model_utils.py         # model/device selection + runtime presets
│   ├── ingest.py              # ffprobe metadata + scene detection prep
│   ├── scenes.py              # PySceneDetect + transition classification
│   ├── sampling.py            # ffmpeg frame extraction
│   ├── metrics.py             # 70+ measurements across 9 categories
│   ├── inference.py           # SigLIP + MiDaS + YOLO + focus + subject/emotion
│   ├── classifier.py          # CPU ViT-B-32 for scale/scene/intent
│   ├── aggregation.py         # ALL metrics + waveform histogram data + mean_embedding
│   ├── scoring.py             # pillar weighting
│   ├── selection.py           # content filter + shot selection
│   ├── export.py              # manifest + clip export
│   ├── baseline_trainer.py    # SigLIP embedding corpus builder
│   ├── stratification.py      # style cluster similarity + visual labelling + percentile
│   ├── two_stage.py           # two-stage ranking scaffold
│   ├── feedback_store.py      # SQLite feedback events + pairwise derivation
│   ├── feature_export.py      # training feature CSV export
│   ├── hero_clip.py           # best-window finder + clip extraction with handles
│   ├── scene_clusters.py      # agglomerative cosine clustering of selected shots
│   └── transition_classifier.py  # LightGBM transition type classifier
├── bridge/api.py              # pywebview JS↔Python bridge (all API methods)
├── config/__init__.py         # DATA_DIR resolution, load_config()
├── config/config.yaml         # all runtime config
├── models/job.py              # Scene, Candidate, Job models
├── models/scores.py           # FrameMetrics, ShotScore, CategoryScore etc.
├── webui/index.html           # single-page UI (all HTML/CSS/JS)
├── app.py                     # pywebview boot + _seed_baseline_if_needed
├── baseline.py                # BaselineStore
└── data/
    ├── transition_model.pkl   # bundled LightGBM transition classifier
    └── baseline/              # seed embeddings for bundle distribution
        ├── embeddings/        # *.json SigLIP 1152-dim embeddings
        └── golden/            # baseline version manifests

AESTHETIC.spec                 # PyInstaller spec (Windows x64)
build.bat                      # build script
hooks/
├── hook-open_clip.py
├── hook-ultralytics.py
└── rthook_suppress_console.py # runtime hook: patches Popen to suppress console windows
tools/
└── ffmpeg.exe                 # place here before building
```

---

## Key Technical Details

### Model Cascade
- Primary GPU: SigLIP ViT-SO400M-14-SigLIP-384 (1152-dim embeddings)
- CPU classifier: ViT-B-32/openai (512-dim) — used for text classification only
- Depth: MiDaS DPT_Hybrid
- Detection: YOLOv8n
- Emotion: DeepFace (FER2013 backend, CPU-forced in bundle)
- Transition: LightGBM (57 features, 5 classes, bundled at `aesthetic/data/transition_model.pkl`)

### Scoring Architecture
- Technical (50%): 9 category scores from pixel metrics
- Creative (30%): SigLIP baseline similarity + style-family percentile rank
- Subjective (20%): SigLIP zero-shot (thumbnail, portfolio, mood, presence) + DeepFace emotion
- Reranker: stubbed, waiting on 50+ feedback pairs

### Style-Family Creative Scoring (Phase 4)
- `_analyse_cluster_visuals()` samples source images, computes luma/sat/DR/temp stats
- `_label_from_visual_stats()` maps to 16 named families (Prestige Naturalism, Neo-Noir, etc.)
- `sim_stats` stored at build time (P10/P25/P50/P75/P90) for percentile scoring
- `style_family` + `cluster_percentile` on ShotScore, surfaced in UI as indigo badge

### Scene Clustering (Phase 3)
- `aesthetic/agents/scene_clusters.py`
- Agglomerative single-linkage, cosine distance threshold 0.35
- Primary: SigLIP mean_embedding per shot; Secondary: palette chromaticity (15%); Soft: scene_type/scale bonus (8%)
- UI: colour-coded badges per cluster (C1★, C2...), cluster summary panel above results
- `mean_embedding` computed in `aggregation.py:_compute_mean_embedding()`, stored on ShotScore
- CRITICAL FIX: `scene_candidate_map` must be rebuilt AFTER inference (done in bridge/api.py ~line 1151)

### Hero Clip Extraction (Phase 2b)
- `aesthetic/agents/hero_clip.py`
- `score_frame()`: weights sharpness, eye_sharpness, subject_focus, thumbnail_strength, portfolio_potential, emotion, saliency
- `find_best_window()`: 2–6s sliding window, 0.25s steps, longer window bonus
- Transition-aware handles: hard cuts clamp to boundary; dissolves/fades allow 50% bleed
- ffmpeg stream copy → H.264 CRF18 fallback
- Output filename: `{rank:02d}_{score:05.1f}_{shot_id}_win{window_score:.0f}.mp4`

### Transition Classifier
- LightGBM, 57 temporal features, 5 classes: hard_cut, dissolve, fade_black, fade_white, wipe
- 100% CV accuracy, 5000 clips
- Bundled at `aesthetic/data/transition_model.pkl`
- Wired into `detect_scenes()` — classifies all boundaries automatically

### Runtime Presets
- `detect_preset()`: CUDA ≥8GB→balanced, <8GB→fast, MPS→balanced, CPU→fast
- Applied in `analyze()` with safe try/except fallback
- UI dropdown: Auto/Fast/Balanced/Precision

### Waveform/Parade Scopes
- Backend: `_col_histogram()` — 100-bucket IRE histogram per column (64 cols × 100 buckets)
- Renderer: `Math.pow(density, 0.45) * 0.85` sqrt opacity curve — true density look
- Layout: [5px margin] [Luma 160×160] [5px] [RGB Parade 160×160] [5px] [CIE 160×160] [text right]
- Canvas internal res: 320×160 (2× for sharpness), styled at 160×160px

### Baseline Queue
- `queue_baseline_videos(paths)` → sequential processing in background thread
- Cluster rebuild once at end (not per-file)
- UI: + Add Video to Queue, Run Queue, Clear, progress log panel

### Content Filter
- `_is_non_cinematic()` reads from `score.metric_detail` dict (NOT CategoryScore attributes)
- Pure black (`hist_mean < 12`) → instant `return True`
- Dark+flat compound: `mean < 30 AND std < 18` → `flags += 2`
- All metric reads via `_v(dict, key)` helper

---

## ShotScore Fields (models/scores.py)
All fields relevant to know about:
```python
mean_embedding:     Optional[List[float]]   # L2-normalised SigLIP mean for clustering
style_family:       Optional[str]           # e.g. "Prestige Naturalism"
cluster_percentile: Optional[float]         # 0-100 percentile within style family
gamut_coverage:     Optional[Dict]
dominant_colours:   Optional[List]
per_frame_colours:  Optional[List]          # per-frame CIE xy clusters
waveform:           Optional[List]          # 64 cols × 100 buckets IRE histogram
parade_r/g/b:       Optional[List]          # same format per channel
```

### selection.py output dict includes:
`mean_embedding`, `style_family`, `cluster_percentile`, `dominant_colours`,
`per_frame_colours`, `waveform`, `parade_r`, `parade_g`, `parade_b`,
`cluster_id`, `is_representative`

### bridge/api.py UI shot dict includes:
`styleFamily`, `clusterPct`, `clusterId`, `isRepresentative`,
`perFrameColours`, `waveform`, `paradeR`, `paradeG`, `paradeB`

---

## Packaging Status

### PyInstaller Bundle
- Spec: `AESTHETIC.spec` — Windows x64, `console=False`
- Runtime hook: `hooks/rthook_suppress_console.py` — patches `subprocess.Popen` globally to add `CREATE_NO_WINDOW` on Windows
- `app.py:_seed_baseline_if_needed()` — copies bundled 1152-dim embeddings to `%LOCALAPPDATA%\AESTHETIC\data\baseline\` on first run if no valid baseline exists
- WebView2 bridge: `http_server=True`, raw file path to index.html
- Video preview in bundle: blob URL via `get_video_data()` (base64, 50MB limit)
- File dialog: `self._window.create_file_dialog()` — pywebview native, no PowerShell

### Known Bundle Issues
- ~~PowerShell/console windows during analysis~~ — **FIXED** via `hooks/rthook_suppress_console.py` runtime hook (patches `subprocess.Popen` globally)
- Baseline seeding: baseline embeddings must be copied into `aesthetic/data/baseline/embeddings/` before building (requires manual step — retrain in dev, copy to repo)
- Train (new) button: fixed — was referencing non-existent `baselineStatus` DOM element

### Build Command
```powershell
cd E:\AestheticApp
.venv\Scripts\Activate.ps1
.\build.bat
dist\AESTHETIC\AESTHETIC.exe
```

### Pre-Build Checklist
1. Delete stale 512-dim embeddings: `Remove-Item "$env:LOCALAPPDATA\AESTHETIC\data\baseline\embeddings\*" -Force`
2. Retrain baseline in dev: `python -m aesthetic.app` → Baseline tab → Train (new) with `E:\goldtrainer`
3. Copy embeddings to repo: `Copy-Item "$env:LOCALAPPDATA\AESTHETIC\data\baseline\embeddings\*" "aesthetic\data\baseline\embeddings\"`
4. Commit embeddings: `git add aesthetic/data/baseline/ && git commit -m "Bundle baseline embeddings"`
5. Build: `.\build.bat`

---

## Roadmap Status

| Phase | Status | Notes |
|---|---|---|
| Phase 1 — Feedback + two-stage | ✅ | feedback_store.py, feature_export.py, two_stage.py |
| Phase 1.5 — 70+ metrics | ✅ | FocusMetrics, SubjectMetrics, all new fields |
| Phase 2a — Runtime presets | ✅ | detect_preset(), PRESETS dict, UI dropdown |
| Phase 2b — Hero clip extraction | ✅ | hero_clip.py fully wired |
| Phase 2c — Reranker | ⏳ | Needs 50+ feedback pairs; SQLite accumulating |
| Transition classifier | ✅ | Bundled, 100% CV accuracy |
| Phase 3 — Scene clustering | ✅ | scene_clusters.py, UI badges + panel |
| Phase 4 — Style-family scoring | ✅ | stratification.py, visual labels, percentile |
| Packaging | 🔧 | Functional, console windows being fixed |
| Phase 5 — Reranker training | 🔲 | After feedback accumulates |

---

## Pre-Packaging Known Issues (README)
- **Waveform/parade rendering**: histograms compute correctly, rendering is functional but not pixel-perfect scope quality. Noted in README for post-v1 fix.

---

## Data Locations
- User data: `%LOCALAPPDATA%\AESTHETIC\data\`
- Baseline embeddings: `%LOCALAPPDATA%\AESTHETIC\data\baseline\embeddings\` (1152-dim JSON)
- Jobs output: `%LOCALAPPDATA%\AESTHETIC\data\jobs\`
- Feedback SQLite: `%LOCALAPPDATA%\AESTHETIC\data\feedback.db`
- Torch model cache: `C:\Users\Jared\.cache\torch\hub\`
- Open CLIP model cache: `C:\Users\Jared\.cache\huggingface\`

---

## Configuration (config.yaml key sections)
```yaml
clustering:
  distance_threshold: 0.35
  palette_weight:     0.15
  semantic_bonus:     0.08
clip_export:
  handle_sec:  4.0
  min_dur:     2.0
  max_dur:     6.0
selection:
  shortlist_pct: 0.25
  top_k: 10
features:
  gpu_enabled: true
  midas_enabled: true
  clip_enabled: true
  yolo_enabled: true
```

---

## Immediate Next Steps (in priority order)
1. **Move bundle to secondary machine** — augment baseline corpus with ~100 feature films using the baseline queue; let it run overnight
2. **Return bundle to primary** — copy augmented `%LOCALAPPDATA%\AESTHETIC\data\baseline\` back, seed into repo, final build
3. **Distribution** — zip `dist\AESTHETIC\`, write install notes (WebView2 runtime required on target machine)
4. **Reranker** — per-user, not bundled; accumulates from normal use via thumbs up/down; train when individual user has 50+ pairwise pairs

## What Is Complete
- Full analysis pipeline with 70+ metrics
- Style-family Creative scoring with percentile ranking
- Scene clustering with visual similarity
- Hero clip extraction with transition-aware handles
- Transition classifier bundled
- Runtime presets
- Baseline augment queue
- Feedback store (reranker data accumulating passively)
- Bundle: bridge, file dialog, video preview, scope layout, no console windows
- Baseline seeded into bundle for first-run

---

## Critical Bug Patterns to Watch For
- `'dict' object has no attribute X` — selected shots are dicts, not models. Use `.get("field")`
- `'CategoryScore' object has no attribute X` — raw metrics live in `score.metric_detail["category"]["field"]`, not on CategoryScore
- `_preset` NameError — resolve_preset() called before assignment in analyze()
- `mixed/missing embeddings` in clustering — scene_candidate_map rebuilt before aggregation, after inference
- JS bridge not connecting — http_server=True required; any JS SyntaxError kills entire JS execution
- Backslash regex `/\\/g` crashes WebView2 strict parser — use `split('\\\\').join('/')` instead
