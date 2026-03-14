# AESTHETIC metrics reconciliation (contrast + compare)

## evaluation tiers and pillars
- Pillars Technical, Creative, Subjective 

---

## exposure

- Histogram distribution (mean, median, std, skew, kurtosis)
- Clipping analysis (highlights and shadows)
- PSNR
- SSIM
- Third moment about 18 percent gray
- SNR for luminance and chroma
- Temporal exposure consistency
- Exposure intent match
- Perceived exposure quality MOS
- Histogram distribution 
- Clipping analysis   
- PSNR 
- SSIM
- Third moment about 18 percent gray
- SNR (luma and chroma)
- Temporal exposure consistency 
- Exposure intent match (rule based first, then learned)
- Perceived exposure quality MOS

**Action**
- Add SNR calc to Exposure bundle
- Ship v1 Exposure Intent classifier

---

## lighting

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
- Dynamic range
- Key to fill ratio 
- Color temperature estimate and deviation
- Shadow detail detection 
- Shadow area noise 
- Hard versus soft transition 
- Lighting coverage consistency
- Light motivation
- Lighting style adherence 
- Lighting mood effectiveness MOS

**Action**
- Add shadow zone SNR
- Implement simple Light Motivation heuristic

---

## composition

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
- Rule of thirds 
- Face detection and placement 
- Center of mass and balance 
- Negative space ratio
- Depth of field absolute — **not practical without lens EXIF**
  We will use blur gradient and MiDaS separation as proxies
- Depth map separation
- Occupancy maps
- Symmetry or asymmetry 
- Headroom and lead room
- Shot scale classification (heuristics now, ShotBench later)
- Frame balance composite 
- Compositional creativity and motif tracking
- Aesthetic impression MOS

**Action**
- Add occupancy maps
- Ship v1 shot scale classifier from face size

---

## camera movement

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
- Optical flow (Farneback)
- Smoothness and jerkiness
- Stabilization and micro jitter
- Motion blur amount via gradient spectrum proxy
- Motion blur direction Radon based
- Movement type detection rule based first
- Shot duration
- Focus accuracy during movement
- Path trajectory to spline
- Movement motivation and impact on tension
- Movement effectiveness MOS

**Action**
- Add blur direction metric
- Add rule based movement type tagger

---

## color

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
- WB deviation and variance
- Saturation richness and uniformity
- Lab distributions and entropy
- Palette classification now, labeled families
- Color accuracy ΔE2000 when you provide a chart or reference
- Skin tone ΔE
- Grading uniformity
- Chroma noise
- Banding detection proxy as gradient based proxy
- Color temperature cross scene variance
- Palette emotional accuracy
- Color style adherence
- Color aesthetic MOS

**Action**
- Add skin tone ΔE
- Add palette family labels and emotional mapping

---

## image quality bundle

- Sharpness and resolution MTF proxy
- VMAF, PSNR, SSIM when reference exists
- Lens distortion percent
- Vignetting stops center to edge
- Chromatic aberration width
- Veiling glare and flare contrast loss
- Compression artifacts: blocking, banding, mosquito, ringing
- Texture detail retention on textured regions
- Sharpness proxy with Laplacian var and edge density. MTF proxy
- VMAF, PSNR, SSIM when a true reference exists
- Lens distortion proxy via straight line detection
- Vignetting
- Chromatic aberration width
- Veiling glare and flare
- Compression artifacts
- Texture detail retention via local SSIM or high frequency masks

**Action**
- Add CA width detector and line based distortion proxy
- Keep VMAF and SSIM in the optional QC pack

---

## narrative and aesthetic

- Visual storytelling effectiveness
- Cinematic techniques quality
- Audio visual richness
- Compelling degree MOS
- Memorability
- Attention time via eye tracking

**Roadmap status**
- Visual storytelling and technique quality as learned classifiers aligned to gold labels
- Audio visual richness
- Compelling degree MOS
- Memorability predictor using CLIP similarity plus aesthetic regressor
- Attention time — **not feasible without eye tracking**
  Substitute a **saliency consistency proxy**

**Action**
- Add saliency consistency proxy as the stand in for attention

---

## implementation recommendations
- Technical metrics as losses — acknowledged for future deep heads. For now used as features and calibration anchors.
- FilmEval and ShotBench alignment
- Diverse datasets and expert annotations
- Automated QC with VMAF, PSNR, SSIM, CAMBI, flow as optional pack
- Creative assessment via reference databases and genre profiles
- Scalability statement — **captured** in roadmap

---

## gaps to add
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
