# AESTHETIC — Metrics Specification

This document is the single source of truth for every metric AESTHETIC computes.
Each metric belongs to one of seven categories and is scored across three pillars.
If something is in here it is either implemented, in progress, or explicitly deferred.
If it is not in here it is not being measured.

---

## The three pillars

Every category score is broken into three pillars combined using weights from `config.yaml`.

**Technical** — objective, math-based measurements. Reproducible. Does not care what the shot is supposed to look like, only whether it is executed correctly. Sharpness, clipping, noise, optical flow — these are facts about the image.

**Creative** — how closely this shot resembles award-winning cinematography. Measured by comparing the shot's CLIP embedding against the Golden Baseline corpus via cosine similarity. A high creative score means the shot looks like something the industry has already judged excellent. A low score means it diverges — which could be bad execution or intentional style. Delta curves handle this distinction.

**Subjective** — what the industry has collectively agreed is emotionally and artistically effective, encoded in the Golden Baseline corpus plus aesthetic predictor model signals. This pillar allows cinematography to be an art form and not a mathematical proof. Weighted lower than Technical and Creative but not zero.

Default weights: Technical 50%, Creative 30%, Subjective 20%. All configurable.

---

## Status legend

- ✅ implemented and computing real values
- 🟨 partially implemented or using a proxy
- ⏱ video-only — not available from stills, populated when reference video is ingested
- 🎯 scoring output — computed at scoring time against the baseline, not a raw measurement
- 🔮 future — requires a learned model not yet built
- ❌ not practical — acknowledged and substituted

---

## Exposure

The duck question: is this frame correctly exposed, or is it blown out, crushed, or flat?

| Metric | Status | Notes |
|---|---|---|
| Histogram mean, median, std, skew, kurtosis | ✅ | Five separate fields |
| Highlight clipping % | ✅ | Pixels at or above 250/255 |
| Shadow clipping % | ✅ | Pixels at or below 5/255 |
| PSNR | ✅ | Proxy vs Gaussian-smoothed self |
| SSIM | ✅ | Structural integrity vs smoothed self |
| Third moment about 18% gray | ✅ | Zone V deviation |
| SNR luma | ✅ | Signal-to-noise via local patch variance |
| SNR chroma | ✅ | SNR on Lab a* b* channels |
| Temporal exposure consistency | ⏱ | Std of histogram mean across shot frames |
| Exposure intent match | ✅ | Rule-based: penalises clipping, rewards histogram spread |
| Perceived exposure quality MOS | 🎯 | Subjective pillar, from baseline distribution |

---

## Lighting

The duck question: is the lighting doing something intentional and doing it well?

| Metric | Status | Notes |
|---|---|---|
| Dynamic range in stops | ✅ | Log2 of p2-p98 luminance range |
| Key to fill ratio | ✅ | Bright zone mean vs shadow zone mean |
| Color temperature (Kelvin) | ✅ | Blue/red channel ratio proxy |
| Color temperature deviation | ✅ | Delta from 5600K neutral |
| Shadow detail detection | ✅ | Mean luminance in shadow zone |
| Shadow area noise | ✅ | Std of gray values in shadow zone |
| Hard vs soft transition | ✅ | Gradient magnitude variance |
| Lighting coverage consistency | ⏱ | Cross-shot variance — video only |
| Light motivation | ✅ | Quadrant luminance variance — directional = motivated |
| Lighting style adherence | 🎯 | Creative pillar delta vs baseline |
| Lighting mood effectiveness MOS | 🎯 | Subjective pillar |

---

## Composition

The duck question: is the frame organised to draw the eye to the right place?

| Metric | Status | Notes |
|---|---|---|
| Rule of thirds adherence | ✅ | Edge density near thirds lines |
| Face detection and placement | ✅ | Haar cascade + thirds proximity score |
| Face count | ✅ | Number of detected faces |
| Center of mass X and Y | ✅ | Luminance-weighted centroid, normalised 0-1 |
| Negative space ratio | ✅ | % of frame below median luminance |
| Depth of field absolute | ❌ | Requires lens EXIF. Substituted with depth proxy |
| Depth separation proxy | ✅ | Laplacian pyramid ratio (MiDaS at inference) |
| Occupancy map score | ✅ | % of frame with content above background |
| Symmetry / asymmetry score | ✅ | Left vs flipped-right pixel diff |
| Headroom | ✅ | Proportion of frame above luminance COM |
| Lead room | ✅ | Horizontal COM distance from center |
| Shot scale classification | ✅ | YOLO person size → scale, CLIP zero-shot fallback |
| Frame balance composite | ✅ | COM proximity to rule-of-thirds power points |
| Compositional creativity | 🎯 | Creative pillar |
| Aesthetic impression MOS | 🎯 | Subjective pillar |

---

## Camera movement

The duck question: is the camera moving with intention and control, or just shaky?

| Metric | Status | Notes |
|---|---|---|
| Optical flow mean and std | ✅ | Farneback dense flow magnitude |
| Smoothness | ✅ | Inverse of jerkiness |
| Jerkiness | ✅ | Spatial variance of flow magnitude |
| Stabilization | ✅ | Residual micro-jitter after global motion removal |
| Motion blur amount | ✅ | High-frequency energy ratio in FFT |
| Motion blur direction | ✅ | Dominant gradient orientation via Radon proxy |
| Movement type detection | ✅ | Rule-based: static/pan/tilt/dolly/handheld/drone |
| Shot duration | ⏱ | Derived from scene boundaries — video only |
| Focus accuracy during movement | ✅ | Sharpness relative to motion magnitude |
| Path trajectory | ✅ | Single-frame always 100; sequence: flow path smoothness |
| Movement motivation | 🎯 | Creative pillar |
| Movement effectiveness MOS | 🎯 | Subjective pillar |

---

## Color

The duck question: does this frame have a consistent, intentional color story?

| Metric | Status | Notes |
|---|---|---|
| White balance deviation | ✅ | Euclidean distance of Lab a* b* means from zero |
| WB cross-scene variance | ⏱ | Std of WB deviation across shot — video only |
| Saturation mean (Lab chroma) | ✅ | Mean sqrt(a²+b²) |
| Saturation uniformity | ✅ | 100 minus std of chroma |
| Palette entropy | ✅ | Hue histogram entropy |
| Palette family | ✅ | warm / cool / desaturated / dark / bright / neutral |
| Color accuracy ΔE2000 | ⚠️ | Requires color chart reference |
| Skin tone ΔE | ⚠️ | Requires reference |
| Grading uniformity | ⏱ | Cross-shot WB and palette consistency — video only |
| Chroma noise | ✅ | Mean std of Lab a* b* channels |
| Banding detection | ✅ | Periodic gradient step proxy |
| Color temp cross-scene variance | ⏱ | Video only |
| Palette emotional accuracy | 🎯 | Creative pillar |
| Color aesthetic MOS | 🎯 | Subjective pillar |

---

## Image quality

The duck question: is this a technically clean image, or has something degraded it?

| Metric | Status | Notes |
|---|---|---|
| Sharpness — Laplacian variance | ✅ | Higher = sharper |
| Sharpness — edge density | ✅ | % of pixels detected as edges |
| MTF proxy | ✅ | High-frequency energy ratio in FFT |
| VMAF / PSNR / SSIM (QC pack) | 🟨 | Optional, off by default, requires reference |
| Lens distortion | ✅ | Hough straight-line detection proxy |
| Vignetting stops | ✅ | Corner vs center brightness ratio |
| Chromatic aberration width | ✅ | Channel misalignment at edges |
| Veiling glare and flare | ✅ | Overexposed pixel % at frame edges |
| Compression blocking | ✅ | DCT 8-pixel boundary artifact |
| Compression banding | ✅ | Periodic gradient step |
| Compression mosquito | ✅ | High-frequency noise near edges |
| Compression ringing | ✅ | High-pass oscillation std |
| Texture detail retention | ✅ | Local Laplacian variance on high-frequency mask |

---

## Narrative and aesthetic

The duck question: is this a shot that grabs attention and makes you feel something?

| Metric | Status | Notes |
|---|---|---|
| Visual storytelling effectiveness | 🔮 | Needs learned classifier — field exists in model |
| Cinematic technique quality | 🔮 | Needs learned classifier — field exists in model |
| Audio-visual richness | ❌ | Audio not in scope — future placeholder only |
| Compelling degree MOS | ✅ | Rule-based: sharpness × exposure × contrast |
| Memorability | 🔮 | CLIP + aesthetic regressor — field exists in model |
| Saliency consistency | ✅ | OpenCV spectral residual concentration proxy |

---

## Shot classification

Not metrics in the traditional sense but computed alongside metrics and used to apply intent-appropriate scoring weights and diversity constraints.

| Classification | Method | Status |
|---|---|---|
| Shot scale | YOLO person size, CLIP zero-shot fallback, rules fallback | ✅ |
| Movement type | Optical flow signals already in metrics | ✅ |
| Scene type | CLIP zero-shot — interior/exterior, day/night | ✅ |
| Shot intent | CLIP zero-shot — intimate/establishing/action/dialogue/transitional | ✅ |

---

## AI model inference outputs

Stored in every frame sidecar. Used by scoring and selection pipeline.

| Output | Model | Status |
|---|---|---|
| CLIP embedding (512-dim) | ViT-B-32 / OpenAI | ✅ |
| Depth map | MiDaS small | ✅ |
| Object and person detections | YOLOv8n | ✅ |
| NIMA aesthetic score | — | 🔮 |
| LAION aesthetic score | — | 🔮 |
| VLM rationale text | Claude / GPT-4o | ✅ optional |

---

## Corpus QC filter

Every reference still and video frame passes this before ingestion. Rejected if three or more signals fail:

- Minimum resolution: 480×270
- Aspect ratio: widescreen (wider than 1.2:1)
- Non-cinematic: low entropy + low saturation + flat histogram = title card / logo
- Subtitle detection: high horizontal edge density in lower 20% of frame
- Suspect sharpness: very high Laplacian variance + low texture retention = upscaled image

---

## What a frame sidecar contains

Every candidate frame gets `jobs/<job_id>/metrics/<frame_id>.json` containing all metric values, all inference outputs, shot classification, and a `metrics_version` field. Sidecars are cached — re-scoring with a new baseline reuses them rather than re-running inference.

---

## What is still missing and why

**Video-only metrics from stills baseline** — populated as reference films are added. Grows richer over time.

**Skin tone ΔE and color accuracy ΔE2000** — require a color chart or reference. Optional fields in the model, not computed by default.

**VMAF** — requires reference video. Optional QC pack, off by default.

**Learned classifiers for storytelling and technique** — need human-annotated training data. Future work.

**Baseline stratification** — the corpus compares against the global average. Style family clustering is next — it will make Creative scores compare like-for-like rather than against everything at once.