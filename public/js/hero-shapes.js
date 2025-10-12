
import { tickerItemsFor } from './ticker-items.js';
import { openCustomPopup } from './answer-popup.js';
import { lang } from './i18n.js';
import { sfx } from './sfx.js';
const layer = document.getElementById('shape-layer');
const SIZE_MIN = 150, SIZE_MAX = 300;
const NEON = ['#7ef9ff','#64ffda','#ffb3ff','#ffd166','#a7f432','#ff9bd3','#9bffd6','#b388ff','#e3ff7d'];
function pick(arr){ return arr[Math.floor(Math.random()*arr.length)]; }
function hexToRgba(hex, a){ const h = hex.replace('#',''); const bigint=parseInt(h,16); const r=(bigint>>16)&255, g=(bigint>>8)&255, b=bigint&255; return `rgba(${r},${g},${b},${a})`; }
function maxActive(){ const isMobile = Math.max(window.innerWidth, window.innerHeight) < 768; const perf = Number(localStorage.getItem('perf_bucket') || '60'); let base = isMobile ? 4 : 10; if (perf < 30) base = Math.max(3, Math.round(base * 0.6)); else if (perf < 45) base = Math.max(4, Math.round(base * 0.8)); return base; }
function makeBubble(item){
  const el = document.createElement('button'); el.className='shape';
  const size = Math.round(SIZE_MIN + Math.random()*(SIZE_MAX-SIZE_MIN));
  el.style.width = el.style.height = size + 'px'; el.style.setProperty('--r', String(size));
  const rect = layer.getBoundingClientRect(); const W=rect.width,H=rect.height;
  const x = Math.max(8, Math.floor(Math.random()*Math.max(8, W - size - 8)));
  const y = Math.max(8, Math.floor(Math.random()*Math.max(8, H - size - 8)));
  el.style.left = x + 'px'; el.style.top = y + 'px';
  const c = pick(NEON);
  el.style.background = `radial-gradient(circle at 30% 30%, rgba(255,255,255,.98), ${hexToRgba(c,0.9)})`;
  el.style.boxShadow = `0 0 28px ${hexToRgba(c,0.60)}, 0 0 88px ${hexToRgba(c,0.32)}, 0 10px 44px rgba(0,0,0,.46)`;
  el.setAttribute('aria-label', item.label);
  el.addEventListener('click', () => { sfx.click(); openCustomPopup(item); });
  const label = document.createElement('div'); label.className='label';
  const t = document.createElement('div'); t.className='title'; t.textContent=item.label;
  const s = document.createElement('div'); s.className='sub'; s.textContent=item.explain||'';
  label.append(t,s); el.append(label); return el;
}
let queue = tickerItemsFor(lang()); let idx = 0; let running=false;
function nextItem(){ if(!queue.length) queue = tickerItemsFor(lang()); const it = queue[idx % queue.length]; idx += 1; return it; }
const live = new Set();
function spawnOne(){ if (live.size >= maxActive()) return; const el = makeBubble(nextItem()); layer.append(el); requestAnimationFrame(()=>el.classList.add('live')); live.add(el); sfx.spawn(); setTimeout(()=>retire(el), 10000 + Math.floor(Math.random()*5000)); }
function retire(el){ if(!live.has(el)) return; el.classList.add('exit'); live.delete(el); setTimeout(()=>el.remove(),1200); }
function tick(){ spawnOne(); setTimeout(tick, 1400 + Math.floor(Math.random()*1000)); }
function start(){ if(running) return; running=true; spawnOne(); setTimeout(spawnOne, 800); tick(); }
function resetForLang(){ queue = tickerItemsFor(lang()); idx=0; }
start(); window.addEventListener('resize',()=>{}); document.addEventListener('lang-changed', resetForLang);
