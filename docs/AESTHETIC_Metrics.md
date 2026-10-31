# AESTHETIC — Metrics Specification

This document is the single source of truth for every metric AESTHETIC computes.
Each metric belongs to one of seven categories and is scored across three pillars.
If something is listed here it is either implemented, a known stub, or explicitly deferred.
If it is not listed here it is not being measured.

---

## The three pillars

Every category score breaks into three pillars combined using weights from `config.yaml`.

**Technical** — objective, reproducible pixel measurements. Does not care what the shot is supposed to look like, only whether it was executed correctly. Sharpness, clipping, noise, flow consistency — these are facts about the image. Default weight: 50%.

**Creative** — how closely this shot resembles award-winning cinematography. Measured by comparing the shot's embedding against the Golden Baseline corpus via cosine similarity. A high Creative score means the shot looks like something the industry has already judged excellent. A low score means it diverges — which could be bad execution or intentional style. Default weight: 30%.

**Subjective** — the learned human-preference layer. Currently a rule-based proxy combining saliency consistency and composite aesthetic appeal. Will be replaced by trained reranker heads (hero-frame potency, three-second impact, memorability, authorship/distinctiveness) as user feedback data accumulates. Default weight: 20%.

All weights are configurable in `config.yaml`.

---

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Implemented — computing real values, feeding into scores |
| 🟨 | Partial — computed but using a proxy, or computed but not yet in scoring |
| ⏱ | Video-only — not available from stills, populated when reference video is ingested |
| 🎯 | Scoring output — computed at scoring time against the baseline, not a raw measurement |
| 🔮 | Future — requires a learned model or training data not yet built |
| ❌ | Not practical — acknowledged, substituted, or out of scope |

---

## Exposure

*Duck test: is this frame correctly exposed, or is it blown out, crushed, or flat?*

| Metric | Status | Feeds into score | Notes |
|---|---|---|---|
| Histogram mean | ✅ | ✅ | Midtone placement — rewards values near 118 |
| Histogram median | ✅ | 🟨 | Available in detail panel, not in pillar score |
| Histogram std | ✅ | ✅ | Tonal spread — rewards full-range use |
| Histogram skew | ✅ | ✅ | Penalises extreme dark or bright skew |
| Histogram kurtosis | ✅ | 🟨 | Available in detail panel |
| Highlight clipping % | ✅ | ✅ | Pixels at or above 250/255 |
| Shadow clipping % | ✅ | ✅ | Pixels at or below 5/255 |
| PSNR | ✅ | ✅ | Proxy vs Gaussian-smoothed self |
| SSIM | ✅ | ✅ | Structural integrity vs smoothed self |
| Third moment about 18% gray | ✅ | 🟨 | Zone V deviation — available, not yet in pillar score |
| SNR luma | ✅ | ✅ | Signal-to-noise via local patch variance |
| SNR chroma | ✅ | ✅ | SNR on Lab a*/b* channels |
| Temporal exposure consistency | ⏱ | ✅ | Std of histogram mean across shot frames |
| Exposure intent | ✅ | ✅ | Rule-based: penalises clipping, rewards tonal spread |

---

## Lighting

*Duck test: is the lighting doing something intentional and doing it well?*

| Metric | Status | Feeds into score | Notes |
|---|---|---|---|
| Dynamic range in stops | ✅ | ✅ | Log₂ of p2–p98 luminance range |
| Key to fill ratio | ✅ | ✅ | Bright zone mean vs shadow zone mean |
| Colour temperature (Kelvin) | ✅ | ✅ | Blue/red channel ratio proxy |
| Colour temperature deviation | ✅ | ✅ | Delta from 5600K neutral |
| Shadow detail | ✅ | ✅ | Mean luminance in shadow zone |
| Shadow noise | ✅ | ✅ | Std of gray values in shadow zone |
| Light transition hardness | ✅ | ✅ | Gradient magnitude variance — hard vs soft light |
| Light motivation | ✅ | ✅ | Quadrant luminance variance — directional = motivated |
| Coverage consistency | ⏱ | ❌ | Cross-shot variance — video only, not yet implemented |
| Lighting style adherence | 🎯 | 🎯 | Creative pillar delta vs baseline — future |

---

## Composition

*Duck test: is the frame organised to draw the eye to the right place?*

| Metric | Status | Feeds into score | Notes |
|---|---|---|---|
| Rule of thirds | ✅ | ✅ | Edge density near thirds lines |
| Frame balance | ✅ | ✅ | COM proximity to thirds power points |
| Visual centre of mass X | ✅ | ✅ | Scores nearness to 0.33 or 0.67 |
| Visual centre of mass Y | ✅ | ✅ | Scores nearness to upper-third placement |
| Negative space ratio | ✅ | ✅ | % of frame below median luminance — 20–60% ideal |
| Depth separation | ✅ | ✅ | **Primary: MiDaS DPT_Hybrid depth map score** (sharpness diff fallback when MiDaS disabled) |
| Occupancy map score | ✅ | ✅ | % of frame with content above background threshold |
| Symmetry score | ✅ | ✅ | Left vs mirror-flipped pixel difference |
| Headroom | ✅ | ✅ | Proportion of frame above luminance COM — 15–35% ideal |
| Lead room | ✅ | ✅ | Horizontal COM distance from center |
| Face placement | ✅ | ✅ | Thirds proximity score for detected faces |
| Face count | ✅ | ✅ | Weights face_placement — more faces = stronger weight |
| Shot scale | ✅ | ✅ | YOLO person size → scale label; CLIP zero-shot fallback |

---

## Camera movement

*Duck test: is the camera moving with intention and control, or just shaky?*

| Metric | Status | Feeds into score | Notes |
|---|---|---|---|
| Optical flow mean | ✅ | ✅ | Farneback dense flow magnitude |
| Optical flow std | ✅ | ✅ | Inverted — high variance = inconsistent movement penalty |
| Smoothness | ✅ | ✅ | Inverse of jerkiness |
| Jerkiness | ✅ | ✅ | Spatial variance of flow — inverted in scoring |
| Stabilisation | ✅ | ✅ | Residual micro-jitter after global motion removal |
| Motion blur amount | ✅ | ✅ | High-frequency energy ratio — rewards 10–40 range (180° shutter) |
| Motion blur direction | ✅ | 🟨 | Dominant gradient orientation — available, not yet in pillar score |
| Movement type | ✅ | ✅ | Priority: metrics-engine result → smoothness/stabilisation → flow consistency ratio |
| Shot duration | ⏱ | 🟨 | Derived from scene boundaries — field exists |
| Focus during movement | ✅ | ✅ | Subject-region sharpness relative to motion magnitude |
| Trajectory smoothness | ✅ | ✅ | Single-frame: 100; sequence: flow path smoothness |

**Movement type classification priority:**
1. `movement_type` from metrics engine (computed on consecutive frame pairs — most reliable)
2. Smoothness and stabilisation signals (available even on first frame)
3. Optical flow consistency ratio (`flow_std / flow_mean`) — >0.85 = handheld, <0.6 = dolly
4. Static threshold: flow mean < 1.5 px/frame

---

## Colour

*Duck test: does this frame have a consistent, intentional colour story?*

| Metric | Status | Feeds into score | Notes |
|---|---|---|---|
| White balance deviation | ✅ | ✅ | Euclidean distance of Lab a*/b* means from neutral |
| Saturation mean (Lab chroma) | ✅ | ✅ | Mean √(a²+b²) — rewards 20–60 range |
| Saturation uniformity | ✅ | ✅ | 100 minus std of chroma |
| Palette entropy | ✅ | ✅ | Hue histogram entropy — rewards intentional colour complexity |
| Palette family | ✅ | 🟨 | warm / cool / desaturated / dark / bright / neutral — used for display, not yet in pillar score |
| Colour accuracy ΔE2000 vs D65 | ✅ | ✅ | Full Sharma 2005 ΔE2000 formula. Compares mean scene Lab against D65 neutral at same luminance. <2 imperceptible, 2–5 subtle cast, >10 strong |
| Colour accuracy ΔE2000 vs Baseline | ✅ | ✅ | Reconstructed from corpus colour_temp_kelvin and wb_deviation statistics |
| Skin tone ΔE2000 | ✅ | ✅ | When YOLO detects a person: samples Lab values from upper 25% of bounding box (head region), finds closest Macbeth-derived reference (fair → deep), computes ΔE2000. Reports cross-shoot WB inconsistency |
| Chroma noise | ✅ | ✅ | Mean std of Lab a*/b* channels |
| Banding detection | ✅ | ✅ | Periodic gradient step proxy |
| Gamut coverage (sRGB / P3 / Rec.2020) | ✅ | 🟨 | BGR→linear RGB→XYZ D65→xy chromaticity. Point-in-triangle test against gamut primaries. Shown in CIE 1931 diagram — not yet in pillar score |
| WB cross-scene variance | ⏱ | ❌ | Video only, not yet implemented |
| Colour temp cross-scene variance | ⏱ | ❌ | Video only, not yet implemented |
| Grading uniformity | ⏱ | ❌ | Video only, not yet implemented |

**Log-encoding detection:** `VideoMeta.is_log_encoded` detects S-Log, C-Log, Log-C, V-Log, Log316, PQ, HLG from ffprobe `color_transfer` metadata. A warning is shown in the UI when log footage is detected — ΔE values are only meaningful on display-referred (graded) footage.

---

## Image quality

*Duck test: is this a technically clean image, or has something degraded it?*

| Metric | Status | Feeds into score | Notes |
|---|---|---|---|
| Sharpness — Laplacian variance | ✅ | ✅ | Higher = sharper edges |
| Sharpness — edge density | ✅ | ✅ | % of pixels detected as edges |
| MTF proxy | ✅ | ✅ | High-frequency vs low-frequency energy ratio in FFT |
| Texture retention | ✅ | ✅ | Local Laplacian variance on high-frequency mask |
| Lens distortion | ✅ | ✅ | Hough straight-line deviation proxy — inverted in scoring |
| Vignetting stops | ✅ | ✅ | Corner vs center brightness ratio |
| Chromatic aberration width (px) | ✅ | ✅ | Channel misalignment at high-contrast edges |
| Flare / veiling glare | ✅ | ✅ | Overexposed pixel % at frame edges |
| Compression blocking | ✅ | ✅ | DCT 8-pixel boundary artifact |
| Compression banding | ✅ | ✅ | Periodic gradient step in smooth regions |
| Compression mosquito noise | ✅ | ✅ | High-frequency noise near edges |
| Compression ringing | ✅ | ✅ | High-pass oscillation std at edges |
| VMAF / PSNR / SSIM (QC pack) | 🟨 | ❌ | Optional, off by default, requires reference frame |

---

## Narrative and aesthetic

*Duck test: is this a shot that grabs attention and makes you feel something?*

| Metric | Status | Feeds into score | Notes |
|---|---|---|---|
| Saliency consistency | ✅ | ✅ | OpenCV spectral residual concentration — measures strength of focal point |
| Compelling MOS | ✅ | ✅ | Rule-based composite: sharpness × exposure balance × contrast |
| Visual storytelling effectiveness | 🔮 | 🔮 | Needs learned classifier — field defined in model |
| Cinematic technique quality | 🔮 | 🔮 | Needs learned classifier — field defined in model |
| Memorability | 🔮 | 🔮 | CLIP + aesthetic regressor — field defined in model |
| Hero-frame potency | 🔮 | 🔮 | Probability a human would choose this as representative still |
| Three-second impact | 🔮 | 🔮 | How strongly a short clip reads in first few seconds |
| Authorship / distinctiveness | 🔮 | 🔮 | Distinctiveness relative to candidate pool |
| Reel diversity contribution | 🔮 | 🔮 | How much new value this shot adds to already selected material |

---

## Shot classification

Computed alongside metrics and used to apply intent-appropriate scoring weights and diversity constraints.

| Classification | Method | Status |
|---|---|---|
| Shot scale | YOLO person size → scale label; CLIP zero-shot fallback; rules fallback | ✅ |
| Movement type | Metrics engine `movement_type` → smoothness/stabilisation → flow consistency ratio | ✅ |
| Scene type | Multi-prompt CLIP zero-shot (3 prompts per class, averaged) with voting rules fallback using colour temp, DR, and saturation | ✅ |
| Shot intent | CLIP zero-shot — intimate / establishing / action / dialogue / transitional | ✅ |

**Scene type voting signals (rules fallback):**
- Colour temp > 6500K → 2 exterior votes; < 3800K → 2 interior votes
- Dynamic range > 11 stops → 2 exterior votes (strong sunlight)
- Saturation > 45 Lab chroma → 1 exterior vote
- Requires majority of votes — no longer defaults to exterior when data is missing

---

## AI model inference

Stored in every frame sidecar. Used by scoring and selection pipeline.

| Output | Model | Embedding dim | Status |
|---|---|---|---|
| Vision embedding | Best available (auto-selected at runtime) | 512 / 768 / 1152 | ✅ |
| Depth map + depth separation score | MiDaS DPT_Hybrid | — | ✅ |
| Object and person detections | YOLOv8n | — | ✅ |
| Skin tone Lab sampling | From YOLO face regions (upper 25% of person bbox) | — | ✅ |
| NIMA aesthetic score | — | — | 🔮 |
| LAION aesthetic score | — | — | 🔮 |
| VLM rationale text | Claude / GPT-4o (optional, requires API key) | — | 🟨 |

**Model selection cascade (best available at runtime):**

| Priority | Model | Pretrained | Embedding dim |
|---|---|---|---|
| 1 | ViT-SO400M-14-SigLIP-384 | webli | 1152 |
| 2 | ViT-SO400M-14-SigLIP | webli | 1152 |
| 3 | ViT-L-14-336 | openai | 768 |
| 4 | ViT-L-14 | openai | 768 |
| 5 | ViT-B-32 | openai | 512 |

The best model available in the installed `open_clip` is selected automatically. No configuration required. `model_utils.py` is the single source of truth for all model and device selection.

**GPU detection:** CUDA (any NVIDIA GPU) → MPS (Apple Silicon) → CPU. Auto-detected, no specific GPU required.

**Embedding dimension note:** Baseline embeddings are stored at the dimension of whichever model was used to train them. Switching model families (e.g. ViT-B-32 → ViT-L-14) produces incompatible dimensions. Rebuild the baseline after any model family change.

**MiDaS depth:** Runs on one frame per scene (not every candidate frame) for performance. The computed depth separation score is promoted directly into `CompositionMetrics.depth_separation`, replacing the Laplacian proxy for that shot. Laplacian remains as fallback when MiDaS is disabled.

---

## Colour analysis detail

### ΔE2000 computation (Sharma 2005)

Full CIEDE2000 formula is implemented in `aesthetic/agents/metrics.py::_compute_delta_e2000`. Inputs are CIE Lab values in centred form (neutral = 0, 0 — not OpenCV's 128, 128 encoding). The function handles the full a′ adjustment, hue-angle computation, weighting functions SL/SC/SH, and the RT rotation term.

**ΔE2000 vs D65 neutral** — compares mean scene Lab against a neutral grey at the same luminance (a*=0, b*=0). Measures the strength of any colour cast in the frame.

**ΔE2000 vs Baseline** — reconstructed from the corpus `color_temp_kelvin` and `wb_deviation` statistics stored in the Golden Baseline. Colour temperature is mapped to approximate Lab a*/b* hue angle using a linear approximation of the D65 daylight locus.

### Skin tone references (Macbeth-derived)

| Label | L | a* | b* |
|---|---|---|---|
| Fair | 73.0 | 14.0 | 17.0 |
| Light | 65.0 | 16.0 | 18.0 |
| Medium | 55.0 | 18.0 | 16.0 |
| Medium-dark | 45.0 | 17.0 | 13.0 |
| Dark | 35.0 | 13.0 | 9.0 |
| Deep | 25.0 | 9.0 | 6.0 |

The closest reference is selected by luminance distance. ΔE2000 is computed between the sampled face region and the matched reference. Values are averaged across all detected persons in the shot.

### CIE 1931 gamut chart

Rendered per shot in the Matrix tab detail panel. Computation: BGR → linear RGB (sRGB gamma removal) → XYZ D65 (IEC 61966-2-1 matrix) → xy chromaticity. Pixels are downsampled to 32×32 per frame before conversion for speed. 8 dominant colour clusters are extracted via k-means in xy space. Gamut coverage percentages are computed via point-in-triangle test against the known primary xy coordinates for sRGB, DCI-P3, and Rec.2020.

---

## Corpus QC filter

Every reference still and video frame passes this before ingestion into the Golden Baseline. Rejection requires **all three** conditions simultaneously (not a flag count — this prevents over-rejection of legitimately desaturated or high-contrast cinematic images):

1. **Near-zero chroma** — mean Lab chroma < 3 units (truly achromatic, not just a desaturated grade)
2. **Spatially flat** — Laplacian std < 8 (essentially no edge complexity — a solid-colour fill)
3. **Tonally flat** — luminance std < 12 (near-uniform brightness — no meaningful tonal variation)

Additional filters (each can independently reject):
- Resolution below 480×270
- Non-widescreen aspect ratio (narrower than 1.2:1)
- Subtitle/watermark: high horizontal edge density in the lower 20% of frame
- Suspect upscale: very high Laplacian variance with low texture retention

---

## Frame sidecar schema

Every candidate frame gets a JSON sidecar at `jobs/<job_id>/metrics/<frame_id>.json` containing:
- All metric values across all seven categories
- All inference outputs (embedding vector, depth map path, MiDaS depth separation score, YOLO detections, skin tone ΔE)
- Shot classification results
- `metrics_version` field for schema versioning

Sidecars are cached. Re-scoring with a new baseline version reuses them — inference does not re-run.

---

## What is still missing and why

**Video-only metrics** — `coverage_consistency`, `wb_cross_scene_variance`, `color_temp_cross_scene_variance`, `grading_uniformity`, `shot_duration_sec` all require multiple frames in temporal context. These fields exist in the model and will be populated as reference films are ingested.

**VMAF** — requires a reference video for comparison. Optional QC pack, disabled by default.

**Learned Subjective heads** — hero-frame potency, memorability, three-second impact, authorship/distinctiveness all require training data. The feedback event logger (Phase 1 of the roadmap) will begin accumulating this data from user selects.

**Transition classifier** — a lightweight learned refinement for the existing cut detector (hard cut / dissolve / fade / false positive). Training dataset compilation is in progress.

**Style-family Creative scoring** — the corpus currently compares against a single global baseline. Style-family clustering (prestige naturalism, gritty handheld, documentary vérité, etc.) will enable within-style Creative scores as an additional signal alongside global baseline similarity.

**Gamut coverage in pillar score** — the CIE 1931 gamut computation and coverage percentages are computed and displayed in the Matrix tab but not yet included in the colour category score. Will be added once the display-referred vs log-encoded distinction is handled more robustly.