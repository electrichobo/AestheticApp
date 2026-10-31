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
  } catch (err) {
    console.warn('Backend polling error:', err);
  }
}

// Update the 4-Output Cinematographic Matrix UI
function updateEvaluationUI(data) {
  if (!data) return;

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

  // 3. Technical Concerns
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

// Wire Header Action Buttons
const btnOpen = document.getElementById('btn-open-file');
if (btnOpen) {
  btnOpen.addEventListener('click', async () => {
    try {
      const browseRes = await fetch('/api/browse_file');
      const browseData = await browseRes.json();
      if (!browseData.success || !browseData.path) return;

      const filePath = browseData.path;
      const res = await fetch(`/api/open_media?path=${encodeURIComponent(filePath)}`);
      const data = await res.json();
      if (data.success && data.media) {
        videoDuration = data.media.duration_sec || 60.0;
        alert(`Loaded: ${data.media.file_path}\nCodec: ${data.media.codec}\nDuration: ${videoDuration.toFixed(1)}s (${data.media.width}x${data.media.height})`);
        fetchFrameData(currentTime);
      } else {
        alert(`Failed to load media: ${data.error || 'Unknown error'}`);
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

      alert(`Selected for Baseline Ingestion: ${browseData.path}\nReady for baseline calibration.`);
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

// Wire Timeline Scrubbing
const track = document.getElementById('timeline-track');
const playhead = document.getElementById('playhead');
if (track && playhead) {
  let isDragging = false;
  const updateScrub = (e) => {
    const rect = track.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    playhead.style.left = `${ratio * 100}%`;
    const newTime = ratio * videoDuration;
    fetchFrameData(newTime);
  };

  track.addEventListener('mousedown', (e) => {
    isDragging = true;
    updateScrub(e);
  });

  window.addEventListener('mousemove', (e) => {
    if (isDragging) updateScrub(e);
  });

  window.addEventListener('mouseup', () => {
    isDragging = false;
  });
}

// Populate initial candidate selects list
function populateSelects() {
  const takesList = document.getElementById('takes-list');
  const countBadge = document.getElementById('take-count-badge');
  if (!takesList) return;

  const demoTakes = [
    { id: 'Take 01', range: '00:00:14:05 – 00:00:18:17', dur: '4.5s', score: '92.4', style: 'Roger Deakins [Skyfall]' },
    { id: 'Take 02', range: '00:00:32:00 – 00:00:35:20', dur: '3.8s', score: '88.7', style: 'Greig Fraser [Dune]' }
  ];

  if (countBadge) countBadge.textContent = `${demoTakes.length} Takes`;
  takesList.innerHTML = '';

  demoTakes.forEach((t, i) => {
    const item = document.createElement('div');
    item.className = `take-item ${i === 0 ? 'active' : ''}`;
    item.innerHTML = `
      <div class="take-title-row">
        <span class="take-name">${t.id}</span>
        <span class="take-score">${t.score}</span>
      </div>
      <div class="take-details">${t.range} (${t.dur})</div>
      <div class="take-style-tag">${t.style}</div>
    `;
    item.addEventListener('click', () => {
      document.querySelectorAll('.take-item').forEach(el => el.classList.remove('active'));
      item.classList.add('active');
      fetchFrameData(i === 0 ? 16.0 : 33.5);
    });
    takesList.appendChild(item);
  });
}

// Initial initialization
populateSelects();
fetchFrameData(currentTime);
console.log('AESTHETIC Scopes & Evaluation Matrix active.');
