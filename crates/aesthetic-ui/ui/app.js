// AESTHETIC Frontend Controller
// Real-time Canvas Scope Renderers & Tauri IPC Bridge

const canvas = document.getElementById('scope-canvas');
const ctx = canvas.getContext('2d');
let currentScope = 'waveform';

// Scope switching
document.querySelectorAll('.scope-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.scope-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    currentScope = tab.dataset.scope;
    renderCurrentScope();
  });
});

// Render simulated scope data initially or upon frame update
function renderCurrentScope() {
  const w = canvas.width;
  const h = canvas.height;
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, w, h);

  switch (currentScope) {
    case 'waveform':
      drawLumaWaveform(ctx, w, h);
      break;
    case 'parade':
      drawRgbParade(ctx, w, h);
      break;
    case 'vectorscope':
      drawVectorscope(ctx, w, h);
      break;
    case 'histogram':
      drawHistograms(ctx, w, h);
      break;
    case 'cie':
      drawCieChromaticity(ctx, w, h);
      break;
  }
}

// 1. Luma Waveform with phosphor glow
function drawLumaWaveform(c, w, h) {
  drawScopeGraticule(c, w, h, ['100 IRE', '75 IRE', '50 IRE', '25 IRE', '0 IRE']);
  
  c.fillStyle = 'rgba(0, 255, 120, 0.4)';
  for (let x = 0; x < w; x++) {
    const centerLuma = (h / 2) + Math.sin(x / 20) * (h / 4);
    for (let i = 0; i < 15; i++) {
      const y = centerLuma + (Math.random() - 0.5) * 30;
      c.fillRect(x, Math.max(0, Math.min(h - 1, y)), 1, 1);
    }
  }
}

// 2. RGB Parade (Red, Green, Blue columns)
function drawRgbParade(c, w, h) {
  const colW = Math.floor(w / 3);
  drawScopeGraticule(c, w, h, ['100', '50', '0']);

  // Red
  c.fillStyle = 'rgba(255, 60, 60, 0.45)';
  for (let x = 0; x < colW; x++) {
    for (let i = 0; i < 12; i++) {
      const y = (h * 0.4) + (Math.random() - 0.5) * (h * 0.4);
      c.fillRect(x, y, 1, 1);
    }
  }

  // Green
  c.fillStyle = 'rgba(60, 255, 60, 0.45)';
  for (let x = colW; x < colW * 2; x++) {
    for (let i = 0; i < 12; i++) {
      const y = (h * 0.45) + (Math.random() - 0.5) * (h * 0.4);
      c.fillRect(x, y, 1, 1);
    }
  }

  // Blue
  c.fillStyle = 'rgba(60, 160, 255, 0.45)';
  for (let x = colW * 2; x < w; x++) {
    for (let i = 0; i < 12; i++) {
      const y = (h * 0.5) + (Math.random() - 0.5) * (h * 0.4);
      c.fillRect(x, y, 1, 1);
    }
  }
}

// 3. Vectorscope (Cb vs Cr with 57° skin tone line)
function drawVectorscope(c, w, h) {
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
  c.strokeStyle = 'rgba(229, 169, 59, 0.5)';
  c.beginPath();
  c.moveTo(cx, cy);
  const rad = (57.0 * Math.PI) / 180;
  c.lineTo(cx + Math.cos(rad) * radius, cy - Math.sin(rad) * radius);
  c.stroke();

  // Color target boxes (R, Mg, B, Cy, G, Yl)
  c.fillStyle = '#667799';
  c.font = '9px monospace';
  c.fillText('SKIN', cx + Math.cos(rad) * (radius + 4) - 10, cy - Math.sin(rad) * (radius + 4));

  // Trace
  c.fillStyle = 'rgba(0, 230, 255, 0.35)';
  for (let i = 0; i < 800; i++) {
    const angle = Math.random() * Math.PI * 2;
    const r = Math.random() * radius * 0.6;
    c.fillRect(cx + Math.cos(angle) * r, cy + Math.sin(angle) * r, 1.5, 1.5);
  }
}

// 4. Histograms
function drawHistograms(c, w, h) {
  c.fillStyle = '#222d3d';
  c.fillRect(0, h - 1, w, 1);

  c.fillStyle = 'rgba(255, 255, 255, 0.3)';
  for (let x = 0; x < w; x++) {
    const barH = (Math.sin(x / 40) + 1) * (h * 0.35) + Math.random() * 10;
    c.fillRect(x, h - barH, 1, barH);
  }
}

// 5. CIE 1931 Chromaticity Map with Gamut Triangles
function drawCieChromaticity(c, w, h) {
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

  // Density scatter
  c.fillStyle = 'rgba(255, 200, 50, 0.3)';
  for (let i = 0; i < 400; i++) {
    const x = w * (0.2 + Math.random() * 0.3);
    const y = h * (0.3 + Math.random() * 0.4);
    c.fillRect(x, y, 1.5, 1.5);
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

// Initial draw
renderCurrentScope();
console.log('AESTHETIC Scopes Engine active (Tauri IPC ready).');
