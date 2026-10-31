// AESTHETIC Frontend Controller
// Real-time Canvas Scope Renderers & Backend API Bridge

const canvas = document.getElementById('scope-canvas');
const ctx = canvas.getContext('2d');
let currentScope = 'waveform';
let currentScopesData = null;
let currentEvaluateData = null;
let currentTime = 14.5;
let videoDuration = 60.0;

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
  const totalFrames = Math.round(sec * fps);
  const frames = totalFrames % fps;
  const totalSec = Math.floor(totalFrames / fps);
  const s = totalSec % 60;
  const m = Math.floor(totalSec / 60) % 60;
  const h = Math.floor(totalSec / 3600);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}:${String(frames).padStart(2, '0')}`;
}

// Fetch live scopes and evaluation from Rust backend
async function fetchFrameData(timeSec) {
  try {
    currentTime = timeSec;
    const [scopesRes, evalRes] = await Promise.all([
      fetch(`/api/scopes?time=${timeSec}`),
      fetch(`/api/evaluate?time=${timeSec}`)
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

// Update the 4-Output Cinematographic Matrix UI
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

  // 2. Discovered Style & Master DP Match
  if (data.style) {
    const lTag = document.getElementById('lighting-key-tag');
    if (lTag) lTag.textContent = `Lighting: ${data.style.lighting_key || 'Unknown'}`;

    const mTag = document.getElementById('motion-pacing-tag');
    if (mTag) mTag.textContent = `Motion: ${data.style.motion_type || 'Unknown'}`;

    const masterText = document.getElementById('master-text');
    if (masterText) {
      if (data.style.cinematographer_match) {
        masterText.textContent = `${data.style.cinematographer_match} (${Math.round(data.style.match_confidence || 90)}% Match)`;
      } else {
        masterText.textContent = 'Golden Baseline Cinema Match';
      }
    }
  }

  // 3. Benchmark Comparison Table
  const dpBadge = document.getElementById('benchmark-dp-badge');
  const tableBody = document.getElementById('benchmark-table-body');
  if (tableBody) {
    tableBody.innerHTML = '';
    const comp = resData.comparison;
    if (comp && comp.rows) {
      if (dpBadge) dpBadge.textContent = `${comp.dp_name} [${comp.reference_film}] (${comp.similarity}% Match)`;
      comp.rows.forEach(r => {
        const tr = document.createElement('tr');
        let pillClass = 'status-optimal';
        if (r.status.includes('Needs') || r.status.includes('Steep') || r.status.includes('Short-Sided')) {
          pillClass = 'status-warning';
        } else if (r.status.includes('Subdued') || r.status.includes('Clip')) {
          pillClass = 'status-alert';
        }
        tr.innerHTML = `
          <td><strong>${r.metric}</strong></td>
          <td>${r.shot_val}</td>
          <td>${r.target_val}</td>
          <td><span class="status-pill ${pillClass}">${r.status}</span></td>
        `;
        tableBody.appendChild(tr);
      });
    }
  }

  // 4. Cinematographic Improvement Action Cards
  const actionsList = document.getElementById('action-cards-list');
  if (actionsList) {
    actionsList.innerHTML = '';
    const actions = resData.actions || [];
    if (actions.length === 0) {
      actionsList.innerHTML = '<div class="concern-item clean">All metrics align closely with Golden Baseline standards.</div>';
    } else {
      actions.forEach(a => {
        const card = document.createElement('div');
        const pillType = (a.priority || '').toLowerCase();
        const pilClass = a.pillar === 'Technical' ? 'technical' : (pillType === 'optimal' ? 'optimal' : 'creative');
        card.className = `action-card ${pilClass}`;
        card.innerHTML = `
          <div class="action-card-header">
            <span class="action-card-category">${a.category}</span>
            <span class="action-card-pillar">${a.pillar} · ${a.priority}</span>
          </div>
          <div class="action-card-text">${a.recommendation}</div>
        `;
        actionsList.appendChild(card);
      });
    }
  }

  // 5. Technical Concerns
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

// Render the selected scope onto HTML5 Canvas
function renderCurrentScope() {
  const w = canvas.width;
  const h = canvas.height;
  ctx.fillStyle = '#0a0d14';
  ctx.fillRect(0, 0, w, h);

  if (!currentScopesData) {
    drawScopeGraticule(ctx, w, h, ['100 IRE', '75 IRE', '50 IRE', '25 IRE', '0 IRE']);
    return;
  }

  switch (currentScope) {
    case 'waveform':
      drawLumaWaveform(ctx, w, h, currentScopesData.waveform);
      break;
    case 'parade':
      drawRgbParade(ctx, w, h, currentScopesData.parade);
      break;
    case 'vectorscope':
      drawVectorscope(ctx, w, h, currentScopesData.vectorscope);
      break;
    case 'histogram':
      drawHistograms(ctx, w, h, currentScopesData.histogram);
      break;
    case 'cie':
      drawCieChromaticity(ctx, w, h, currentScopesData.cie);
      break;
  }
}

// 1. Luma Waveform with phosphor density curve
function drawLumaWaveform(c, w, h, wf) {
  drawScopeGraticule(c, w, h, ['100 IRE', '75 IRE', '50 IRE', '25 IRE', '0 IRE']);
  if (!wf || !wf.density) return;

  const cols = wf.columns;
  const ireLevels = wf.ire_levels;
  const colW = w / cols;

  for (let col = 0; col < cols; col++) {
    for (let ire = 0; ire < ireLevels; ire++) {
      const d = wf.density[col * ireLevels + ire];
      if (d > 0.02) {
        const y = h - (ire / ireLevels) * h;
        c.fillStyle = `rgba(0, 255, 120, ${d * 0.75})`;
        c.fillRect(col * colW, y, Math.max(1, colW), 2);
      }
    }
  }
}

// 2. RGB Parade (Red, Green, Blue columns)
function drawRgbParade(c, w, h, p) {
  const colW = Math.floor(w / 3);
  drawScopeGraticule(c, w, h, ['100', '50', '0']);
  if (!p || !p.r_density) return;

  const cols = p.columns;
  const ireLevels = p.ire_levels;
  const subColW = colW / cols;

  // Red
  for (let col = 0; col < cols; col++) {
    for (let ire = 0; ire < ireLevels; ire++) {
      const d = p.r_density[col * ireLevels + ire];
      if (d > 0.02) {
        const y = h - (ire / ireLevels) * h;
        c.fillStyle = `rgba(255, 60, 60, ${d * 0.8})`;
        c.fillRect(col * subColW, y, Math.max(1, subColW), 2);
      }
    }
  }

  // Green
  for (let col = 0; col < cols; col++) {
    for (let ire = 0; ire < ireLevels; ire++) {
      const d = p.g_density[col * ireLevels + ire];
      if (d > 0.02) {
        const y = h - (ire / ireLevels) * h;
        c.fillStyle = `rgba(60, 255, 60, ${d * 0.8})`;
        c.fillRect(colW + col * subColW, y, Math.max(1, subColW), 2);
      }
    }
  }

  // Blue
  for (let col = 0; col < cols; col++) {
    for (let ire = 0; ire < ireLevels; ire++) {
      const d = p.b_density[col * ireLevels + ire];
      if (d > 0.02) {
        const y = h - (ire / ireLevels) * h;
        c.fillStyle = `rgba(60, 160, 255, ${d * 0.8})`;
        c.fillRect(colW * 2 + col * subColW, y, Math.max(1, subColW), 2);
      }
    }
  }
}

// 3. Vectorscope (Cb vs Cr with 57° skin tone line)
function drawVectorscope(c, w, h, vs) {
  const cx = w / 2;
  const cy = h / 2;
  const radius = Math.min(w, h) * 0.42;

  // Graticule circles
  c.strokeStyle = '#222d3d';
  c.lineWidth = 1;
  c.beginPath();
  c.arc(cx, cy, radius, 0, Math.PI * 2);
  c.arc(cx, cy, radius * 0.75, 0, Math.PI * 2);
  c.stroke();

  // Skin tone I-line (~57 degrees)
  c.strokeStyle = 'rgba(229, 169, 59, 0.7)';
  c.beginPath();
  c.moveTo(cx, cy);
  const rad = (57.0 * Math.PI) / 180;
  c.lineTo(cx + Math.cos(rad) * radius, cy - Math.sin(rad) * radius);
  c.stroke();

  c.fillStyle = '#e5a93b';
  c.font = '9px monospace';
  c.fillText('SKIN', cx + Math.cos(rad) * (radius + 4) - 10, cy - Math.sin(rad) * (radius + 4));

  if (!vs || !vs.density) return;
  const res = vs.resolution;

  for (let y = 0; y < res; y++) {
    for (let x = 0; x < res; x++) {
      const d = vs.density[y * res + x];
      if (d > 0.05) {
        const px = cx + ((x - res / 2) / (res / 2)) * radius;
        const py = cy + ((y - res / 2) / (res / 2)) * radius;
        c.fillStyle = `rgba(0, 230, 255, ${d * 0.8})`;
        c.fillRect(px, py, 1.5, 1.5);
      }
    }
  }
}

// 4. Histograms (Luma, R, G, B)
function drawHistograms(c, w, h, hist) {
  c.fillStyle = '#222d3d';
  c.fillRect(0, h - 1, w, 1);
  if (!hist || !hist.luma) return;

  const maxVal = Math.max(...hist.luma, ...hist.r, ...hist.g, ...hist.b, 1);

  // Draw Luma curve
  c.fillStyle = 'rgba(255, 255, 255, 0.35)';
  for (let i = 0; i < 256; i++) {
    const x = (i / 256) * w;
    const barH = (hist.luma[i] / maxVal) * (h * 0.8);
    c.fillRect(x, h - barH, w / 256 + 1, barH);
  }

  // Draw R, G, B outline traces
  const channels = [
    { data: hist.r, color: 'rgba(255, 80, 80, 0.7)' },
    { data: hist.g, color: 'rgba(80, 255, 80, 0.7)' },
    { data: hist.b, color: 'rgba(80, 160, 255, 0.7)' }
  ];

  channels.forEach(ch => {
    c.strokeStyle = ch.color;
    c.beginPath();
    for (let i = 0; i < 256; i++) {
      const x = (i / 256) * w;
      const y = h - (ch.data[i] / maxVal) * (h * 0.8);
      if (i === 0) c.moveTo(x, y);
      else c.lineTo(x, y);
    }
    c.stroke();
  });
}

// 5. CIE 1931 Chromaticity Map with sRGB Gamut Overlay
function drawCieChromaticity(c, w, h, cie) {
  // sRGB triangle
  c.strokeStyle = 'rgba(0, 255, 120, 0.8)';
  c.lineWidth = 1.5;
  c.beginPath();
  c.moveTo(w * 0.64, h * (1 - 0.33));
  c.lineTo(w * 0.30, h * (1 - 0.60));
  c.lineTo(w * 0.15, h * (1 - 0.06));
  c.closePath();
  c.stroke();

  c.fillStyle = 'rgba(0, 255, 120, 0.8)';
  c.font = '9px monospace';
  c.fillText('sRGB', w * 0.32, h * (1 - 0.61));

  if (!cie || !cie.density) return;
  const res = cie.grid_size;

  for (let y = 0; y < res; y++) {
    for (let x = 0; x < res; x++) {
      const d = cie.density[y * res + x];
      if (d > 0.05) {
        const px = (x / res) * w;
        const py = h - (y / res) * h;
        c.fillStyle = `rgba(255, 200, 50, ${d * 0.85})`;
        c.fillRect(px, py, 1.5, 1.5);
      }
    }
  }
}

function drawScopeGraticule(c, w, h, labels) {
  c.strokeStyle = '#1b2230';
  c.lineWidth = 1;
  c.font = '9px monospace';
  c.fillStyle = '#445566';

  const step = h / (labels.length - 1);
  labels.forEach((lbl, idx) => {
    const y = idx * step;
    c.beginPath();
    c.moveTo(0, y);
    c.lineTo(w, y);
    c.stroke();
    c.fillText(lbl, 4, y + 9);
  });
}

// ============================================================================
// Stage 2: Diagnostic Viewport Modes & Forensic Overlays
// ============================================================================
let activeViewportMode = 'picture';
const vpButtons = document.querySelectorAll('.vp-btn');
const overlayImg = document.getElementById('diagnostic-overlay-img');
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
  if (!overlayImg) return;

  if (activeViewportMode === 'picture') {
    overlayImg.style.display = 'none';
    if (vectorCanvas) vectorCanvas.style.display = 'none';
    if (elZoneLegend) elZoneLegend.style.display = 'none';
  } else if (activeViewportMode === 'el_zone') {
    overlayImg.src = `/api/frame_el_zone?time=${currentTime}&_t=${Date.now()}`;
    overlayImg.style.display = 'block';
    if (vectorCanvas) vectorCanvas.style.display = 'none';
    if (elZoneLegend) elZoneLegend.style.display = 'flex';
  } else if (activeViewportMode === 'peaking') {
    overlayImg.src = `/api/frame_peaking?time=${currentTime}&_t=${Date.now()}`;
    overlayImg.style.display = 'block';
    if (vectorCanvas) vectorCanvas.style.display = 'none';
    if (elZoneLegend) elZoneLegend.style.display = 'none';
  } else if (activeViewportMode === 'volumetric') {
    overlayImg.style.display = 'none';
    if (elZoneLegend) elZoneLegend.style.display = 'none';
    if (vectorCanvas) {
      vectorCanvas.style.display = 'block';
      drawVolumetricLight(currentEvaluateData?.craft?.lighting);
    }
  } else if (activeViewportMode === 'gaze') {
    overlayImg.style.display = 'none';
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

  // 3D Light Compass in the top-right
  const cx = Math.max(120, w - 120);
  const cy = 110;
  const radius = 55;

  // Background Dial
  vectorCtx.beginPath();
  vectorCtx.arc(cx, cy, radius, 0, Math.PI * 2);
  vectorCtx.fillStyle = 'rgba(10, 12, 16, 0.85)';
  vectorCtx.fill();
  vectorCtx.lineWidth = 2;
  vectorCtx.strokeStyle = '#252d3d';
  vectorCtx.stroke();

  // Crosshairs
  vectorCtx.strokeStyle = 'rgba(139, 148, 158, 0.3)';
  vectorCtx.lineWidth = 1;
  vectorCtx.beginPath();
  vectorCtx.moveTo(cx - radius, cy);
  vectorCtx.lineTo(cx + radius, cy);
  vectorCtx.moveTo(cx, cy - radius);
  vectorCtx.lineTo(cx, cy + radius);
  vectorCtx.stroke();

  // Subject Head Silhouette icon at center
  vectorCtx.fillStyle = '#8b949e';
  vectorCtx.beginPath();
  vectorCtx.arc(cx, cy - 6, 8, 0, Math.PI * 2);
  vectorCtx.fill();
  vectorCtx.beginPath();
  vectorCtx.arc(cx, cy + 12, 14, Math.PI, 0);
  vectorCtx.fill();

  // Key Light Ray Vector
  const angleRad = ((azimuth - 90) * Math.PI) / 180;
  const lightX = cx + Math.cos(angleRad) * (radius - 8);
  const lightY = cy + Math.sin(angleRad) * (radius - 8);

  // Volumetric Light Beam
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

  // Source Bulb Indicator
  vectorCtx.beginPath();
  vectorCtx.arc(lightX, lightY, 6, 0, Math.PI * 2);
  vectorCtx.fillStyle = '#e5a93b';
  vectorCtx.fill();
  vectorCtx.strokeStyle = '#ffffff';
  vectorCtx.lineWidth = 2;
  vectorCtx.stroke();

  // Readouts badge below dial
  vectorCtx.fillStyle = 'rgba(10, 12, 16, 0.90)';
  vectorCtx.fillRect(cx - 85, cy + radius + 10, 170, 52);
  vectorCtx.strokeStyle = '#252d3d';
  vectorCtx.strokeRect(cx - 85, cy + radius + 10, 170, 52);

  vectorCtx.font = 'bold 11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
  vectorCtx.fillStyle = '#e5a93b';
  vectorCtx.textAlign = 'center';
  vectorCtx.fillText(`KEY: ${azimuth > 0 ? '+' : ''}${azimuth.toFixed(0)}° Az | ${elevation.toFixed(0)}° El`, cx, cy + radius + 28);
  vectorCtx.fillStyle = '#00d2ff';
  vectorCtx.fillText(`Key:Fill: ${ratio.toFixed(1)}:1  •  Catch: ${catchlight.toFixed(0)}%`, cx, cy + radius + 46);
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
  const gazeY = staging && staging.gaze_vector_y != null ? staging.gaze_vector_y : -0.10;
  const lookingRoom = staging && staging.looking_room_score != null ? staging.looking_room_score : 85;
  const poise = staging && staging.gaze_poise_score != null ? staging.gaze_poise_score : 88;

  // 1. Rule-of-Thirds Grid
  vectorCtx.strokeStyle = 'rgba(229, 169, 59, 0.28)';
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

  // Eyeline tag
  vectorCtx.font = '10px "SF Mono", "Fira Code", monospace';
  vectorCtx.fillStyle = '#e5a93b';
  vectorCtx.textAlign = 'left';
  vectorCtx.fillText('EYELINE (RULE OF THIRDS)', 14, yThird1 - 6);

  // 2. Subject Centroid and Reticle
  const subjNormX = gazeX > 0 ? 0.38 : 0.62;
  const subjNormY = 0.3333;
  const subPxX = w * subjNormX;
  const subPxY = h * subjNormY;

  const boxW = 80;
  const boxH = 95;
  vectorCtx.strokeStyle = '#00d2ff';
  vectorCtx.lineWidth = 1.5;
  vectorCtx.strokeRect(subPxX - boxW / 2, subPxY - boxH / 2, boxW, boxH);

  // Reticle corners
  vectorCtx.fillStyle = '#00d2ff';
  const cLen = 8;
  vectorCtx.fillRect(subPxX - boxW / 2 - 2, subPxY - boxH / 2 - 2, cLen, 2);
  vectorCtx.fillRect(subPxX - boxW / 2 - 2, subPxY - boxH / 2 - 2, 2, cLen);
  vectorCtx.fillRect(subPxX + boxW / 2 - cLen + 2, subPxY - boxH / 2 - 2, cLen, 2);
  vectorCtx.fillRect(subPxX + boxW / 2, subPxY - boxH / 2 - 2, 2, cLen);
  vectorCtx.fillRect(subPxX - boxW / 2 - 2, subPxY + boxH / 2, cLen, 2);
  vectorCtx.fillRect(subPxX - boxW / 2 - 2, subPxY + boxH / 2 - cLen + 2, 2, cLen);
  vectorCtx.fillRect(subPxX + boxW / 2 - cLen + 2, subPxY + boxH / 2, cLen, 2);
  vectorCtx.fillRect(subPxX + boxW / 2, subPxY + boxH / 2 - cLen + 2, 2, cLen);

  // 3. Directional Gaze Arrow
  const arrowLen = 140;
  const arrowEndX = subPxX + gazeX * arrowLen;
  const arrowEndY = subPxY + gazeY * arrowLen;

  vectorCtx.strokeStyle = '#00ff66';
  vectorCtx.lineWidth = 2.5;
  vectorCtx.beginPath();
  vectorCtx.moveTo(subPxX, subPxY);
  vectorCtx.lineTo(arrowEndX, arrowEndY);
  vectorCtx.stroke();

  // Arrowhead
  const headAngle = Math.atan2(arrowEndY - subPxY, arrowEndX - subPxX);
  const headLen = 12;
  vectorCtx.beginPath();
  vectorCtx.moveTo(arrowEndX, arrowEndY);
  vectorCtx.lineTo(
    arrowEndX - headLen * Math.cos(headAngle - Math.PI / 6),
    arrowEndY - headLen * Math.sin(headAngle - Math.PI / 6)
  );
  vectorCtx.moveTo(arrowEndX, arrowEndY);
  vectorCtx.lineTo(
    arrowEndX - headLen * Math.cos(headAngle + Math.PI / 6),
    arrowEndY - headLen * Math.sin(headAngle + Math.PI / 6)
  );
  vectorCtx.stroke();

  // 4. Staging HUD Card
  vectorCtx.fillStyle = 'rgba(10, 12, 16, 0.90)';
  vectorCtx.fillRect(16, h - 70, 240, 50);
  vectorCtx.strokeStyle = '#252d3d';
  vectorCtx.lineWidth = 1;
  vectorCtx.strokeRect(16, h - 70, 240, 50);

  vectorCtx.font = 'bold 11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto';
  vectorCtx.fillStyle = '#00ff66';
  vectorCtx.textAlign = 'left';
  vectorCtx.fillText(`GAZE POISE SCORE: ${poise.toFixed(0)} / 100`, 28, h - 48);
  vectorCtx.fillStyle = '#8b949e';
  vectorCtx.font = '10px "SF Mono", "Fira Code", monospace';
  vectorCtx.fillText(`Looking Room: ${lookingRoom.toFixed(0)}%  •  Lead: Screen ${gazeX > 0 ? 'Right' : 'Left'}`, 28, h - 30);
}

// ============================================================================
// Stage 1: In-App Showreel Assembly & Interactive Trim Handles
// ============================================================================
let currentInTime = 14.0;
let currentOutTime = 18.5;
let currentTakes = [];
let activeTakeIndex = 0;

const inHandle = document.getElementById('in-handle');
const outHandle = document.getElementById('out-handle');
const windowHighlight = document.getElementById('window-highlight');
const tcWindowInfo = document.getElementById('tc-window-info');
const tcCurrent = document.getElementById('tc-current');
const tcTotal = document.getElementById('tc-total');
const track = document.getElementById('timeline-track');
const playhead = document.getElementById('playhead');

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
  if (playhead) {
    playhead.style.left = `${playheadRatio * 100}%`;
  }

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
    // Only drag playhead if not clicking handle
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

// In-Handle Dragging
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
      const newIn = Math.min(ratio * videoDuration, currentOutTime - 0.5);
      currentInTime = Math.max(0, newIn);
      updateTimelineUI();
    }
  });

  window.addEventListener('mouseup', () => {
    isDraggingIn = false;
  });
}

// Out-Handle Dragging
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
      const newOut = Math.max(currentInTime + 0.5, ratio * videoDuration);
      currentOutTime = Math.min(videoDuration, newOut);
      updateTimelineUI();
    }
  });

  window.addEventListener('mouseup', () => {
    isDraggingOut = false;
  });
}

// Populate candidate selects list from backend API
async function loadSelects() {
  const takesList = document.getElementById('takes-list');
  const countBadge = document.getElementById('take-count-badge');
  if (!takesList) return;

  try {
    const res = await fetch('/api/selects');
    if (!res.ok) return;
    const data = await res.json();
    currentTakes = data.takes || [];
    if (data.duration) videoDuration = data.duration;

    if (countBadge) countBadge.textContent = `${currentTakes.length} Takes`;
    takesList.innerHTML = '';

    if (currentTakes.length === 0) {
      takesList.innerHTML = '<div class="empty-state">No takes found. Open a media file to evaluate.</div>';
      return;
    }

    currentTakes.forEach((t, i) => {
      const item = document.createElement('div');
      item.className = `take-item ${i === activeTakeIndex ? 'active' : ''}`;

      const score = Math.round(t.scores?.overall || 90);
      const startTc = formatTimecode(t.start_sec);
      const endTc = formatTimecode(t.end_sec);
      const dur = (t.duration_sec || (t.end_sec - t.start_sec)).toFixed(1);
      const match = t.style?.cinematographer_match || 'Golden Baseline Cinema';

      let decisionClass = 'decision-candidate';
      let decisionText = 'Candidate';
      if (t.recommendation === 'Hero Select' || i === 0) {
        decisionClass = 'decision-hero';
        decisionText = 'Hero Select';
      } else if (t.recommendation && t.recommendation.includes('Defect')) {
        decisionClass = 'decision-defect';
        decisionText = 'Defect Alert';
      }

      item.innerHTML = `
        <div class="take-title-row">
          <span class="take-name">${t.take_id || `Take ${String(i + 1).padStart(2, '0')}`}</span>
          <span class="take-score">${score}</span>
        </div>
        <div class="take-details">${startTc} – ${endTc} (${dur}s)</div>
        <div class="take-style-tag">${match}</div>
        <span class="take-decision-badge ${decisionClass}">${decisionText}</span>
      `;

      item.addEventListener('click', () => {
        document.querySelectorAll('.take-item').forEach(el => el.classList.remove('active'));
        item.classList.add('active');
        activeTakeIndex = i;
        currentInTime = t.start_sec;
        currentOutTime = t.end_sec;
        const heroTime = t.hero_timestamp_sec != null ? t.hero_timestamp_sec : (t.start_sec + (t.end_sec - t.start_sec) / 2);
        currentTime = heroTime;
        updateTimelineUI();
        fetchFrameData(heroTime);
      });

      takesList.appendChild(item);
    });

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

// Media Ingestion Flow
const btnOpen = document.getElementById('btn-open-file');
if (btnOpen) {
  btnOpen.addEventListener('click', async () => {
    try {
      const browseRes = await fetch('/api/browse_file');
      const browseData = await browseRes.json();
      if (!browseData.success || !browseData.path) return;

      const filePath = browseData.path;
      const takesList = document.getElementById('takes-list');
      if (takesList) {
        takesList.innerHTML = '<div class="empty-state">Analyzing video stream & computing cinematographic matrix...</div>';
      }

      const res = await fetch(`/api/analyze?path=${encodeURIComponent(filePath)}`);
      const data = await res.json();
      if (data.success) {
        await loadSelects();
      } else {
        const openRes = await fetch(`/api/open_media?path=${encodeURIComponent(filePath)}`);
        const openData = await openRes.json();
        if (openData.success && openData.media) {
          videoDuration = openData.media.duration_sec || 60.0;
          await loadSelects();
        } else {
          alert(`Failed to load media: ${data.error || openData.error || 'Unknown error'}`);
        }
      }
    } catch (err) {
      alert(`Error opening media: ${err}`);
    }
  });
}

const btnBaseline = document.getElementById('btn-baseline');
if (btnBaseline) {
  btnBaseline.addEventListener('click', async () => {
    try {
      const choice = confirm('Click OK to select a Reference Stills Directory, or Cancel to select a single Video or Still File.');
      const endpoint = choice ? '/api/browse_dir' : '/api/browse_file';
      const browseRes = await fetch(endpoint);
      const browseData = await browseRes.json();
      if (!browseData.success || !browseData.path) return;

      alert(`Selected for Baseline Ingestion: ${browseData.path}\nBaseline corpus will index reference craft profiles.`);
    } catch (err) {
      alert(`Error browsing baseline media: ${err}`);
    }
  });
}

// Wire Export Buttons
const btnExportSheet = document.getElementById('btn-export-sheet');
if (btnExportSheet) {
  btnExportSheet.addEventListener('click', () => {
    window.open('/api/export_contact_sheet', '_blank');
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

const btnWeb = document.getElementById('btn-web-url');
if (btnWeb) {
  btnWeb.addEventListener('click', async () => {
    const url = prompt('Enter video URL (YouTube, Vimeo):');
    if (!url) return;

    try {
      const res = await fetch(`/api/web_probe?url=${encodeURIComponent(url)}`);
      const data = await res.json();
      if (data.success) {
        alert(`URL Probed: ${data.info.title || url}\nDuration: ${data.info.duration_sec || 'N/A'}s`);
      } else {
        alert(`Failed to probe URL: ${data.error}`);
      }
    } catch (err) {
      alert(`Error probing URL: ${err}`);
    }
  });
}

// Initialize workspace
loadSelects();
fetchFrameData(currentTime);
console.log('AESTHETIC Stage 1 & Stage 2 Engine Active.');
