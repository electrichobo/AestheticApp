# AESTHETIC metrics reconciliation (contrast + compare)

## evaluation tiers and pillars
- Tiers: Technical, Creative, Subjective — **covered**
- Core pillars: Exposure, Lighting, Composition, Camera Movement, Color — **covered**
- Extra bundles: Image Quality, Narrative/Aesthetic — **added** for completeness

---

## exposure
**From your spec**
- Histogram distribution (mean, median, std, skew, kurtosis)
- Clipping analysis (highlights and shadows)
- PSNR
- SSIM
- Third moment about 18 percent gray
- SNR for luminance and chroma
- Temporal exposure consistency
- Exposure intent match
- Perceived exposure quality MOS

**Roadmap status**
- Histogram distribution — **covered**
- Clipping analysis — **covered**
- PSNR — **planned opt in** when a true reference exists
- SSIM — **planned opt in** when a true reference exists
- Third moment about 18 percent gray — **covered**
- SNR (luma and chroma) — **planned**
- Temporal exposure consistency — **covered**
- Exposure intent match — **planned** (rule based first, then learned)
- Perceived exposure quality MOS — **planned**

**Action**
- Add SNR calc to Exposure bundle
- Ship v1 Exposure Intent classifier

---

## lighting
**From your spec**
- Dynamic range in stops
- Key to fill ratio
- Color temperature and deviation
- Shadow detail detection
- Shadow area noise
- Hard versus soft transition analysis
- Lighting coverage consistency across shots
- Light motivation (creative)
- Lighting style adherence (creative)
- Lighting mood effectiveness MOS (subjective)

**Roadmap status**
- Dynamic range proxy — **covered**
- Key to fill ratio — **covered**
- Color temperature estimate and deviation — **covered**
- Shadow detail detection — **covered**
- Shadow area noise — **planned**
- Hard versus soft transition — **covered**
- Lighting coverage consistency — **covered**
- Light motivation — **planned**
- Lighting style adherence — **planned**
- Lighting mood effectiveness MOS — **planned**

**Action**
- Add shadow zone SNR
- Implement simple Light Motivation heuristic

---

## composition
**From your spec**
- Rule of thirds adherence
- Face detection and placement
- Center of mass and balance
- Negative space ratio
- Depth of field in mm or feet
- Depth map separation
- Occupancy maps
- Symmetry or asymmetry score
- Headroom and lead room
- Shot scale classification
- Frame balance composite score
- Compositional creativity and motif tracking (creative)
- Aesthetic impression MOS (subjective)

**Roadmap status**
- Rule of thirds — **covered**
- Face detection and placement — **covered**
- Center of mass and balance — **covered**
- Negative space ratio — **covered**
- Depth of field absolute — **not practical without lens EXIF**
  We will use blur gradient and MiDaS separation as proxies — **planned**
- Depth map separation — **covered**
- Occupancy maps — **planned**
- Symmetry or asymmetry — **covered**
- Headroom and lead room — **covered**
- Shot scale classification — **planned** (heuristics now, ShotBench later)
- Frame balance composite — **covered**
- Compositional creativity and motif tracking — **planned**
- Aesthetic impression MOS — **planned**

**Action**
- Add occupancy maps
- Ship v1 shot scale classifier from face size

---

## camera movement
**From your spec**
- Optical flow foundation
- Motion smoothness and jerkiness
- Stabilization and micro jitter
- Motion blur amount
- Motion blur direction
- Movement type detection
- Shot duration
- Focus accuracy during movement
- Path trajectory analysis
- Movement motivation and impact on tension (creative)
- Movement effectiveness MOS (subjective)

**Roadmap status**
- Optical flow (Farneback) — **covered**
- Smoothness and jerkiness — **covered**
- Stabilization and micro jitter — **covered**
- Motion blur amount — **covered** via gradient spectrum proxy
- Motion blur direction — **planned** Radon based
- Movement type detection — **planned** rule based first
- Shot duration — **covered**
- Focus accuracy during movement — **planned**
- Path trajectory to spline — **planned**
- Movement motivation and impact on tension — **planned**
- Movement effectiveness MOS — **planned**

**Action**
- Add blur direction metric
- Add rule based movement type tagger

---

## color
**From your spec**
- White balance deviation and cross scene variance
- Saturation richness and uniformity in Lab
- Lab distributions and palette entropy
- Palette classification
- Color accuracy ΔE2000 vs chart or reference
- Skin tone accuracy ΔE
- Grading uniformity across shots
- Chroma noise in a* b*
- Banding detection like CAMBI
- Color temperature cross scene variance
- Palette emotional accuracy and style adherence (creative)
- Color aesthetic MOS (subjective)

**Roadmap status**
- WB deviation and variance — **covered**
- Saturation richness and uniformity — **covered**
- Lab distributions and entropy — **covered**
- Palette classification — **covered** now, labeled families **planned**
- Color accuracy ΔE2000 — **planned opt in** when you provide a chart or reference
- Skin tone ΔE — **planned**
- Grading uniformity — **covered**
- Chroma noise — **covered**
- Banding detection proxy — **covered** as gradient based proxy
- Color temperature cross scene variance — **covered**
- Palette emotional accuracy — **planned**
- Color style adherence — **planned**
- Color aesthetic MOS — **planned**

**Action**
- Add skin tone ΔE
- Add palette family labels and emotional mapping

---

## image quality bundle
**From your spec**
- Sharpness and resolution MTF proxy
- VMAF, PSNR, SSIM when reference exists
- Lens distortion percent
- Vignetting stops center to edge
- Chromatic aberration width
- Veiling glare and flare contrast loss
- Compression artifacts: blocking, banding, mosquito, ringing
- Texture detail retention on textured regions

**Roadmap status**
- Sharpness proxy — **covered** with Laplacian var and edge density. MTF proxy **planned**
- VMAF, PSNR, SSIM — **planned opt in** when a true reference exists
- Lens distortion proxy — **planned** via straight line detection
- Vignetting — **covered**
- Chromatic aberration width — **planned**
- Veiling glare and flare — **planned**
- Compression artifacts — **covered** with proxy detectors and **planned** to expand
- Texture detail retention — **planned** via local SSIM or high frequency masks

**Action**
- Add CA width detector and line based distortion proxy
- Keep VMAF and SSIM in the optional QC pack

---

## narrative and aesthetic
**From your spec**
- Visual storytelling effectiveness
- Cinematic techniques quality
- Audio visual richness
- Compelling degree MOS
- Memorability
- Attention time via eye tracking

**Roadmap status**
- Visual storytelling and technique quality — **planned** as learned classifiers aligned to gold labels
- Audio visual richness — **planned**
- Compelling degree MOS — **planned**
- Memorability predictor — **planned** using CLIP similarity plus aesthetic regressor
- Attention time — **not feasible without eye tracking**
  Substitute a **saliency consistency proxy** — **planned**

**Action**
- Add saliency consistency proxy as the stand in for attention

---

## implementation recommendations from your note
- Technical metrics as losses — acknowledged for future deep heads. For now used as features and calibration anchors.
- FilmEval and ShotBench alignment — **planned**
- Diverse datasets and expert annotations — **planned**
- Automated QC with VMAF, PSNR, SSIM, CAMBI, flow — **planned** as optional pack
- Creative assessment via reference databases and genre profiles — **planned**
- Scalability statement — **captured** in roadmap

---

## gaps to add to roadmap now
1. Exposure SNR and chroma SNR  
2. Exposure intent classifier v1  
3. Occupancy maps in Composition  
4. Shot scale classifier v1  
5. Motion blur direction metric  
6. Movement type tagger v1  
7. Skin tone ΔE and palette families  
8. Chromatic aberration width and lens distortion proxy  
9. Saliency consistency proxy for attention  
10. Optional QC pack for VMAF PSNR SSIM (off by default)

---

## acceptance updates
- Sidecars include raw and calibrated values for every metric marked covered or planned
- Config toggles for reference based QC pack and other optional metrics
- Manifest records calibration snapshot id and metric availability per frame
- Creative and Subjective placeholders stay zero weighted until data paths are ready
