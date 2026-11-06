// AESTHETIC Frontend Controller
// Real-time Broadcast Scopes, Real Frame Decoding, & Cinematographic Intelligence

const canvas = document.getElementById('scope-canvas');
const ctx = canvas ? canvas.getContext('2d') : null;
let currentScope = 'waveform';
let currentScopesData = null;
let currentEvaluateData = null;
let currentTakes = [];
let activeTakeIndex = 0;
let currentTime = 16.0;
let currentInTime = 14.2;
let currentOutTime = 18.7;
let videoDuration = 60.0;
let vectorscopeZoom = 2.5; // Broadcast 2.5x zoom so natural cinematic chroma fills graticule

if (canvas) {
  canvas.addEventListener('click', () => {
    if (currentScope === 'vectorscope') {
      const levels = [1.0, 2.0, 2.5, 4.0];
      const curIdx = levels.indexOf(vectorscopeZoom);
      vectorscopeZoom = levels[(curIdx + 1) % levels.length];
      renderCurrentScope();
    }
  });
}

// Scope switching
document.querySelectorAll('.scope-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.scope-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    currentScope = tab.dataset.scope;
    renderCurrentScope();
  });
});

// Format seconds into SMPTE timecode (24fps)
function formatTimecode(sec, fps = 24) {
  if (sec == null || isNaN(sec)) sec = 0;
  const totalFrames = Math.max(0, Math.round(sec * fps));
  const frames = totalFrames % fps;
  const totalSec = Math.floor(totalFrames / fps);
  const s = totalSec % 60;
  const m = Math.floor(totalSec / 60) % 60;
  const h = Math.floor(totalSec / 3600);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}:${String(frames).padStart(2, '0')}`;
}

// Fetch live scopes, evaluation, and update picture frame from Rust backend
async function fetchFrameData(timeSec) {
  try {
    currentTime = timeSec;

    // 1. Immediately update master viewport frame image
    const frameImg = document.getElementById('viewport-frame-img');
    if (frameImg && activeViewportMode === 'picture') {
      frameImg.src = `/api/frame?time=${timeSec.toFixed(2)}&_t=${Date.now()}`;
      frameImg.style.display = 'block';
    }

    const [scopesRes, evalRes] = await Promise.all([
      fetch(`/api/scopes?time=${timeSec.toFixed(2)}`),
      fetch(`/api/evaluate?time=${timeSec.toFixed(2)}`)
    ]);

    if (scopesRes.ok) {
      currentScopesData = await scopesRes.json();
      renderCurrentScope();
    }

    if (evalRes.ok) {
      currentEvaluateData = await evalRes.json();
      updateEvaluationUI(currentEvaluateData);
    }

    updateViewportOverlay();
    updateTimelineUI();
  } catch (err) {
    console.warn('Backend polling error:', err);
  }
}

// Update the Cinematographic Matrix UI (Pillars, Visual Æesthetic, Forensics)
function updateEvaluationUI(resData) {
  if (!resData) return;
  const data = resData.take || resData;

  // 1. Pillar Scores
  if (data.scores) {
    const overall = Math.round(data.scores.overall || 0);
    const tech = Math.round(data.scores.technical || 0);
    const creat = Math.round(data.scores.creative || 0);
    const temp = Math.round(data.scores.temporal || 0);

    const badge = document.getElementById('overall-score-badge');
    if (badge) badge.textContent = `${overall} / 100`;

    const techFill = document.getElementById('tech-fill');
    const techVal = document.getElementById('tech-val');
    if (techFill) techFill.style.width = `${tech}%`;
    if (techVal) techVal.textContent = tech;

    const creatFill = document.getElementById('creat-fill');
    const creatVal = document.getElementById('creat-val');
    if (creatFill) creatFill.style.width = `${creat}%`;
    if (creatVal) creatVal.textContent = creat;

    const tempFill = document.getElementById('temp-fill');
    const tempVal = document.getElementById('temp-val');
    if (tempFill) tempFill.style.width = `${temp}%`;
    if (tempVal) tempVal.textContent = temp;
  }

  // 2. Visual Æesthetic: Golden Baseline (184 Award-Winning Cinema Films) Comparison
  const styleTagsFlow = document.getElementById('style-tags-flow');
  const masterText = document.getElementById('master-text');
  const dpBadge = document.getElementById('benchmark-dp-badge');

  const comp = resData.golden_baseline_benchmark || resData.stylistic_similar || resData.comparison;
  if (comp) {
    const alignScore = Math.min(100, Math.max(0, Math.round(comp.alignment_pct ?? comp.similarity ?? 88)));
    if (dpBadge) {
      dpBadge.textContent = `Award Cinema Baseline: ${alignScore}%`;
    }
    if (masterText) {
      const family = comp.style_family || data.style?.style_family || 'Prestige Naturalism';
      const ancillary = comp.ancillary_dp
        ? ` • Ancillary DP Affinity: ${comp.ancillary_dp}`
        : (comp.dp_name ? ` • Ancillary DP Affinity: ${comp.dp_name} (${comp.reference_film})` : '');
      masterText.textContent = `Golden Baseline (184 Oscar / ASC / BSC Films) — ${family}${ancillary}`;
    }

    // Populate discovered stylistic & physical craft tags
    if (styleTagsFlow) {
      styleTagsFlow.innerHTML = '';
      const tags = (comp.comparison_tags && comp.comparison_tags.length > 0) ? comp.comparison_tags : [
        data.style?.lighting_key || 'Low-Key Chiaroscuro',
        data.style?.motion_type || 'Smooth Camera Move',
        data.style?.shot_scale || 'Medium Close-Up',
        data.style?.style_family || 'Prestige Naturalism'
      ];
      tags.forEach(t => {
        if (!t) return;
        const span = document.createElement('span');
        span.className = 'style-tag';
        span.textContent = t;
        styleTagsFlow.appendChild(span);
      });
    }

    // Populate Golden Baseline Benchmark Table (Objective, Non-Judgmental Distribution Deltas)
    const tableBody = document.getElementById('benchmark-table-body');
    if (tableBody && comp.rows) {
      tableBody.innerHTML = '';
      comp.rows.forEach(r => {
        const tr = document.createElement('tr');
        let deltaClass = 'delta-match';
        const st = (r.status || '').toLowerCase();
        if (st.includes('less') || st.includes('steeper') || st.includes('softer') || st.includes('subdued') || st.includes('short-sided')) {
          deltaClass = 'delta-negative';
        } else if (st.includes('higher') || st.includes('lower') || st.includes('extended') || st.includes('crisper') || st.includes('prominent')) {
          deltaClass = 'delta-variant';
        }

        tr.innerHTML = `
          <td><strong>${r.metric}</strong></td>
          <td style="font-family: var(--font-mono);">${r.shot_val}</td>
          <td style="font-family: var(--font-mono); color: var(--text-muted);">${r.target_val}</td>
          <td><span class="delta-tag ${deltaClass}">${r.status}</span></td>
        `;
        tableBody.appendChild(tr);
      });
    }
  }

  // 3. Technical Concerns & Forensics
  const concernsList = document.getElementById('concerns-list');
  if (concernsList) {
    concernsList.innerHTML = '';
    if (!data.concerns || data.concerns.length === 0) {
      concernsList.innerHTML = '<div class="concern-item clean">No technical defects or clipping concerns detected.</div>';
    } else {
      data.concerns.forEach(c => {
        const item = document.createElement('div');
        item.className = 'concern-item warning';
        item.textContent = `[${c.code}] ${c.description}`;
        concernsList.appendChild(item);
      });
    }
  }

  // Update timecode displays
  const tcCurrent = document.getElementById('tc-current');
  if (tcCurrent) tcCurrent.textContent = formatTimecode(currentTime);
  const tcTotal = document.getElementById('tc-total');
  if (tcTotal) tcTotal.textContent = formatTimecode(videoDuration);
}

// ============================================================================
// Broadcast Scopes Rendering Engine (High-DPI Continuous Phosphor Traces)
// ============================================================================
const offscreenScopeSampler = document.createElement('canvas');
const offscreenScopeCtx = offscreenScopeSampler.getContext('2d', { willReadFrequently: true });
let cachedFramePixels = null;
let cachedFrameWidth = 0;
let cachedFrameHeight = 0;

// Sample active viewport image pixels for 1:1 continuous broadcast scopes
function sampleLiveViewportPixels() {
  const imgEl = document.getElementById('viewport-frame-img');
  if (!imgEl || !imgEl.complete || !imgEl.naturalWidth || !imgEl.naturalHeight) {
    return false;
  }
  const sw = Math.min(640, imgEl.naturalWidth);
  const sh = Math.min(360, imgEl.naturalHeight);
  offscreenScopeSampler.width = sw;
  offscreenScopeSampler.height = sh;
  try {
    offscreenScopeCtx.drawImage(imgEl, 0, 0, sw, sh);
    cachedFramePixels = offscreenScopeCtx.getImageData(0, 0, sw, sh).data;
    cachedFrameWidth = sw;
    cachedFrameHeight = sh;
    return true;
  } catch (_) {
    return false;
  }
}

const viewportImgForScopes = document.getElementById('viewport-frame-img');
if (viewportImgForScopes) {
  viewportImgForScopes.addEventListener('load', () => {
    if (sampleLiveViewportPixels()) {
      renderCurrentScope();
    }
  });
}

function renderCurrentScope() {
  if (!canvas || !ctx) return;
  const w = canvas.width;
  const h = canvas.height;

  // Deep CRT/OLED black background
  ctx.fillStyle = '#05070b';
  ctx.fillRect(0, 0, w, h);

  sampleLiveViewportPixels();

  switch (currentScope) {
    case 'waveform':
      drawLumaWaveform(ctx, w, h, currentScopesData?.waveform);
      break;
    case 'parade':
      drawRgbParade(ctx, w, h, currentScopesData?.parade);
      break;
    case 'vectorscope':
      drawVectorscope(ctx, w, h, currentScopesData?.vectorscope);
      break;
    case 'histogram':
      drawHistograms(ctx, w, h, currentScopesData?.histogram);
      break;
    case 'cie':
      drawCieChromaticity(ctx, w, h, currentScopesData?.cie);
      break;
  }
}

// 1. High-Resolution Continuous Phosphor Luma Waveform (DaVinci / Tektronix style)
function drawLumaWaveform(c, w, h, wf) {
  const imgData = c.createImageData(w, h);
  const buf = imgData.data;
  // Initialize background to #05070b
  for (let i = 0; i < buf.length; i += 4) {
    buf[i] = 5;
    buf[i + 1] = 7;
    buf[i + 2] = 11;
    buf[i + 3] = 255;
  }

  const accum = new Float32Array(w * h);

  if (cachedFramePixels && cachedFrameWidth > 0 && cachedFrameHeight > 1) {
    const sw = cachedFrameWidth;
    const sh = cachedFrameHeight;
    const px = cachedFramePixels;

    // Sweep every horizontal column of the scope at 1:1 pixel resolution
    for (let cx = 0; cx < w; cx++) {
      const sx = Math.min(sw - 1, Math.floor((cx / w) * sw));
      let prevY = -1;
      for (let sy = 0; sy < sh; sy++) {
        const idx = (sy * sw + sx) * 4;
        const luma = 0.2126 * px[idx] + 0.7152 * px[idx + 1] + 0.0722 * px[idx + 2];
        const cy = Math.max(2, Math.min(h - 3, Math.round(h - 1 - (luma / 255.0) * (h - 1))));

        if (prevY >= 0) {
          // Connect vertical transition between adjacent scanlines so gradients form smooth continuous traces
          const y0 = Math.min(prevY, cy);
          const y1 = Math.max(prevY, cy);
          const span = Math.max(1, y1 - y0);
          const weight = 1.0 / Math.sqrt(span);
          for (let y = y0; y <= y1; y++) {
            accum[y * w + cx] += weight;
            if (y > 0) accum[(y - 1) * w + cx] += weight * 0.35;
            if (y + 1 < h) accum[(y + 1) * w + cx] += weight * 0.35;
          }
        } else {
          accum[cy * w + cx] += 1.0;
        }
        prevY = cy;
      }
    }
  } else if (wf && wf.density && wf.columns > 0 && wf.ire_levels > 0) {
    // Smooth bilinear interpolation of backend waveform density
    const cols = wf.columns;
    const levels = wf.ire_levels;
    for (let cx = 0; cx < w; cx++) {
      const colF = (cx / (w - 1)) * (cols - 1);
      const c0 = Math.floor(colF);
      const c1 = Math.min(cols - 1, c0 + 1);
      const tx = colF - c0;
      for (let cy = 0; cy < h; cy++) {
        const ireF = ((h - 1 - cy) / (h - 1)) * (levels - 1);
        const i0 = Math.floor(ireF);
        const i1 = Math.min(levels - 1, i0 + 1);
        const ty = ireF - i0;
        const d00 = wf.density[c0 * levels + i0] || 0;
        const d10 = wf.density[c1 * levels + i0] || 0;
        const d01 = wf.density[c0 * levels + i1] || 0;
        const d11 = wf.density[c1 * levels + i1] || 0;
        const d = (d00 * (1 - tx) + d10 * tx) * (1 - ty) + (d01 * (1 - tx) + d11 * tx) * ty;
        accum[cy * w + cx] = d * 6.0;
      }
    }
  }

  // Convert accumulated phosphor energy into OLED green trace with white-hot core bloom
  let maxVal = 0.001;
  for (let i = 0; i < accum.length; i++) {
    if (accum[i] > maxVal) maxVal = accum[i];
  }
  const normScale = 1.0 / Math.pow(maxVal, 0.55);

  for (let i = 0; i < accum.length; i++) {
    const v = accum[i];
    if (v <= 0.01) continue;
    const intensity = Math.min(1.0, Math.pow(v, 0.55) * normScale * 1.35);
    const core = Math.max(0.0, (intensity - 0.65) / 0.35);
    const p = i * 4;
    buf[p] = Math.min(255, Math.round(5 + intensity * 35 + core * 195));
    buf[p + 1] = Math.min(255, Math.round(7 + intensity * 240 + core * 15));
    buf[p + 2] = Math.min(255, Math.round(11 + intensity * 125 + core * 120));
  }

  c.putImageData(imgData, 0, 0);
  drawScopeGraticule(c, w, h, ['100 IRE', '75 IRE', '50 IRE', '25 IRE', '0 IRE']);
}

// 2. High-Resolution Continuous RGB Parade (Separate Red, Green, Blue Phosphor Channels)
function drawRgbParade(c, w, h, p) {
  const imgData = c.createImageData(w, h);
  const buf = imgData.data;
  for (let i = 0; i < buf.length; i += 4) {
    buf[i] = 5;
    buf[i + 1] = 7;
    buf[i + 2] = 11;
    buf[i + 3] = 255;
  }

  const paneW = Math.floor(w / 3);
  const accumR = new Float32Array(paneW * h);
  const accumG = new Float32Array(paneW * h);
  const accumB = new Float32Array(paneW * h);

  if (cachedFramePixels && cachedFrameWidth > 0 && cachedFrameHeight > 1) {
    const sw = cachedFrameWidth;
    const sh = cachedFrameHeight;
    const px = cachedFramePixels;

    for (let cx = 0; cx < paneW; cx++) {
      const sx = Math.min(sw - 1, Math.floor((cx / paneW) * sw));
      let prevR = -1, prevG = -1, prevB = -1;
      for (let sy = 0; sy < sh; sy++) {
        const idx = (sy * sw + sx) * 4;
        const ry = Math.max(2, Math.min(h - 3, Math.round(h - 1 - (px[idx] / 255.0) * (h - 1))));
        const gy = Math.max(2, Math.min(h - 3, Math.round(h - 1 - (px[idx + 1] / 255.0) * (h - 1))));
        const by = Math.max(2, Math.min(h - 3, Math.round(h - 1 - (px[idx + 2] / 255.0) * (h - 1))));

        if (prevR >= 0) {
          const y0 = Math.min(prevR, ry), y1 = Math.max(prevR, ry);
          const wt = 1.0 / Math.sqrt(Math.max(1, y1 - y0));
          for (let y = y0; y <= y1; y++) {
            accumR[y * paneW + cx] += wt;
            if (y > 0) accumR[(y - 1) * paneW + cx] += wt * 0.3;
            if (y + 1 < h) accumR[(y + 1) * paneW + cx] += wt * 0.3;
          }
          const g0 = Math.min(prevG, gy), g1 = Math.max(prevG, gy);
          const gwt = 1.0 / Math.sqrt(Math.max(1, g1 - g0));
          for (let y = g0; y <= g1; y++) {
            accumG[y * paneW + cx] += gwt;
            if (y > 0) accumG[(y - 1) * paneW + cx] += gwt * 0.3;
            if (y + 1 < h) accumG[(y + 1) * paneW + cx] += gwt * 0.3;
          }
          const b0 = Math.min(prevB, by), b1 = Math.max(prevB, by);
          const bwt = 1.0 / Math.sqrt(Math.max(1, b1 - b0));
          for (let y = b0; y <= b1; y++) {
            accumB[y * paneW + cx] += bwt;
            if (y > 0) accumB[(y - 1) * paneW + cx] += bwt * 0.3;
            if (y + 1 < h) accumB[(y + 1) * paneW + cx] += bwt * 0.3;
          }
        } else {
          accumR[ry * paneW + cx] += 1.0;
          accumG[gy * paneW + cx] += 1.0;
          accumB[by * paneW + cx] += 1.0;
        }
        prevR = ry;
        prevG = gy;
        prevB = by;
      }
    }
  } else if (p && p.r_density && p.columns > 0 && p.ire_levels > 0) {
    const cols = p.columns;
    const levels = p.ire_levels;
    const sampleBi = (arr, colF, ireF) => {
      const c0 = Math.floor(colF), c1 = Math.min(cols - 1, c0 + 1), tx = colF - c0;
      const i0 = Math.floor(ireF), i1 = Math.min(levels - 1, i0 + 1), ty = ireF - i0;
      return ((arr[c0 * levels + i0] || 0) * (1 - tx) + (arr[c1 * levels + i0] || 0) * tx) * (1 - ty)
           + ((arr[c0 * levels + i1] || 0) * (1 - tx) + (arr[c1 * levels + i1] || 0) * tx) * ty;
    };
    for (let cx = 0; cx < paneW; cx++) {
      const colF = (cx / (paneW - 1)) * (cols - 1);
      for (let cy = 0; cy < h; cy++) {
        const ireF = ((h - 1 - cy) / (h - 1)) * (levels - 1);
        accumR[cy * paneW + cx] = sampleBi(p.r_density, colF, ireF) * 5.0;
        accumG[cy * paneW + cx] = sampleBi(p.g_density, colF, ireF) * 5.0;
        accumB[cy * paneW + cx] = sampleBi(p.b_density, colF, ireF) * 5.0;
      }
    }
  }

  let maxVal = 0.001;
  for (let i = 0; i < accumR.length; i++) {
    if (accumR[i] > maxVal) maxVal = accumR[i];
    if (accumG[i] > maxVal) maxVal = accumG[i];
    if (accumB[i] > maxVal) maxVal = accumB[i];
  }
  const normScale = 1.0 / Math.pow(maxVal, 0.55);

  for (let cy = 0; cy < h; cy++) {
    for (let cx = 0; cx < paneW; cx++) {
      const idx = cy * paneW + cx;
      // Red pane
      if (accumR[idx] > 0.01) {
        const t = Math.min(1.0, Math.pow(accumR[idx], 0.55) * normScale * 1.35);
        const core = Math.max(0.0, (t - 0.65) / 0.35);
        const pIdx = (cy * w + cx) * 4;
        buf[pIdx] = Math.min(255, Math.round(5 + t * 250));
        buf[pIdx + 1] = Math.min(255, Math.round(7 + t * 65 + core * 165));
        buf[pIdx + 2] = Math.min(255, Math.round(11 + t * 75 + core * 155));
      }
      // Green pane
      if (accumG[idx] > 0.01) {
        const t = Math.min(1.0, Math.pow(accumG[idx], 0.55) * normScale * 1.35);
        const core = Math.max(0.0, (t - 0.65) / 0.35);
        const pIdx = (cy * w + (paneW + cx)) * 4;
        buf[pIdx] = Math.min(255, Math.round(5 + t * 40 + core * 185));
        buf[pIdx + 1] = Math.min(255, Math.round(7 + t * 240 + core * 15));
        buf[pIdx + 2] = Math.min(255, Math.round(11 + t * 105 + core * 125));
      }
      // Blue pane
      if (accumB[idx] > 0.01) {
        const t = Math.min(1.0, Math.pow(accumB[idx], 0.55) * normScale * 1.35);
        const core = Math.max(0.0, (t - 0.65) / 0.35);
        const pIdx = (cy * w + (paneW * 2 + cx)) * 4;
        buf[pIdx] = Math.min(255, Math.round(5 + t * 55 + core * 175));
        buf[pIdx + 1] = Math.min(255, Math.round(7 + t * 155 + core * 90));
        buf[pIdx + 2] = Math.min(255, Math.round(11 + t * 244));
      }
    }
  }

  c.putImageData(imgData, 0, 0);
  drawScopeGraticule(c, w, h, ['100 IRE', '75 IRE', '50 IRE', '25 IRE', '0 IRE']);

  // Crisp channel dividers & labels
  c.strokeStyle = 'rgba(120, 145, 180, 0.25)';
  c.lineWidth = 1.5;
  c.beginPath();
  c.moveTo(paneW, 0);
  c.lineTo(paneW, h);
  c.moveTo(paneW * 2, 0);
  c.lineTo(paneW * 2, h);
  c.stroke();

  c.font = 'bold 16px monospace';
  c.fillStyle = 'rgba(255, 95, 105, 0.8)';
  c.fillText('R', paneW - 22, 24);
  c.fillStyle = 'rgba(50, 235, 120, 0.8)';
  c.fillText('G', paneW * 2 - 22, 24);
  c.fillStyle = 'rgba(75, 165, 255, 0.8)';
  c.fillText('B', w - 22, 24);
}

// 3. High-Resolution Vectorscope (Target boxes, 75% & 100% saturation rings, Multi-Ethnic Skin Tone Cone)
function drawVectorscope(c, w, h, vs) {
  const cx = w / 2;
  const cy = h / 2;
  const radius = Math.min(w, h) * 0.43;
  const zoom = typeof vectorscopeZoom === 'number' ? vectorscopeZoom : 2.5;

  // Render phosphor cloud first from live frame pixels or backend density
  if (cachedFramePixels && cachedFrameWidth > 0 && cachedFrameHeight > 0) {
    const imgData = c.getImageData(0, 0, w, h);
    const buf = imgData.data;
    const accum = new Float32Array(w * h);
    const px = cachedFramePixels;
    const totalPx = cachedFrameWidth * cachedFrameHeight;

    for (let i = 0; i < totalPx; i++) {
      const p = i * 4;
      const r = px[p], g = px[p + 1], b = px[p + 2];
      const cb = -0.1146 * r - 0.3854 * g + 0.5000 * b;
      const cr = 0.5000 * r - 0.4542 * g - 0.0458 * b;
      const vx = Math.round(cx + ((cb * zoom) / 128.0) * radius);
      const vy = Math.round(cy - ((cr * zoom) / 128.0) * radius);
      if (vx >= 2 && vx < w - 2 && vy >= 2 && vy < h - 2) {
        accum[vy * w + vx] += 1.0;
        accum[vy * w + (vx - 1)] += 0.45;
        accum[vy * w + (vx + 1)] += 0.45;
        accum[(vy - 1) * w + vx] += 0.45;
        accum[(vy + 1) * w + vx] += 0.45;
      }
    }

    let maxV = 1.0;
    for (let i = 0; i < accum.length; i++) {
      if (accum[i] > maxV) maxV = accum[i];
    }
    const scale = 1.0 / Math.pow(maxV, 0.45);
    for (let i = 0; i < accum.length; i++) {
      if (accum[i] <= 0.01) continue;
      const t = Math.min(1.0, Math.pow(accum[i], 0.45) * scale * 1.4);
      const core = Math.max(0.0, (t - 0.6) / 0.4);
      const bIdx = i * 4;
      buf[bIdx] = Math.min(255, Math.round(5 + t * 40 + core * 195));
      buf[bIdx + 1] = Math.min(255, Math.round(7 + t * 235 + core * 20));
      buf[bIdx + 2] = Math.min(255, Math.round(11 + t * 185 + core * 70));
    }
    c.putImageData(imgData, 0, 0);
  } else if (vs && vs.density) {
    const res = vs.resolution;
    for (let y = 0; y < res; y++) {
      for (let x = 0; x < res; x++) {
        const d = vs.density[y * res + x];
        if (d > 0.02) {
          const px = cx + ((x - res / 2) / (res / 2)) * radius;
          const py = cy + ((y - res / 2) / (res / 2)) * radius;
          c.fillStyle = `rgba(0, 240, 175, ${Math.min(0.92, d * 0.9)})`;
          c.beginPath();
          c.arc(px, py, 2.2, 0, Math.PI * 2);
          c.fill();
        }
      }
    }
  }

  // 1. Broadcast Standard Skin Tone I-Line (~123° / ~10:30 position on clock face)
  // Shifted 33° from the +V (90°) axis into Quadrant II, positioned between Red (104°) and Yellow (167°)
  const skinAngleDeg = 123.0;
  const skinRad = (skinAngleDeg * Math.PI) / 180;

  // Subtle broadcast tolerance zone (±2.5°)
  const tolRad = (2.5 * Math.PI) / 180;
  c.beginPath();
  c.moveTo(cx, cy);
  c.arc(cx, cy, radius, -(skinRad + tolRad), -(skinRad - tolRad));
  c.closePath();
  c.fillStyle = 'rgba(235, 170, 85, 0.12)';
  c.fill();

  // Central Reference I-Line
  c.strokeStyle = 'rgba(240, 180, 75, 0.95)';
  c.lineWidth = 2.0;
  c.beginPath();
  c.moveTo(cx, cy);
  c.lineTo(cx + Math.cos(skinRad) * radius, cy - Math.sin(skinRad) * radius);
  c.stroke();

  // Graduation markers along the skin axis (25%, 50%, 75% saturation)
  [0.25, 0.50, 0.75].forEach(mult => {
    const tx = cx + Math.cos(skinRad) * radius * mult;
    const ty = cy - Math.sin(skinRad) * radius * mult;
    c.beginPath();
    c.arc(tx, ty, 2.2, 0, Math.PI * 2);
    c.fillStyle = '#ffbe5b';
    c.fill();
  });

  // I-Line Skin Tone Labeling positioned cleanly in Quadrant II
  const labelX = cx + Math.cos(skinRad) * (radius * 0.78);
  const labelY = cy - Math.sin(skinRad) * (radius * 0.78);
  c.fillStyle = '#ffbe5b';
  c.font = 'bold 11px monospace';
  c.fillText('I-LINE (10:30)', labelX - 86, labelY - 4);
  c.font = '9px monospace';
  c.fillStyle = 'rgba(235, 175, 75, 0.85)';
  c.fillText('Skin Tone (123°)', labelX - 86, labelY + 8);

  // Concentric Saturation Graticule Rings (25%, 50%, 75%, 100%)
  c.strokeStyle = 'rgba(110, 140, 180, 0.25)';
  c.lineWidth = 1.2;
  [0.25, 0.5, 0.75, 1.0].forEach(mult => {
    c.beginPath();
    c.arc(cx, cy, radius * mult, 0, Math.PI * 2);
    c.stroke();
  });

  // Crosshairs
  c.beginPath();
  c.moveTo(cx - radius, cy);
  c.lineTo(cx + radius, cy);
  c.moveTo(cx, cy - radius);
  c.lineTo(cx, cy + radius);
  c.stroke();

  // Rec.709 Target boxes (R, Mg, B, Cy, G, Yl at 75% saturation)
  const targets = [
    { label: 'R', angle: 104, color: '#ff5566' },
    { label: 'Mg', angle: 61, color: '#ff55ff' },
    { label: 'B', angle: 347, color: '#3399ff' },
    { label: 'Cy', angle: 284, color: '#00d2ff' },
    { label: 'G', angle: 241, color: '#00ff78' },
    { label: 'Yl', angle: 167, color: '#ffff33' }
  ];

  targets.forEach(t => {
    const rad = (t.angle * Math.PI) / 180;
    const tx = cx + Math.cos(rad) * radius * 0.75;
    const ty = cy - Math.sin(rad) * radius * 0.75;
    c.strokeStyle = t.color;
    c.lineWidth = 1.5;
    c.strokeRect(tx - 7, ty - 7, 14, 14);
    c.fillStyle = t.color;
    c.font = 'bold 15px monospace';
    c.fillText(t.label, tx + 11, ty + 5);
  });

  // Zoom readout badge in top-left
  c.fillStyle = 'rgba(15, 20, 28, 0.85)';
  c.strokeStyle = 'rgba(110, 140, 180, 0.35)';
  c.lineWidth = 1.0;
  c.strokeRect(12, 12, 178, 22);
  c.fillRect(12, 12, 178, 22);
  c.fillStyle = '#38bdf8';
  c.font = 'bold 10px monospace';
  c.fillText(`ZOOM: ${zoom.toFixed(1)}× (Click to cycle)`, 18, 27);
}

// 4. Smooth Anti-Aliased Spline Histograms
function drawHistograms(c, w, h, hist) {
  drawScopeGraticule(c, w, h, ['100%', '75%', '50%', '25%', '0%']);
  if (!hist || !hist.luma) return;

  // Apply 3-tap Gaussian smoothing to eliminate stair-stepping spikes
  const smoothCurve = (arr) => {
    const out = new Float32Array(256);
    for (let i = 0; i < 256; i++) {
      const p0 = arr[Math.max(0, i - 2)];
      const p1 = arr[Math.max(0, i - 1)];
      const p2 = arr[i];
      const p3 = arr[Math.min(255, i + 1)];
      const p4 = arr[Math.min(255, i + 2)];
      out[i] = p0 * 0.06 + p1 * 0.24 + p2 * 0.40 + p3 * 0.24 + p4 * 0.06;
    }
    return out;
  };

  const sLuma = smoothCurve(hist.luma);
  const sR = smoothCurve(hist.r);
  const sG = smoothCurve(hist.g);
  const sB = smoothCurve(hist.b);

  const maxVal = Math.max(...sLuma, ...sR, ...sG, ...sB, 1);

  const drawSmoothChannel = (data, strokeColor, fillColor) => {
    c.beginPath();
    c.moveTo(0, h);
    for (let i = 0; i < 256; i++) {
      const x = (i / 255) * w;
      const y = h - (data[i] / maxVal) * (h * 0.86);
      if (i === 0) {
        c.lineTo(x, y);
      } else {
        const prevX = ((i - 1) / 255) * w;
        const prevY = h - (data[i - 1] / maxVal) * (h * 0.86);
        const midX = (prevX + x) * 0.5;
        const midY = (prevY + y) * 0.5;
        c.quadraticCurveTo(prevX, prevY, midX, midY);
      }
    }
    c.lineTo(w, h);
    c.closePath();
    c.fillStyle = fillColor;
    c.fill();

    c.beginPath();
    for (let i = 0; i < 256; i++) {
      const x = (i / 255) * w;
      const y = h - (data[i] / maxVal) * (h * 0.86);
      if (i === 0) c.moveTo(x, y);
      else {
        const prevX = ((i - 1) / 255) * w;
        const prevY = h - (data[i - 1] / maxVal) * (h * 0.86);
        c.quadraticCurveTo(prevX, prevY, (prevX + x) * 0.5, (prevY + y) * 0.5);
      }
    }
    c.strokeStyle = strokeColor;
    c.lineWidth = 2.2;
    c.stroke();
  };

  drawSmoothChannel(sLuma, 'rgba(235, 240, 250, 0.85)', 'rgba(235, 240, 250, 0.14)');
  drawSmoothChannel(sR, 'rgba(255, 85, 95, 0.92)', 'rgba(255, 85, 95, 0.10)');
  drawSmoothChannel(sG, 'rgba(45, 235, 115, 0.92)', 'rgba(45, 235, 115, 0.10)');
  drawSmoothChannel(sB, 'rgba(65, 160, 255, 0.92)', 'rgba(65, 160, 255, 0.10)');
}

// 5. CIE 1931 Chromaticity Map (sRGB, DCI-P3 & Rec.2020 Gamut Triangles)
function drawCieChromaticity(c, w, h, cie) {
  drawScopeGraticule(c, w, h, ['y=0.9', 'y=0.6', 'y=0.3', 'y=0.0']);

  // Rec.2020 triangle
  c.strokeStyle = 'rgba(130, 150, 180, 0.35)';
  c.lineWidth = 1.5;
  c.setLineDash([6, 4]);
  c.beginPath();
  c.moveTo(w * (0.708 / 0.8), h * (1 - 0.292 / 0.9));
  c.lineTo(w * (0.170 / 0.8), h * (1 - 0.797 / 0.9));
  c.lineTo(w * (0.131 / 0.8), h * (1 - 0.046 / 0.9));
  c.closePath();
  c.stroke();
  c.setLineDash([]);

  // sRGB / Rec.709 triangle
  c.strokeStyle = 'rgba(0, 255, 120, 0.85)';
  c.lineWidth = 2.0;
  c.beginPath();
  c.moveTo(w * (0.64 / 0.8), h * (1 - 0.33 / 0.9));
  c.lineTo(w * (0.30 / 0.8), h * (1 - 0.60 / 0.9));
  c.lineTo(w * (0.15 / 0.8), h * (1 - 0.06 / 0.9));
  c.closePath();
  c.stroke();

  c.fillStyle = 'rgba(0, 255, 120, 0.9)';
  c.font = 'bold 14px monospace';
  c.fillText('Rec.709 / sRGB', w * 0.36, h * 0.30);

  if (!cie || !cie.density) return;
  const res = cie.grid_size;

  for (let y = 0; y < res; y++) {
    for (let x = 0; x < res; x++) {
      const d = cie.density[y * res + x];
      if (d > 0.025) {
        const px = (x / res) * w;
        const py = (y / res) * h;
        c.fillStyle = `rgba(255, 200, 65, ${Math.min(0.92, d * 0.9)})`;
        c.beginPath();
        c.arc(px, py, 2.4, 0, Math.PI * 2);
        c.fill();
      }
    }
  }
}

function drawScopeGraticule(c, w, h, labels) {
  c.strokeStyle = 'rgba(110, 135, 175, 0.16)';
  c.lineWidth = 1;
  c.font = '14px monospace';
  c.fillStyle = 'rgba(145, 165, 195, 0.68)';

  const step = h / (labels.length - 1);
  labels.forEach((lbl, idx) => {
    const y = Math.round(idx * step);
    c.beginPath();
    c.moveTo(0, y);
    c.lineTo(w, y);
    c.stroke();
    c.fillText(lbl, 8, Math.min(h - 6, y + 18));
  });
}

// ============================================================================
// Diagnostic Viewport Modes & Forensic Overlays
// ============================================================================
let activeViewportMode = 'picture';
const vpButtons = document.querySelectorAll('.vp-btn');
const overlayImg = document.getElementById('diagnostic-overlay-img');
const frameImg = document.getElementById('viewport-frame-img');
const vectorCanvas = document.getElementById('viewport-vector-canvas');
const vectorCtx = vectorCanvas ? vectorCanvas.getContext('2d') : null;
const elZoneLegend = document.getElementById('el-zone-legend');

vpButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    vpButtons.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeViewportMode = btn.dataset.mode || 'picture';
    updateViewportOverlay();
  });
});

function updateViewportOverlay() {
  if (activeViewportMode === 'picture') {
    if (frameImg) {
      frameImg.style.display = 'block';
      frameImg.src = `/api/frame?time=${currentTime.toFixed(2)}&_t=${Date.now()}`;
    }
    if (overlayImg) overlayImg.style.display = 'none';
    if (vectorCanvas) vectorCanvas.style.display = 'none';
    if (elZoneLegend) elZoneLegend.style.display = 'none';
  } else if (activeViewportMode === 'el_zone') {
    if (frameImg) frameImg.style.display = 'none';
    if (overlayImg) {
      overlayImg.src = `/api/frame_el_zone?time=${currentTime.toFixed(2)}&_t=${Date.now()}`;
      overlayImg.style.display = 'block';
    }
    if (vectorCanvas) vectorCanvas.style.display = 'none';
    if (elZoneLegend) elZoneLegend.style.display = 'flex';
  } else if (activeViewportMode === 'peaking') {
    if (frameImg) frameImg.style.display = 'none';
    if (overlayImg) {
      overlayImg.src = `/api/frame_peaking?time=${currentTime.toFixed(2)}&_t=${Date.now()}`;
      overlayImg.style.display = 'block';
    }
    if (vectorCanvas) vectorCanvas.style.display = 'none';
    if (elZoneLegend) elZoneLegend.style.display = 'none';
  } else if (activeViewportMode === 'volumetric') {
    if (frameImg) {
      frameImg.style.display = 'block';
      frameImg.src = `/api/frame?time=${currentTime.toFixed(2)}&_t=${Date.now()}`;
    }
    if (overlayImg) overlayImg.style.display = 'none';
    if (elZoneLegend) elZoneLegend.style.display = 'none';
    if (vectorCanvas) {
      vectorCanvas.style.display = 'block';
      drawVolumetricLight(currentEvaluateData?.craft?.lighting);
    }
  } else if (activeViewportMode === 'gaze') {
    if (frameImg) {
      frameImg.style.display = 'block';
      frameImg.src = `/api/frame?time=${currentTime.toFixed(2)}&_t=${Date.now()}`;
    }
    if (overlayImg) overlayImg.style.display = 'none';
    if (elZoneLegend) elZoneLegend.style.display = 'none';
    if (vectorCanvas) {
      vectorCanvas.style.display = 'block';
      drawEyelineAndGaze(currentEvaluateData?.craft?.staging);
    }
  }
}

function drawVolumetricLight(lighting) {
  if (!vectorCanvas || !vectorCtx) return;
  const rect = vectorCanvas.getBoundingClientRect();
  vectorCanvas.width = rect.width;
  vectorCanvas.height = rect.height;
  const w = vectorCanvas.width;
  const h = vectorCanvas.height;

  vectorCtx.clearRect(0, 0, w, h);

  const azimuth = lighting && lighting.key_azimuth_deg != null ? lighting.key_azimuth_deg : 45;
  const elevation = lighting && lighting.key_elevation_deg != null ? lighting.key_elevation_deg : 35;
  const ratio = lighting && lighting.key_to_fill_ratio != null ? lighting.key_to_fill_ratio : 3.8;
  const catchlight = lighting && lighting.catchlight_intensity != null ? lighting.catchlight_intensity : 75;

  const cx = Math.max(120, w - 120);
  const cy = 110;
  const radius = 55;

  vectorCtx.beginPath();
  vectorCtx.arc(cx, cy, radius, 0, Math.PI * 2);
  vectorCtx.fillStyle = 'rgba(10, 12, 16, 0.88)';
  vectorCtx.fill();
  vectorCtx.lineWidth = 1.5;
  vectorCtx.strokeStyle = '#252d3d';
  vectorCtx.stroke();

  // Ray Vector
  const angleRad = ((azimuth - 90) * Math.PI) / 180;
  const lightX = cx + Math.cos(angleRad) * (radius - 8);
  const lightY = cy + Math.sin(angleRad) * (radius - 8);

  const grad = vectorCtx.createRadialGradient(lightX, lightY, 4, cx, cy, radius);
  grad.addColorStop(0, 'rgba(229, 169, 59, 0.85)');
  grad.addColorStop(1, 'rgba(229, 169, 59, 0.08)');

  vectorCtx.beginPath();
  vectorCtx.moveTo(lightX, lightY);
  vectorCtx.lineTo(cx - 10, cy);
  vectorCtx.lineTo(cx + 10, cy);
  vectorCtx.closePath();
  vectorCtx.fillStyle = grad;
  vectorCtx.fill();

  vectorCtx.beginPath();
  vectorCtx.arc(lightX, lightY, 5, 0, Math.PI * 2);
  vectorCtx.fillStyle = '#e5a93b';
  vectorCtx.fill();
  vectorCtx.strokeStyle = '#ffffff';
  vectorCtx.lineWidth = 1.5;
  vectorCtx.stroke();

  // Readouts
  vectorCtx.fillStyle = 'rgba(10, 12, 16, 0.92)';
  vectorCtx.fillRect(cx - 85, cy + radius + 10, 170, 48);
  vectorCtx.strokeStyle = '#252d3d';
  vectorCtx.strokeRect(cx - 85, cy + radius + 10, 170, 48);

  vectorCtx.font = 'bold 11px sans-serif';
  vectorCtx.fillStyle = '#e5a93b';
  vectorCtx.textAlign = 'center';
  vectorCtx.fillText(`KEY: ${azimuth > 0 ? '+' : ''}${azimuth.toFixed(0)}° Az | ${elevation.toFixed(0)}° El`, cx, cy + radius + 26);
  vectorCtx.fillStyle = '#00d2ff';
  vectorCtx.fillText(`Key:Fill: ${ratio.toFixed(1)}:1  •  Catch: ${catchlight.toFixed(0)}%`, cx, cy + radius + 42);
}

function drawEyelineAndGaze(staging) {
  if (!vectorCanvas || !vectorCtx) return;
  const rect = vectorCanvas.getBoundingClientRect();
  vectorCanvas.width = rect.width;
  vectorCanvas.height = rect.height;
  const w = vectorCanvas.width;
  const h = vectorCanvas.height;

  vectorCtx.clearRect(0, 0, w, h);

  const gazeX = staging && staging.gaze_vector_x != null ? staging.gaze_vector_x : 0.65;
  const lookingRoom = staging && staging.looking_room_score != null ? staging.looking_room_score : 85;

  // Rule-of-Thirds Grid
  vectorCtx.strokeStyle = 'rgba(229, 169, 59, 0.35)';
  vectorCtx.lineWidth = 1;
  vectorCtx.setLineDash([6, 6]);

  const yThird1 = h * 0.3333;
  const yThird2 = h * 0.6667;
  vectorCtx.beginPath();
  vectorCtx.moveTo(0, yThird1);
  vectorCtx.lineTo(w, yThird1);
  vectorCtx.moveTo(0, yThird2);
  vectorCtx.lineTo(w, yThird2);

  const xThird1 = w * 0.3333;
  const xThird2 = w * 0.6667;
  vectorCtx.moveTo(xThird1, 0);
  vectorCtx.lineTo(xThird1, h);
  vectorCtx.moveTo(xThird2, 0);
  vectorCtx.lineTo(xThird2, h);
  vectorCtx.stroke();
  vectorCtx.setLineDash([]);

  // Eyeline label
  vectorCtx.font = '10px monospace';
  vectorCtx.fillStyle = '#e5a93b';
  vectorCtx.textAlign = 'left';
  vectorCtx.fillText('EYELINE (RULE OF THIRDS)', 14, yThird1 - 6);
}

// ============================================================================
// Timeline Scrubbing & In/Out Handles
// ============================================================================
const track = document.getElementById('timeline-track');
const playhead = document.getElementById('playhead');
const inHandle = document.getElementById('in-handle');
const outHandle = document.getElementById('out-handle');
const windowHighlight = document.getElementById('window-highlight');
const tcCurrent = document.getElementById('tc-current');
const tcTotal = document.getElementById('tc-total');
const tcWindowInfo = document.getElementById('tc-window-info');

function updateTimelineUI() {
  if (!track) return;
  const inRatio = Math.max(0, Math.min(1, currentInTime / videoDuration));
  const outRatio = Math.max(0, Math.min(1, currentOutTime / videoDuration));
  const playheadRatio = Math.max(0, Math.min(1, currentTime / videoDuration));

  if (inHandle) inHandle.style.left = `${inRatio * 100}%`;
  if (outHandle) outHandle.style.left = `${outRatio * 100}%`;
  if (windowHighlight) {
    windowHighlight.style.left = `${inRatio * 100}%`;
    windowHighlight.style.width = `${Math.max(0, outRatio - inRatio) * 100}%`;
  }
  if (playhead) playhead.style.left = `${playheadRatio * 100}%`;

  if (tcWindowInfo) {
    const dur = (currentOutTime - currentInTime).toFixed(1);
    tcWindowInfo.textContent = `Window: ${dur}s [In: ${formatTimecode(currentInTime)} | Out: ${formatTimecode(currentOutTime)}]`;
  }
  if (tcCurrent) tcCurrent.textContent = formatTimecode(currentTime);
  if (tcTotal) tcTotal.textContent = formatTimecode(videoDuration);
}

// Scrubber drag
if (track && playhead) {
  let isDraggingScrub = false;
  const updateScrub = (e) => {
    const rect = track.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const newTime = ratio * videoDuration;
    currentTime = newTime;
    updateTimelineUI();
    fetchFrameData(newTime);
  };

  track.addEventListener('mousedown', (e) => {
    if (e.target === inHandle || e.target === outHandle) return;
    isDraggingScrub = true;
    updateScrub(e);
  });

  window.addEventListener('mousemove', (e) => {
    if (isDraggingScrub) updateScrub(e);
  });

  window.addEventListener('mouseup', () => {
    isDraggingScrub = false;
  });
}

// In / Out Dragging
if (inHandle && track) {
  let isDraggingIn = false;
  inHandle.addEventListener('mousedown', (e) => {
    e.stopPropagation();
    isDraggingIn = true;
  });

  window.addEventListener('mousemove', (e) => {
    if (isDraggingIn) {
      const rect = track.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      currentInTime = Math.max(0, Math.min(ratio * videoDuration, currentOutTime - 0.5));
      updateTimelineUI();
    }
  });

  window.addEventListener('mouseup', () => {
    isDraggingIn = false;
  });
}

if (outHandle && track) {
  let isDraggingOut = false;
  outHandle.addEventListener('mousedown', (e) => {
    e.stopPropagation();
    isDraggingOut = true;
  });

  window.addEventListener('mousemove', (e) => {
    if (isDraggingOut) {
      const rect = track.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      currentOutTime = Math.min(videoDuration, Math.max(currentInTime + 0.5, ratio * videoDuration));
      updateTimelineUI();
    }
  });

  window.addEventListener('mouseup', () => {
    isDraggingOut = false;
  });
}

// ============================================================================
// Load Selects & Candidate Takes (With Real Decoded Thumbnails)
// ============================================================================
async function loadSelects() {
  const takesList = document.getElementById('takes-list');
  const countBadge = document.getElementById('take-count-badge');
  const modalSheetCount = document.getElementById('modal-sheet-count');
  const modalSheetGrid = document.getElementById('modal-sheet-grid');
  if (!takesList) return;

  try {
    const res = await fetch('/api/selects');
    if (!res.ok) return;
    const data = await res.json();
    currentTakes = data.takes || [];
    if (data.duration) videoDuration = data.duration;

    if (countBadge) countBadge.textContent = `${currentTakes.length} Takes`;
    if (modalSheetCount) modalSheetCount.textContent = `${currentTakes.length} Hero Selects`;
    takesList.innerHTML = '';
    if (modalSheetGrid) {
      modalSheetGrid.innerHTML = '';
      if (data.sequence_metrics) {
        const sm = data.sequence_metrics;
        const seqBanner = document.createElement('div');
        seqBanner.style.cssText = 'grid-column: 1 / -1; background: #14161a; border: 1px solid #282c35; border-radius: 8px; padding: 10px 16px; display: flex; flex-wrap: wrap; gap: 18px; align-items: center; justify-content: space-between; font-size: 12px; margin-bottom: 6px;';
        seqBanner.innerHTML = `
          <div><span style="color:#8a919e;text-transform:uppercase;font-size:10px;font-weight:700;">Sequence &amp; Reel Continuity</span><div style="color:#fff;font-weight:600;">${sm.transfer_curve_label || 'Display-Referred (Rec.709)'}</div></div>
          <div><span style="color:#8a919e;font-size:10px;">Grading Uniformity</span><div style="color:#4ade80;font-weight:700;font-family:var(--font-mono);">${Number(sm.grading_uniformity_score ?? 85).toFixed(1)} / 100</div></div>
          <div><span style="color:#8a919e;font-size:10px;">Coverage Consistency</span><div style="color:#38bdf8;font-weight:700;font-family:var(--font-mono);">${Number(sm.coverage_consistency_score ?? 85).toFixed(1)} / 100</div></div>
          <div><span style="color:#8a919e;font-size:10px;">Reel Diversity</span><div style="color:#e5a93c;font-weight:700;font-family:var(--font-mono);">${Number(sm.reel_diversity_score ?? 80).toFixed(1)} / 100</div></div>
          <div><span style="color:#8a919e;font-size:10px;">Visual Fatigue Index</span><div style="color:#e8eaed;font-weight:700;font-family:var(--font-mono);">${Number(sm.visual_fatigue_index ?? 18).toFixed(1)} / 100</div></div>
          <div><span style="color:#8a919e;font-size:10px;">Cross-Scene Spread</span><div style="color:#8a919e;font-family:var(--font-mono);font-size:11px;">WB &sigma;=${Number(sm.wb_cross_scene_std ?? 0).toFixed(2)} | CCT &sigma;=${Number(sm.color_temp_cross_scene_std ?? 0).toFixed(0)}K</div></div>
        `;
        modalSheetGrid.appendChild(seqBanner);
      }
    }

    if (currentTakes.length === 0) {
      takesList.innerHTML = '<div class="empty-state">No takes found. Open a media file to evaluate.</div>';
      return;
    }

    currentTakes.forEach((t, i) => {
      const heroTime = t.hero_timestamp_sec != null ? t.hero_timestamp_sec : (t.start_sec + (t.end_sec - t.start_sec) / 2);
      const score = Math.round(t.scores?.overall || 90);
      const startTc = formatTimecode(t.start_sec);
      const endTc = formatTimecode(t.end_sec);
      const dur = (t.duration_sec || (t.end_sec - t.start_sec)).toFixed(1);
      const match = t.style?.cinematographer_match || 'Golden Baseline Cinema Match';

      let decisionClass = 'decision-candidate';
      let decisionText = 'Candidate';
      if (t.recommendation === 'Hero Select' || i === 0) {
        decisionClass = 'decision-hero';
        decisionText = 'Hero Select';
      } else if (t.recommendation && t.recommendation.includes('Defect')) {
        decisionClass = 'decision-defect';
        decisionText = 'Defect Alert';
      }

      // 1. Candidate Selects Card in Left Panel
      const item = document.createElement('div');
      item.className = `take-item ${i === activeTakeIndex ? 'active' : ''}`;
      item.innerHTML = `
        <div class="take-thumb-wrap">
          <img class="take-thumb" src="/api/thumbnail?take=${encodeURIComponent(t.take_id)}&time=${heroTime.toFixed(2)}" alt="${t.take_id}" loading="lazy" onerror="this.src='/logo_icon.png'">
        </div>
        <div class="take-title-row">
          <span class="take-name">${t.take_id || `Take ${String(i + 1).padStart(2, '0')}`}</span>
          <span class="take-score">${score}</span>
        </div>
        <div class="take-details">${startTc} – ${endTc} (${dur}s)</div>
        <div class="take-tags-row">
          <span class="take-tag-pill">${t.style?.lighting_key || 'Natural'}</span>
          <span class="take-tag-pill">${t.style?.motion_type || 'Static'}</span>
          <span class="take-tag-pill">${t.style?.shot_scale || 'MCU'}</span>
        </div>
        <span class="take-decision-badge ${decisionClass}">${decisionText}</span>
      `;

      item.addEventListener('click', () => {
        document.querySelectorAll('.take-item').forEach(el => el.classList.remove('active'));
        item.classList.add('active');
        activeTakeIndex = i;
        currentInTime = t.start_sec;
        currentOutTime = t.end_sec;
        currentTime = heroTime;
        updateTimelineUI();
        fetchFrameData(heroTime);
      });

      takesList.appendChild(item);

      // 2. Contact Sheet Modal Card with Complete Collapsible Metrics Tree (EVERY SINGLE METRIC)
      if (modalSheetGrid) {
        const exp = t.measured?.exposure || {};
        const fcz = exp.false_color_zones || {};
        const elz = exp.el_zones || {};
        const opt = t.measured?.optics || {};
        const col = t.measured?.color || {};
        const craft = t.craft || {};
        const lgt = craft.lighting || {};
        const foc = craft.focus || {};
        const stg = craft.staging || {};
        const mot = craft.motion || {};
        const gbRows = Array.isArray(t.golden_baseline) ? t.golden_baseline : [];
        const concerns = Array.isArray(t.concerns) ? t.concerns : [];

        const fmt = (v, digits = 2, fallback = 0) => Number(v ?? fallback).toFixed(digits);

        const gbHtml = gbRows.length > 0
          ? `<div class="sheet-tree-pillar" style="margin-top: 6px;">Golden Baseline Distribution (Award Cinema)</div>` +
            gbRows.map(r => `<div class="sheet-tree-row"><span>${r.metric} (Award p50: ${fmt(r.corpus_p50, 1)} ${r.unit})</span><span>${fmt(r.shot_value, 2)} ${r.unit} • ${r.descriptor}</span></div>`).join('')
          : '';

        const concernsHtml = concerns.length === 0
          ? `<div class="sheet-tree-row"><span>Sensor &amp; Signal Status</span><span>Clean (0 Advisory Flags)</span></div>`
          : concerns.map(c => `<div class="sheet-tree-row"><span>[${c.code}] ${c.title || c.description}</span><span>${c.severity || 'Warning'}</span></div>`).join('');

        const sheetCard = document.createElement('div');
        sheetCard.className = 'sheet-card';
        sheetCard.innerHTML = `
          <div class="sheet-card-thumb-wrap">
            <img class="sheet-card-thumb" src="/api/thumbnail?take=${encodeURIComponent(t.take_id)}&time=${heroTime.toFixed(2)}" alt="${t.take_id}" loading="lazy" onerror="this.src='/logo_icon.png'">
          </div>
          <div class="sheet-card-body">
            <div class="sheet-card-header">
              <span class="sheet-card-title">#${i + 1} — ${t.take_id}</span>
              <span class="sheet-card-score">${score} / 100</span>
            </div>
            <div class="take-details">${startTc} &rarr; ${endTc} (${dur}s)</div>
            <div class="take-tags-row" data-tags="${t.style?.lighting_key || ''},${t.style?.motion_type || ''},${t.style?.shot_scale || ''},${t.style?.style_family || ''}">
              <span class="take-tag-pill">${t.style?.lighting_key || 'Natural'}</span>
              <span class="take-tag-pill">${t.style?.motion_type || 'Static'}</span>
              <span class="take-tag-pill">${t.style?.shot_scale || 'Wide'}</span>
              <span class="take-tag-pill">${t.style?.style_family || 'Naturalism'}</span>
            </div>
            <div class="master-banner" style="font-size: 11px; padding: 6px 8px;">
              <span class="master-icon">★</span>
              <span>Award Cinema Baseline Score: ${score}% • Ancillary DP Note: ${match}</span>
            </div>
            ${t.rationale_summary ? `<div style="background:#0c0d10;border-left:3px solid #e5a93c;padding:7px 9px;border-radius:4px;font-size:11px;line-height:1.4;color:#cbd2dc;margin:4px 0;">${t.rationale_summary}</div>` : ''}
            <div style="display:flex;gap:6px;margin:4px 0 6px 0;">
              <button class="btn btn-secondary btn-feedback-curation" data-take="${t.take_id}" data-action="promote_hero" data-style="${t.style?.style_family || ''}" data-scale="${t.style?.shot_scale || ''}" data-score="${score}" style="font-size:10px;padding:3px 7px;">★ Promote Hero</button>
              <button class="btn btn-secondary btn-feedback-curation" data-take="${t.take_id}" data-action="pin_select" data-style="${t.style?.style_family || ''}" data-scale="${t.style?.shot_scale || ''}" data-score="${score}" style="font-size:10px;padding:3px 7px;">📌 Pin Select</button>
              <button class="btn btn-secondary btn-feedback-curation" data-take="${t.take_id}" data-action="reject_take" data-style="${t.style?.style_family || ''}" data-scale="${t.style?.shot_scale || ''}" data-score="${score}" style="font-size:10px;padding:3px 7px;">✕ Deprioritize</button>
            </div>
            <!-- Complete Collapsible Scoring Metrics & Physics Breakdown (Every Single Metric) -->
            <details class="sheet-metrics-tree" open>
              <summary>▸ Complete 5-Layer Metrics &amp; Physics Breakdown (All Measured Metrics)</summary>
              <div class="sheet-tree-content">
                <div class="sheet-tree-pillar">Pillar 1A: Exposure &amp; Tonal Physics (Technical Score: ${fmt(t.scores?.technical, 1, 90)} / 100)</div>
                <div class="sheet-tree-row"><span>Dynamic Range Latitude</span><span>${fmt(exp.dynamic_range_stops, 2)} stops</span></div>
                <div class="sheet-tree-row"><span>Highlight Roll-Off Shoulder</span><span>${fmt(exp.highlight_rolloff, 1)}%</span></div>
                <div class="sheet-tree-row"><span>Specular Highlight Clip</span><span>${fmt(exp.highlight_clip_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Crushed Shadow Floor Clip</span><span>${fmt(exp.shadow_clip_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Histogram Mean Luma</span><span>${fmt(exp.histogram_mean, 2)} IRE</span></div>
                <div class="sheet-tree-row"><span>Histogram Median Luma</span><span>${fmt(exp.histogram_median, 2)} IRE</span></div>
                <div class="sheet-tree-row"><span>Histogram Std Deviation</span><span>${fmt(exp.histogram_std, 2)}</span></div>
                <div class="sheet-tree-row"><span>Histogram Skewness</span><span>${fmt(exp.histogram_skew, 3)}</span></div>
                <div class="sheet-tree-row"><span>Histogram Kurtosis</span><span>${fmt(exp.histogram_kurtosis, 3)}</span></div>
                <div class="sheet-tree-row"><span>Luma Signal-to-Noise Ratio (SNR)</span><span>${fmt(exp.snr_luma, 2)} dB</span></div>
                <div class="sheet-tree-row"><span>Chroma Signal-to-Noise Ratio (SNR)</span><span>${fmt(exp.snr_chroma, 2)} dB</span></div>
                <div class="sheet-tree-row"><span>Peak Signal-to-Noise Ratio (PSNR)</span><span>${fmt(exp.psnr_db, 1, 42)} dB</span></div>
                <div class="sheet-tree-row"><span>Structural Similarity Index (SSIM)</span><span>${fmt(exp.ssim_score, 3, 0.96)}</span></div>

                <div class="sheet-tree-pillar" style="margin-top: 6px;">Pillar 1B: False Color IRE Zones</div>
                <div class="sheet-tree-row"><span>Crushed Black (&lt; 2% IRE)</span><span>${fmt(fcz.black_clip_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Shadow Detail (2% – 20% IRE)</span><span>${fmt(fcz.shadow_zone_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>18% Middle Gray (35% – 45% IRE)</span><span>${fmt(fcz.middle_gray_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Skin Tone Key (50% – 65% IRE)</span><span>${fmt(fcz.skin_zone_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Highlight Modeling (70% – 90% IRE)</span><span>${fmt(fcz.highlight_zone_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Specular Clip Ceiling (&gt; 98% IRE)</span><span>${fmt(fcz.specular_clip_pct, 2)}%</span></div>

                <div class="sheet-tree-pillar" style="margin-top: 6px;">Pillar 1C: Ed Lachman, ASC EL Zone System (Stops vs 18% Gray)</div>
                <div class="sheet-tree-row"><span>Zone X (+5+ EV Specular Magenta)</span><span>${fmt(elz.zone_10_magenta_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Zone IX (+4 EV Near-Clip Red)</span><span>${fmt(elz.zone_9_red_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Zone VIII (+3 EV High-Key Orange)</span><span>${fmt(elz.zone_8_orange_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Zone VII (+2 EV Bright Skin Yellow)</span><span>${fmt(elz.zone_7_yellow_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Zone VI (+1 EV Caucasian Skin Khaki)</span><span>${fmt(elz.zone_6_khaki_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Zone V (0 EV 18% Middle Gray)</span><span>${fmt(elz.zone_5_gray_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Zone IV (-1 EV Shadow Fill Olive)</span><span>${fmt(elz.zone_4_olive_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Zone III (-2 EV Cyan Shadow)</span><span>${fmt(elz.zone_3_cyan_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Zone II (-3 EV Deep Blue)</span><span>${fmt(elz.zone_2_blue_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Zone I (-4 EV Purple Toe)</span><span>${fmt(elz.zone_1_purple_pct, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Zone 0 (-5+ EV Sensor Floor Black)</span><span>${fmt(elz.zone_0_black_pct, 2)}%</span></div>

                <div class="sheet-tree-pillar" style="margin-top: 6px;">Pillar 2: Optical, MTF &amp; Spatial Frequency Physics</div>
                <div class="sheet-tree-row"><span>MTF50 Acutance (Laplacian Variance)</span><span>${fmt(opt.sharpness_laplacian, 2)} lp/mm</span></div>
                <div class="sheet-tree-row"><span>Edge Micro-Contrast Density</span><span>${fmt(opt.edge_density, 4)}</span></div>
                <div class="sheet-tree-row"><span>MTF Modulation Transfer Proxy</span><span>${fmt(opt.mtf_proxy, 3)}</span></div>
                <div class="sheet-tree-row"><span>Optical Vignetting Falloff</span><span>${fmt(opt.vignetting_stops, 2)} stops</span></div>
                <div class="sheet-tree-row"><span>Chromatic Aberration Fringe Width</span><span>${fmt(opt.chromatic_aberration_px, 2)} px</span></div>

                <div class="sheet-tree-pillar" style="margin-top: 6px;">Pillar 3: Colorimetry &amp; Gamut Physics</div>
                <div class="sheet-tree-row"><span>Correlated Color Temperature (CCT)</span><span>${fmt(col.estimated_kelvin, 0, 5600)} K</span></div>
                <div class="sheet-tree-row"><span>White Balance Tint Deviation</span><span>${fmt(col.wb_deviation, 3)}</span></div>
                <div class="sheet-tree-row"><span>Mean Chromatic Saturation</span><span>${fmt(col.saturation_mean, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Palette Chromatic Entropy</span><span>${fmt(col.palette_entropy, 3)} bits</span></div>
                <div class="sheet-tree-row"><span>Delta-E D65 Neutral Drift</span><span>${fmt(col.delta_e_d65, 2)} &Delta;E</span></div>
                <div class="sheet-tree-row"><span>Skin Tone I-Line Deviation</span><span>${col.skin_tone_delta_e != null ? `${fmt(col.skin_tone_delta_e, 2)} &Delta;E` : 'N/A'}</span></div>
                <div class="sheet-tree-row"><span>Gamut Coverage (Rec.709 / sRGB)</span><span>${fmt(col.gamut_coverage_srgb, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Gamut Coverage (DCI-P3 Cinema)</span><span>${fmt(col.gamut_coverage_p3, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Gamut Coverage (Rec.2020 Wide)</span><span>${fmt(col.gamut_coverage_rec2020, 2)}%</span></div>
                <div class="sheet-tree-row"><span>Split-Toning Vector Separation</span><span>${fmt(col.split_toning_separation_deg, 1)}&deg;</span></div>
                <div class="sheet-tree-row"><span>Harmonic Palette Balance Score</span><span>${fmt(col.harmonic_palette_score, 1)} / 100</span></div>

                <div class="sheet-tree-pillar" style="margin-top: 6px;">Pillar 4: Model-Inferred Craft, Lighting &amp; Staging (Creative Score: ${fmt(t.scores?.creative, 1, 88)} / 100)</div>
                <div class="sheet-tree-row"><span>Lighting Key Classification</span><span>${t.style?.lighting_key || 'Low-Key'}</span></div>
                <div class="sheet-tree-row"><span>Key-to-Fill Contrast Ratio</span><span>${fmt(lgt.key_to_fill_ratio, 2, 3.5)}:1</span></div>
                <div class="sheet-tree-row"><span>Key Light Azimuth Angle</span><span>${fmt(lgt.key_azimuth_deg, 1, 42)}&deg;</span></div>
                <div class="sheet-tree-row"><span>Key Light Elevation Angle</span><span>${fmt(lgt.key_elevation_deg, 1, 35)}&deg;</span></div>
                <div class="sheet-tree-row"><span>Rim / Edge Light Separation</span><span>${fmt(lgt.rim_light_separation, 1)} / 100</span></div>
                <div class="sheet-tree-row"><span>Shadow Boundary Softness</span><span>${fmt(lgt.shadow_softness, 1)} / 100</span></div>
                <div class="sheet-tree-row"><span>Eye Specular Catchlight Intensity</span><span>${fmt(lgt.catchlight_intensity, 1)}%</span></div>
                <div class="sheet-tree-row"><span>Subject Plane Focus Accuracy</span><span>${fmt(foc.subject_focus_accuracy, 1)} / 100</span></div>
                <div class="sheet-tree-row"><span>Subject Eye Sharpness</span><span>${fmt(foc.eye_sharpness, 1)} / 100</span></div>
                <div class="sheet-tree-row"><span>Focus Stability (Non-Hunting)</span><span>${fmt(foc.focus_hunting_score, 1)} / 100</span></div>
                <div class="sheet-tree-row"><span>Gaze Anchor Coordinates (X, Y)</span><span>(${fmt(stg.gaze_vector_x, 2, 0.5)}, ${fmt(stg.gaze_vector_y, 2, 0.38)})</span></div>
                <div class="sheet-tree-row"><span>Looking Room Lead Space</span><span>${fmt(stg.looking_room_score, 1)} / 100</span></div>
                <div class="sheet-tree-row"><span>Gaze Poise &amp; Thirds Balance</span><span>${fmt(stg.gaze_poise_score, 1)} / 100</span></div>
                <div class="sheet-tree-row"><span>3D Depth Plane Separation</span><span>${fmt(stg.depth_separation_score, 1)} / 100 (${stg.depth_plane_count ?? 3} planes)</span></div>
                <div class="sheet-tree-row"><span>Subject Silhouette Readability</span><span>${fmt(stg.silhouette_clarity, 1)} / 100</span></div>
                <div class="sheet-tree-row"><span>Framing Shot Scale</span><span>${t.style?.shot_scale || 'Medium'}</span></div>
                <div class="sheet-tree-row"><span>Chromatic Palette Family</span><span>${t.style?.palette_family || 'Natural Daylight'}</span></div>
                <div class="sheet-tree-row"><span>Scene Environment Type</span><span>${t.style?.scene_type || 'Controlled Studio / Stage'}</span></div>
                <div class="sheet-tree-row"><span>Narrative Shot Intent</span><span>${t.style?.shot_intent || 'Dialogue / Staging'}</span></div>
                <div class="sheet-tree-row"><span>Style Family Manifold Cluster</span><span>${t.style?.style_family || 'Prestige Naturalism'}</span></div>

                <div class="sheet-tree-pillar" style="margin-top: 6px;">Pillar 5: Temporal &amp; Editorial Dynamics (Temporal Score: ${fmt(t.scores?.temporal, 1, 90)} / 100)</div>
                <div class="sheet-tree-row"><span>Usable Hero Window Duration</span><span>${dur}s</span></div>
                <div class="sheet-tree-row"><span>Window In SMPTE Timecode</span><span>${startTc}</span></div>
                <div class="sheet-tree-row"><span>Window Out SMPTE Timecode</span><span>${endTc}</span></div>
                <div class="sheet-tree-row"><span>Hero Frame Timestamp</span><span>${fmt(heroTime, 2)}s</span></div>
                <div class="sheet-tree-row"><span>Camera Motion Classification</span><span>${t.style?.motion_type || 'Smooth Camera Move'}</span></div>
                <div class="sheet-tree-row"><span>Optical Flow Mean Velocity</span><span>${fmt(mot.optical_flow_mean, 2)} px/s</span></div>
                <div class="sheet-tree-row"><span>Optical Flow Velocity Std Dev</span><span>${fmt(mot.optical_flow_std, 2)} px/s</span></div>
                <div class="sheet-tree-row"><span>Camera vs Subject Motion Ratio</span><span>${fmt((mot.camera_motion_ratio ?? 0.85) * 100, 1)}%</span></div>
                <div class="sheet-tree-row"><span>High-Frequency Micro-Jitter</span><span>${fmt(mot.micro_jitter_score, 2)} / 100</span></div>
                <div class="sheet-tree-row"><span>Multi-Plane Parallax Strength</span><span>${fmt(mot.parallax_strength, 1)} / 100</span></div>
                <div class="sheet-tree-row"><span>24fps Pan Judder Risk Score</span><span>${fmt(mot.judder_risk_score, 1)} / 100</span></div>
                <div class="sheet-tree-row"><span>Motion Blur Trajectory Angle</span><span>${fmt(mot.motion_blur_angle_deg, 1)}&deg;</span></div>
                <div class="sheet-tree-row"><span>Motion Trajectory Coherence</span><span>${fmt(mot.motion_coherence_score, 1, 85)} / 100</span></div>

                <div class="sheet-tree-pillar" style="margin-top: 6px;">Narrative &amp; Aesthetic Reranker Heads</div>
                <div class="sheet-tree-row"><span>Hero-Frame Potency (Thumbnail Suitability)</span><span>${fmt(t.scores?.hero_potency_score, 1, score)} / 100</span></div>
                <div class="sheet-tree-row"><span>Three-Second Impact (Opening Authority)</span><span>${fmt(t.scores?.three_second_impact_score, 1, score)} / 100</span></div>
                <div class="sheet-tree-row"><span>Authorship &amp; Distinctiveness</span><span>${fmt(t.scores?.authorship_distinctiveness_score, 1, score)} / 100</span></div>
                <div class="sheet-tree-row"><span>Visual Storytelling Effectiveness</span><span>${fmt(t.scores?.storytelling_score, 1, score)} / 100</span></div>
                <div class="sheet-tree-row"><span>Cinematic Technique Quality</span><span>${fmt(t.scores?.cinematic_technique_score, 1, score)} / 100</span></div>
                <div class="sheet-tree-row"><span>Visual Memorability</span><span>${fmt(t.scores?.memorability_score, 1, score)} / 100</span></div>

                ${gbHtml}

                <div class="sheet-tree-pillar" style="margin-top: 6px;">Layer 5: Forensic Diagnostics (Non-Punitive Technical Flags)</div>
                ${concernsHtml}
              </div>
            </details>
          </div>
        `;
        modalSheetGrid.appendChild(sheetCard);
      }
    });

    if (modalSheetGrid) {
      modalSheetGrid.querySelectorAll('.btn-feedback-curation').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          e.stopPropagation();
          const takeId = btn.dataset.take || 'take_001';
          const action = btn.dataset.action || 'pin_select';
          const styleFam = btn.dataset.style || '';
          const scale = btn.dataset.scale || '';
          const sc = btn.dataset.score || '80';
          try {
            const url = `/api/feedback?take_id=${encodeURIComponent(takeId)}&action=${encodeURIComponent(action)}&style_family=${encodeURIComponent(styleFam)}&shot_scale=${encodeURIComponent(scale)}&overall=${encodeURIComponent(sc)}`;
            await fetch(url);
            await loadSelects();
          } catch (err) {
            console.warn('Feedback log error:', err);
          }
        });
      });
    }

    if (currentTakes.length > 0 && activeTakeIndex < currentTakes.length) {
      const first = currentTakes[activeTakeIndex];
      currentInTime = first.start_sec;
      currentOutTime = first.end_sec;
      currentTime = first.hero_timestamp_sec != null ? first.hero_timestamp_sec : 16.0;
      updateTimelineUI();
    }
  } catch (err) {
    console.warn('Failed to load selects:', err);
  }
}

// ============================================================================
// Header Dropdowns & Navigation Handlers
// ============================================================================
const dropdownImport = document.getElementById('dropdown-import');
const btnDropdownImport = document.getElementById('btn-dropdown-import');
const dropdownExport = document.getElementById('dropdown-export');
const btnDropdownExport = document.getElementById('btn-dropdown-export');

if (btnDropdownImport && dropdownImport) {
  btnDropdownImport.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdownImport.classList.toggle('open');
    if (dropdownExport) dropdownExport.classList.remove('open');
  });
}

if (btnDropdownExport && dropdownExport) {
  btnDropdownExport.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdownExport.classList.toggle('open');
    if (dropdownImport) dropdownImport.classList.remove('open');
  });
}

// Close dropdowns on outside click
window.addEventListener('click', () => {
  if (dropdownImport) dropdownImport.classList.remove('open');
  if (dropdownExport) dropdownExport.classList.remove('open');
});

// Import Options
const btnOpen = document.getElementById('btn-open-file');
if (btnOpen) {
  btnOpen.addEventListener('click', async () => {
    try {
      let filePath = null;
      try {
        const browseRes = await fetch('/api/browse_file');
        const browseData = await browseRes.json();
        if (browseData.success && browseData.path) {
          filePath = browseData.path;
        }
      } catch (e) {}

      if (!filePath) {
        filePath = prompt('Enter media file path to analyze:');
      }
      if (!filePath || !filePath.trim()) return;
      filePath = filePath.trim().replace(/^["']|["']$/g, '').trim();

      const takesList = document.getElementById('takes-list');
      if (takesList) {
        takesList.innerHTML = '<div class="empty-state">Analyzing video stream & computing cinematographic matrix...</div>';
      }

      const res = await fetch(`/api/analyze?path=${encodeURIComponent(filePath)}`);
      const data = await res.json();
      if (data.success) {
        await loadSelects();
        fetchFrameData(currentTime);
      } else {
        const openRes = await fetch(`/api/open_media?path=${encodeURIComponent(filePath)}`);
        const openData = await openRes.json();
        if (openData.success && openData.media) {
          videoDuration = openData.media.duration_sec || 60.0;
          await loadSelects();
          fetchFrameData(currentTime);
        } else {
          alert(`Failed to load media: ${data.error || openData.error || 'Unknown error'}`);
        }
      }
    } catch (err) {
      alert(`Error opening media: ${err}`);
    }
  });
}

const btnWeb = document.getElementById('btn-web-url');
if (btnWeb) {
  btnWeb.addEventListener('click', async () => {
    const url = prompt('Enter video URL (YouTube, Vimeo, or direct stream link):');
    if (!url) return;

    try {
      const res = await fetch(`/api/web_probe?url=${encodeURIComponent(url)}`);
      const data = await res.json();
      if (data.success) {
        alert(`URL Probed Successfully:\nTitle: ${data.info.title || url}\nDuration: ${data.info.duration_sec || 'N/A'}s`);
      } else {
        alert(`Failed to probe URL: ${data.error}`);
      }
    } catch (err) {
      alert(`Error probing URL: ${err}`);
    }
  });
}

const btnOpenSidecars = document.getElementById('btn-open-sidecars');
if (btnOpenSidecars) {
  btnOpenSidecars.addEventListener('click', async () => {
    try {
      let dirPath = prompt(
        'Open Cached Sidecars Folder:\n\nEnter directory path containing JSON+PNG sidecars\n(e.g. assets/curated/acting_dead or an individual episode folder):',
        'assets/curated/acting_dead'
      );
      if (!dirPath || !dirPath.trim()) return;
      dirPath = dirPath.trim().replace(/^["']|["']$/g, '').trim();

      const takesList = document.getElementById('takes-list');
      if (takesList) {
        takesList.innerHTML = '<div class="empty-state">Loading cached sidecars & computing baseline similarity...</div>';
      }

      const res = await fetch(`/api/rescore_sidecars?path=${encodeURIComponent(dirPath)}`);
      const data = await res.json();
      if (data.success) {
        await loadSelects();
      } else {
        alert(`Failed to rescore sidecars: ${data.error || 'Unknown error'}`);
      }
    } catch (err) {
      alert(`Error opening sidecars folder: ${err}`);
    }
  });
}

const btnBatchFolder = document.getElementById('btn-batch-folder');
if (btnBatchFolder) {
  btnBatchFolder.addEventListener('click', async () => {
    try {
      let folderPath = null;
      try {
        const browseRes = await fetch('/api/browse_dir');
        const browseData = await browseRes.json();
        if (browseData.success && browseData.path) {
          folderPath = browseData.path;
        }
      } catch (e) {}

      if (!folderPath) {
        folderPath = prompt(
          'Enter directory path containing videos to batch analyze:',
          'O:\\ELECTRICHOBO\\FINALS AND MEZZANINES\\02 DIRECTOR OF PHOTOGRAPHY\\Acting Dead'
        );
      }
      if (!folderPath || !folderPath.trim()) return;
      folderPath = folderPath.trim().replace(/^["']|["']$/g, '').trim();

      btnBatchFolder.disabled = true;
      alert(`[AESTHETIC Batch Queue]\nStarting batch analysis on directory:\n${folderPath}\nThis runs sequentially across all video files and saves individual sidecars.`);
      const res = await fetch(`/api/batch_folder?folder=${encodeURIComponent(folderPath)}&step=2.0`);
      const data = await res.json();
      if (data.folder_path) {
        alert(`[✓] Batch Analysis Finished!\nProcessed ${data.total_files_processed} files in ${data.elapsed_sec.toFixed(1)}s.\nTotal Hero Selects Extracted: ${data.total_takes_extracted}\nOutput saved to: ${data.output_sidecars_dir}`);
      } else {
        alert(`Batch analysis error: ${data.error || 'Failed'}`);
      }
    } catch (err) {
      alert(`Error in batch processing: ${err}`);
    } finally {
      btnBatchFolder.disabled = false;
    }
  });
}

// Export Handlers
const btnLiveResolve = document.getElementById('btn-live-resolve');
if (btnLiveResolve) {
  btnLiveResolve.addEventListener('click', async () => {
    btnLiveResolve.disabled = true;
    const origText = btnLiveResolve.innerHTML;
    btnLiveResolve.innerHTML = '<span class="item-icon">⏳</span><div class="item-text"><div class="item-title">Connecting to Resolve...</div><div class="item-desc">Sending timeline and markers via IPC...</div></div>';
    try {
      const res = await fetch('/api/send_to_resolve?timeline=AESTHETIC_Hero_Selects');
      const data = await res.json();
      if (data.success) {
        alert(`[✓] DaVinci Resolve Bridge Success!\n${data.message}`);
      } else {
        alert(`[!] DaVinci Resolve Bridge Notice:\n${data.message}`);
      }
    } catch (err) {
      alert(`Error communicating with DaVinci Resolve Bridge: ${err}`);
    } finally {
      btnLiveResolve.disabled = false;
      btnLiveResolve.innerHTML = origText;
    }
  });
}

const btnExportResolve = document.getElementById('btn-export-resolve');
if (btnExportResolve) {
  btnExportResolve.addEventListener('click', () => {
    const a = document.createElement('a');
    a.href = '/api/export_resolve_script';
    a.download = 'AESTHETIC_Resolve_Import.py';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });
}

const btnExportXml = document.getElementById('btn-export-xml');
if (btnExportXml) {
  btnExportXml.addEventListener('click', () => {
    const a = document.createElement('a');
    a.href = '/api/export_fcpxml';
    a.download = 'AESTHETIC_SELECTS.fcpxml';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });
}

const btnExportEdl = document.getElementById('btn-export-edl');
if (btnExportEdl) {
  btnExportEdl.addEventListener('click', () => {
    const a = document.createElement('a');
    a.href = '/api/export_edl';
    a.download = 'AESTHETIC_SELECTS.edl';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });
}

const btnExportCsv = document.getElementById('btn-export-csv');
if (btnExportCsv) {
  btnExportCsv.addEventListener('click', () => {
    const a = document.createElement('a');
    a.href = '/api/export_csv';
    a.download = 'AESTHETIC_SELECTS.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });
}

const btnExportSheet = document.getElementById('btn-export-sheet');
if (btnExportSheet) {
  btnExportSheet.addEventListener('click', () => {
    window.open('/api/export_contact_sheet', '_blank');
  });
}

const btnExportSheetPng = document.getElementById('btn-export-sheet-png');
if (btnExportSheetPng) {
  btnExportSheetPng.addEventListener('click', () => {
    const a = document.createElement('a');
    a.href = '/api/export_contact_sheet_png';
    a.download = 'AESTHETIC_Contact_Sheet.png';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });
}

const btnExportHeroPng = document.getElementById('btn-export-hero-png');
if (btnExportHeroPng) {
  btnExportHeroPng.addEventListener('click', () => {
    const a = document.createElement('a');
    a.href = `/api/export_hero_png?time=${currentTime.toFixed(2)}`;
    a.download = 'AESTHETIC_Hero_Frame.png';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });
}

// Modal Export buttons
const btnModalExportPng = document.getElementById('btn-modal-export-png');
if (btnModalExportPng) {
  btnModalExportPng.addEventListener('click', () => {
    window.open('/api/export_contact_sheet_png', '_blank');
  });
}

const btnModalExportHtml = document.getElementById('btn-modal-export-html');
if (btnModalExportHtml) {
  btnModalExportHtml.addEventListener('click', () => {
    window.open('/api/export_contact_sheet', '_blank');
  });
}

// ============================================================================
// Pop-out Contact Sheet Modal
// ============================================================================
const btnOpenContactSheet = document.getElementById('btn-open-contact-sheet');
const contactSheetModal = document.getElementById('contact-sheet-modal');
const modalContactSheetClose = document.getElementById('modal-contact-sheet-close');

if (btnOpenContactSheet && contactSheetModal) {
  btnOpenContactSheet.addEventListener('click', () => {
    contactSheetModal.style.display = 'flex';
  });
}

if (modalContactSheetClose && contactSheetModal) {
  modalContactSheetClose.addEventListener('click', () => {
    contactSheetModal.style.display = 'none';
  });
}

// ============================================================================
// Floating Resizable Popout Panels (Viewport, Scopes, Visual Æesthetic)
// ============================================================================
const floatingModal = document.getElementById('floating-popout-modal');
const floatingTitle = document.getElementById('floating-title');
const floatingContent = document.getElementById('floating-content');
const btnFloatingClose = document.getElementById('btn-floating-close');
const floatingHeader = document.getElementById('floating-header');

let activePoppedPanelId = null;

document.querySelectorAll('.panel-popout-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const panelId = btn.dataset.panel;
    if (!panelId) return;

    if (panelId === 'panel-takes') {
      // Pop out contact sheet gallery
      if (contactSheetModal) contactSheetModal.style.display = 'flex';
      return;
    }

    const targetEl = document.getElementById(panelId);
    if (!targetEl || !floatingModal || !floatingContent) return;

    activePoppedPanelId = panelId;
    const titleText = targetEl.querySelector('h2, h3')?.textContent || 'Popped Panel';
    if (floatingTitle) floatingTitle.textContent = `${titleText} — Floating View`;

    floatingContent.innerHTML = '';
    const clone = targetEl.cloneNode(true);
    // Remove the popout button inside the clone
    clone.querySelectorAll('.panel-popout-btn').forEach(b => b.remove());
    floatingContent.appendChild(clone);

    floatingModal.style.display = 'flex';
  });
});

if (btnFloatingClose && floatingModal) {
  btnFloatingClose.addEventListener('click', () => {
    floatingModal.style.display = 'none';
    if (floatingContent) floatingContent.innerHTML = '';
    activePoppedPanelId = null;
  });
}

// Draggable Floating Header
if (floatingHeader && floatingModal) {
  let isDragging = false;
  let startX = 0, startY = 0, initialLeft = 0, initialTop = 0;

  floatingHeader.addEventListener('mousedown', (e) => {
    if (e.target === btnFloatingClose) return;
    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    const rect = floatingModal.getBoundingClientRect();
    initialLeft = rect.left;
    initialTop = rect.top;
  });

  window.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    floatingModal.style.left = `${Math.max(10, initialLeft + dx)}px`;
    floatingModal.style.top = `${Math.max(10, initialTop + dy)}px`;
  });

  window.addEventListener('mouseup', () => {
    isDragging = false;
  });
}

// ============================================================================
// Smart Showreel Composer Controller (M28)
const btnOpenComposer = document.getElementById('btn-open-composer');
const composerModal = document.getElementById('composer-modal');
const modalComposerClose = document.getElementById('modal-composer-close');
const btnComposerCancel = document.getElementById('btn-composer-cancel');
const btnComposerAssemble = document.getElementById('btn-composer-assemble');
const reelDurationSelect = document.getElementById('reel-target-duration');
const reelObjectiveSelect = document.getElementById('reel-objective');
const composerResultBox = document.getElementById('composer-result-box');

if (btnOpenComposer && composerModal) {
  btnOpenComposer.addEventListener('click', () => {
    composerModal.style.display = 'flex';
    if (composerResultBox) composerResultBox.style.display = 'none';
  });
}

function closeComposerModal() {
  if (composerModal) composerModal.style.display = 'none';
}

if (modalComposerClose) modalComposerClose.addEventListener('click', closeComposerModal);
if (btnComposerCancel) btnComposerCancel.addEventListener('click', closeComposerModal);

if (btnComposerAssemble) {
  btnComposerAssemble.addEventListener('click', async () => {
    const dur = reelDurationSelect ? reelDurationSelect.value : '60';
    const obj = reelObjectiveSelect ? reelObjectiveSelect.value : 'commercial';

    btnComposerAssemble.disabled = true;
    btnComposerAssemble.textContent = 'Optimizing Pacing & Cuts...';
    if (composerResultBox) {
      composerResultBox.style.display = 'block';
      composerResultBox.innerHTML = 'Solving constraint optimization for pacing rhythm and Kelvin continuity...';
    }

    try {
      const res = await fetch(`/api/compose_showreel?duration=${dur}&objective=${obj}`);
      const data = await res.json();
      if (data.success && data.assembled_takes) {
        let rowsHtml = '';
        data.assembled_takes.forEach((t, i) => {
          rowsHtml += `<tr>
            <td style="padding: 4px 8px; color: #e5a93c; font-weight: 700;">#${i + 1}</td>
            <td style="padding: 4px 8px;">${t.take_id}</td>
            <td style="padding: 4px 8px;">${t.style.shot_scale}</td>
            <td style="padding: 4px 8px;">${t.style.lighting_key}</td>
            <td style="padding: 4px 8px;">${t.duration_sec.toFixed(1)}s</td>
            <td style="padding: 4px 8px; color: #4ade80;">${t.scores.overall.toFixed(1)}</td>
          </tr>`;
        });

        composerResultBox.innerHTML = `
          <strong>[✓] Smart Showreel Assembled!</strong><br>
          • Target Duration: ${data.target_duration_sec}s | Assembled: ${data.assembled_duration_sec.toFixed(1)}s (${data.shots_count} shots)<br>
          • Pacing Rhythm: Alternating Shot Scales | Minimized Kelvin Jump<br><br>
          <table style="width: 100%; font-size: 11px; border-collapse: collapse; text-align: left; background: #121419; border-radius: 4px;">
            <thead>
              <tr style="border-bottom: 1px solid #333; color: #888;">
                <th style="padding: 4px 8px;">Cut</th>
                <th style="padding: 4px 8px;">Take</th>
                <th style="padding: 4px 8px;">Scale</th>
                <th style="padding: 4px 8px;">Key</th>
                <th style="padding: 4px 8px;">Dur</th>
                <th style="padding: 4px 8px;">Score</th>
              </tr>
            </thead>
            <tbody>${rowsHtml}</tbody>
          </table>
        `;
      } else {
        composerResultBox.innerHTML = `<span style="color: #ff6666;">Error assembling showreel: ${data.error || 'Failed'}</span>`;
      }
    } catch (err) {
      if (composerResultBox) {
        composerResultBox.innerHTML = `<span style="color: #ff6666;">Communication error: ${err}</span>`;
      }
    } finally {
      btnComposerAssemble.disabled = false;
      btnComposerAssemble.textContent = 'Assemble Smart Reel';
    }
  });
}

// ============================================================================
// Multi-Cam Cross-Angle Continuity & ASC CDL Match Controller (M29)
// ============================================================================
const btnOpenMulticam = document.getElementById('btn-open-multicam');
const multicamModal = document.getElementById('multicam-modal');
const modalMulticamClose = document.getElementById('modal-multicam-close');
const btnMulticamClose = document.getElementById('btn-multicam-close');
const multicamScoreBadge = document.getElementById('multicam-score-badge');
const multicamSummaryBar = document.getElementById('multicam-summary-bar');
const multicamGrid = document.getElementById('multicam-grid');

function closeMulticamModal() {
  if (multicamModal) multicamModal.style.display = 'none';
}

if (modalMulticamClose) modalMulticamClose.addEventListener('click', closeMulticamModal);
if (btnMulticamClose) btnMulticamClose.addEventListener('click', closeMulticamModal);

if (btnOpenMulticam && multicamModal) {
  btnOpenMulticam.addEventListener('click', async () => {
    multicamModal.style.display = 'flex';
    if (multicamGrid) multicamGrid.innerHTML = '<div style="padding: 24px; text-align: center; color: #888;">Evaluating cross-angle color temperature, exposure EV deltas, and synthesizing ASC CDLs...</div>';

    try {
      const res = await fetch('/api/multicam_matching');
      const data = await res.json();
      if (data && data.pairwise_matches) {
        if (multicamScoreBadge) {
          multicamScoreBadge.textContent = `Consistency: ${data.overall_consistency_score.toFixed(0)}%`;
        }

        if (multicamSummaryBar) {
          multicamSummaryBar.innerHTML = `
            <div style="flex: 1;"><span style="color: #64748b; font-size: 11px;">HERO MASTER</span><br><strong style="color: #ffbe5b; font-size: 14px;">${data.hero_master_take_id}</strong></div>
            <div style="flex: 1;"><span style="color: #64748b; font-size: 11px;">SETUPS COMPARED</span><br><strong style="font-size: 14px;">${data.total_takes} Angles</strong></div>
            <div style="flex: 1;"><span style="color: #64748b; font-size: 11px;">AVG SCENE ΔE</span><br><strong style="color: ${data.average_scene_delta_e < 2.0 ? '#4ade80' : '#f59e0b'}; font-size: 14px;">${data.average_scene_delta_e.toFixed(1)} ΔE</strong></div>
            <div style="flex: 1;"><span style="color: #64748b; font-size: 11px;">MAX EXPOSURE Δ</span><br><strong style="font-size: 14px;">${data.max_exposure_stops_delta.toFixed(2)} EV</strong></div>
            <div style="flex: 1;"><span style="color: #64748b; font-size: 11px;">MAX KELVIN DRIFT</span><br><strong style="font-size: 14px;">${data.max_kelvin_delta.toFixed(0)}K</strong></div>
          `;
        }

        if (multicamGrid) {
          multicamGrid.innerHTML = '';
          data.pairwise_matches.forEach((m, idx) => {
            const isMaster = idx === 0;
            const statusColor = isMaster ? '#38bdf8' : (m.color_delta_e < 2.0 ? '#4ade80' : (m.color_delta_e < 3.5 ? '#f59e0b' : '#ef4444'));
            const cdl = m.recommended_cdl || {};
            const slopeStr = cdl.slope ? `${cdl.slope[0].toFixed(3)}, ${cdl.slope[1].toFixed(3)}, ${cdl.slope[2].toFixed(3)}` : '1.0, 1.0, 1.0';
            const offsetStr = cdl.offset ? `${cdl.offset[0].toFixed(3)}, ${cdl.offset[1].toFixed(3)}, ${cdl.offset[2].toFixed(3)}` : '0.0, 0.0, 0.0';
            const powerStr = cdl.power ? `${cdl.power[0].toFixed(3)}, ${cdl.power[1].toFixed(3)}, ${cdl.power[2].toFixed(3)}` : '1.0, 1.0, 1.0';

            const card = document.createElement('div');
            card.style.cssText = 'background: #111827; border: 1px solid rgba(148, 163, 184, 0.15); border-radius: 6px; padding: 14px 18px; display: flex; flex-direction: column; gap: 10px;';
            card.innerHTML = `
              <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(148, 163, 184, 0.1); padding-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                  <strong style="color: #fff; font-size: 14px;">${m.source_take_id}</strong>
                  <span style="color: #64748b; font-size: 12px;">vs. Hero Master (${m.target_take_id})</span>
                  <span style="background: rgba(15, 23, 42, 0.8); color: ${statusColor}; border: 1px solid ${statusColor}; font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 600;">${m.match_status}</span>
                </div>
                ${!isMaster ? `
                <div style="display: flex; gap: 8px;">
                  <a href="/api/export_cdl?source=${encodeURIComponent(m.source_take_id)}&target=${encodeURIComponent(m.target_take_id)}" class="btn btn-secondary btn-sm" download style="text-decoration: none; font-size: 11px; padding: 3px 10px;">Export .CDL</a>
                  <a href="/api/export_lut_cube?source=${encodeURIComponent(m.source_take_id)}&target=${encodeURIComponent(m.target_take_id)}" class="btn btn-secondary btn-sm" download style="text-decoration: none; font-size: 11px; padding: 3px 10px;">Export .CUBE</a>
                </div>` : '<span style="color: #38bdf8; font-size: 12px; font-weight: 600;">Hero Anchor</span>'}
              </div>

              <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; font-size: 12px; background: rgba(15, 23, 42, 0.5); padding: 8px 12px; border-radius: 4px;">
                <div><span style="color: #64748b;">Exposure Δ:</span> <strong style="color: ${m.exposure_stops_delta < 0 ? '#38bdf8' : '#f59e0b'};">${m.exposure_stops_delta > 0 ? '+' : ''}${m.exposure_stops_delta} EV</strong></div>
                <div><span style="color: #64748b;">Kelvin Shift:</span> <strong>${m.kelvin_delta > 0 ? '+' : ''}${m.kelvin_delta}K</strong></div>
                <div><span style="color: #64748b;">Color ΔE:</span> <strong style="color: ${statusColor};">${m.color_delta_e} ΔE</strong></div>
                <div><span style="color: #64748b;">Key:Fill Δ:</span> <strong>${m.key_to_fill_ratio_delta > 0 ? '+' : ''}${m.key_to_fill_ratio_delta}</strong></div>
                <div><span style="color: #64748b;">Sharpness Ratio:</span> <strong>${m.sharpness_ratio}×</strong></div>
              </div>

              <div style="font-size: 12px; color: #94a3b8; display: flex; align-items: center; gap: 8px;">
                <span style="color: #ffbe5b; font-weight: 600;">Grading Directive:</span>
                <span>${cdl.summary_guidance || 'None'}</span>
              </div>

              ${!isMaster ? `
              <div style="font-family: monospace; font-size: 11px; color: #64748b; background: rgba(0, 0, 0, 0.3); padding: 6px 10px; border-radius: 4px;">
                ASC CDL &bull; Slope [${slopeStr}] &bull; Offset [${offsetStr}] &bull; Power [${powerStr}] &bull; Sat [${cdl.saturation || 1.0}]
              </div>` : ''}
            `;
            multicamGrid.appendChild(card);
          });
        }
      } else {
        if (multicamGrid) multicamGrid.innerHTML = `<div style="color: #ef4444; padding: 20px;">Failed to evaluate multi-camera setups: ${data.error || 'No active takes'}</div>`;
      }
    } catch (err) {
      if (multicamGrid) multicamGrid.innerHTML = `<div style="color: #ef4444; padding: 20px;">Error communicating with server: ${err}</div>`;
    }
  });
}

// Media Server Baseline Ingest Modal & Deduplication Controller
// ============================================================================
const btnServerIngest = document.getElementById('btn-server-ingest');
const ingestModal = document.getElementById('server-ingest-modal');
const modalClose = document.getElementById('modal-ingest-close');
const btnIngestCancel = document.getElementById('btn-ingest-cancel');
const btnIngestStart = document.getElementById('btn-ingest-start');
const ingestPathInput = document.getElementById('server-ingest-path');
const ingestLimitInput = document.getElementById('server-ingest-limit');
const ingestShotsInput = document.getElementById('server-ingest-shots');
const ingestForceCheck = document.getElementById('server-ingest-force');
const ingestStatusBox = document.getElementById('server-ingest-status');

if (btnServerIngest && ingestModal) {
  btnServerIngest.addEventListener('click', () => {
    ingestModal.style.display = 'flex';
    if (ingestStatusBox) ingestStatusBox.style.display = 'none';
  });
}

function closeIngestModal() {
  if (ingestModal) ingestModal.style.display = 'none';
}

if (modalClose) modalClose.addEventListener('click', closeIngestModal);
if (btnIngestCancel) btnIngestCancel.addEventListener('click', closeIngestModal);

if (btnIngestStart) {
  btnIngestStart.addEventListener('click', async () => {
    const path = ingestPathInput ? ingestPathInput.value.trim() : 'M:\\movies';
    const limit = ingestLimitInput ? parseInt(ingestLimitInput.value, 10) || 5 : 5;
    const shots = ingestShotsInput ? parseInt(ingestShotsInput.value, 10) || 5 : 5;
    const force = ingestForceCheck ? ingestForceCheck.checked : false;

    if (ingestStatusBox) {
      ingestStatusBox.style.display = 'block';
      ingestStatusBox.innerHTML = `Scanning ${path}...<br>Checking against 184 canonical awards titles...<br>Deduplication: ${force ? 'FORCED (re-extracting)' : 'ENABLED (skipping previous)'}`;
    }

    btnIngestStart.disabled = true;
    btnIngestStart.textContent = 'Ingesting...';

    try {
      const url = `/api/ingest_server?path=${encodeURIComponent(path)}&limit=${limit}&shots=${shots}&force=${force}`;
      const res = await fetch(url);
      const data = await res.json();

      if (data.success && data.report) {
        const r = data.report;
        ingestStatusBox.innerHTML = `
          <strong>[✓] Ingestion Complete!</strong><br>
          • Matched in Library: ${r.matched_films} films<br>
          • Ingested This Batch: ${r.ingested_films} films (${r.total_shots_added} shots)<br>
          • Skipped (Already Present): ${r.skipped_films} films<br>
          • Total Baseline Corpus: ${r.total_corpus_shots} shots<br>
          • Dynamic Range (p50): ${r.dynamic_range_p50.toFixed(1)} stops<br>
          • Highlight Roll-Off (p50): ${r.highlight_rolloff_p50.toFixed(1)}%<br>
          ${r.processed_titles && r.processed_titles.length ? `<small>Ingested: ${r.processed_titles.join(', ')}</small>` : ''}
        `;
      } else {
        ingestStatusBox.innerHTML = `<span style="color: #ff6666;">Error: ${data.error || 'Ingestion failed'}</span>`;
      }
    } catch (err) {
      if (ingestStatusBox) {
        ingestStatusBox.innerHTML = `<span style="color: #ff6666;">Network/Server error: ${err}</span>`;
      }
    } finally {
      btnIngestStart.disabled = false;
      btnIngestStart.textContent = 'Start Ingestion';
    }
  });
}

// ============================================================================
// Initialize Workspace
// ============================================================================
loadSelects();
fetchFrameData(currentTime);
console.log('AESTHETIC Desktop Shell Active: Zero-Scroll UI, Smooth Scopes, True Frame Decoders.');
