/* Utilidades compartidas + graficas en canvas (sin dependencias externas). */

const API = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
  async send(path, body, method = 'POST') {
    const r = await fetch(path, {
      method, headers: {'Content-Type': 'application/json'},
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    if (!r.ok) throw new Error((await r.text()) || r.statusText);
    return r.json();
  },
  del(path) { return this.send(path, undefined, 'DELETE'); },
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function toast(message, type = 'info', ms = 3800) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.innerHTML = `<span class="tag ${type}">${type}</span> ${message}`;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

function fmtTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString('es-MX', {day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'});
}
function fmtClock(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleTimeString('es-MX');
}
function fmtDur(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60), r = s % 60;
  if (m < 60) return `${m}m ${r}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}
function esc(text) {
  return String(text ?? '').replace(/[&<>"']/g, c => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

/* ------------------------------------------------------------------ */
/* Graficas                                                            */
/* ------------------------------------------------------------------ */
const PALETTE = ['#6ea8fe', '#9d8df1', '#4ade80', '#fbbf24', '#f87171', '#2dd4bf', '#f472b6'];

/* Tema claro / oscuro, recordado en el navegador. */
function themeGet() { try { return localStorage.getItem('ov-theme') || 'dark'; } catch (e) { return 'dark'; } }
function themeApply(t) {
  document.documentElement.setAttribute('data-theme', t);
  try { localStorage.setItem('ov-theme', t); } catch (e) {}
  const b = document.getElementById('theme-btn');
  if (b) b.textContent = t === 'dark' ? 'Claro' : 'Oscuro';
  REDRAW.forEach(f => { try { f(); } catch (e) {} });
}
function themeToggle() { themeApply(themeGet() === 'dark' ? 'light' : 'dark'); }
document.documentElement.setAttribute('data-theme', themeGet());

function prepCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(220, rect.width), h = Math.max(120, rect.height || 210);
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return {ctx, w, h};
}

function axes(ctx, box, max, labels, opts = {}) {
  const {x0, y0, x1, y1} = box;
  const css = getComputedStyle(document.documentElement);
  ctx.strokeStyle = css.getPropertyValue('--line').trim() || 'rgba(148,163,184,.16)';
  ctx.fillStyle = css.getPropertyValue('--txt-3').trim() || '#93a4bf';
  ctx.font = '10px Segoe UI, system-ui, sans-serif';
  ctx.lineWidth = 1;
  const steps = 4;
  for (let i = 0; i <= steps; i++) {
    const y = y1 - (i / steps) * (y1 - y0);
    ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    ctx.fillText(((max * i) / steps).toFixed(max <= 5 ? 1 : 0), x0 - 6, y);
  }
  const n = labels.length;
  const every = Math.max(1, Math.ceil(n / (opts.maxLabels || 8)));
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  labels.forEach((lab, i) => {
    if (i % every && i !== n - 1) return;
    const x = n === 1 ? (x0 + x1) / 2 : x0 + (i / (n - 1)) * (x1 - x0);
    const texto = String(lab);
    ctx.fillText(texto.length > 11 ? texto.slice(0, 10) + '…' : texto, x, y1 + 6);
  });
}

function emptyChart(ctx, w, h, msg = 'Sin datos todavia') {
  ctx.fillStyle = getComputedStyle(document.documentElement)
    .getPropertyValue('--txt-3').trim() || '#93a4bf';
  ctx.font = '13px Segoe UI, system-ui, sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(msg, w / 2, h / 2);
}

function lineChart(canvas, {labels = [], series = [], area = true, empty} = {}) {
  const {ctx, w, h} = prepCanvas(canvas);
  if (!labels.length || !series.length || !series.some(s => s.data.length)) {
    return emptyChart(ctx, w, h, empty);
  }
  const box = {x0: 38, y0: 12, x1: w - 10, y1: h - 22};
  const max = Math.max(1, ...series.flatMap(s => s.data.map(v => Number(v) || 0))) * 1.15;
  axes(ctx, box, max, labels);
  series.forEach((s, si) => {
    const color = s.color || PALETTE[si % PALETTE.length];
    const pts = s.data.map((v, i) => [
      labels.length === 1 ? (box.x0 + box.x1) / 2
        : box.x0 + (i / (labels.length - 1)) * (box.x1 - box.x0),
      box.y1 - ((Number(v) || 0) / max) * (box.y1 - box.y0),
    ]);
    if (area) {
      const grad = ctx.createLinearGradient(0, box.y0, 0, box.y1);
      grad.addColorStop(0, color + '55'); grad.addColorStop(1, color + '05');
      ctx.beginPath(); ctx.moveTo(pts[0][0], box.y1);
      pts.forEach(p => ctx.lineTo(p[0], p[1]));
      ctx.lineTo(pts[pts.length - 1][0], box.y1); ctx.closePath();
      ctx.fillStyle = grad; ctx.fill();
    }
    ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    pts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]));
    ctx.stroke();
    if (pts.length <= 40) {
      ctx.fillStyle = color;
      pts.forEach(p => { ctx.beginPath(); ctx.arc(p[0], p[1], 2.4, 0, 7); ctx.fill(); });
    }
  });
}

function barChart(canvas, {labels = [], series = [], empty, stacked = false} = {}) {
  const {ctx, w, h} = prepCanvas(canvas);
  if (!labels.length || !series.length) return emptyChart(ctx, w, h, empty);
  const box = {x0: 38, y0: 12, x1: w - 10, y1: h - 22};
  const totals = labels.map((_, i) => stacked
    ? series.reduce((a, s) => a + (Number(s.data[i]) || 0), 0)
    : Math.max(...series.map(s => Number(s.data[i]) || 0)));
  const max = Math.max(1, ...totals) * 1.15;
  axes(ctx, box, max, labels, {maxLabels: 12});
  const slot = (box.x1 - box.x0) / labels.length;
  const bw = stacked ? slot * 0.55 : (slot * 0.72) / series.length;
  labels.forEach((_, i) => {
    let acc = 0;
    series.forEach((s, si) => {
      const color = s.color || PALETTE[si % PALETTE.length];
      const v = Number(s.data[i]) || 0;
      const hgt = (v / max) * (box.y1 - box.y0);
      const x = stacked ? box.x0 + slot * i + (slot - bw) / 2
        : box.x0 + slot * i + slot * 0.14 + si * bw;
      const y = stacked ? box.y1 - acc - hgt : box.y1 - hgt;
      ctx.fillStyle = color;
      ctx.fillRect(x, y, Math.max(2, bw - 2), Math.max(0, hgt));
      acc += hgt;
    });
  });
}

function legend(target, series) {
  target.innerHTML = series.map((s, i) =>
    `<span><i style="background:${s.color || PALETTE[i % PALETTE.length]}"></i>${esc(s.name)}</span>`
  ).join('');
}

function severityTag(sev) {
  const map = {info: 'info', warning: 'warning', critical: 'critical'};
  return `<span class="tag ${map[sev] || 'muted'}">${esc(sev)}</span>`;
}

/* Redibuja las graficas registradas al cambiar el tamano de la ventana. */
const REDRAW = [];
function registerChart(fn) { REDRAW.push(fn); fn(); }
let _rt;
window.addEventListener('resize', () => {
  clearTimeout(_rt);
  _rt = setTimeout(() => REDRAW.forEach(f => { try { f(); } catch (e) {} }), 180);
});
