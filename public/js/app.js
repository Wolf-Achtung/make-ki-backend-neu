import { renderAnswerPopup } from '/js/answer-popup.js';
import { openNews } from '/js/nav-popups.js';
import '/js/sfx.js'; // audio gesture hookup
import { openSettings } from '/js/settings-panel.js';
import { loadSettings } from '/js/settings-store.js';

// --- Bubble data (you can extend freely) ---
const items = [
  { t: 'Zeitlinien‑Explosion', d: 'Beschreibe eine Welt – ich verzweige 5 Varianten.', neon:'#ff7bd9', id:'zeit' },
  { t: 'Empathie‑Tutorial', d: 'Wähle eine Sequenz – ich erkläre schwierige Dinge.', neon:'#7be7ff', id:'emp' },
  { t: 'Detektiv rückwärts', d: 'Skizziere einen Fall — ich rekonstruiere alles rückwärts.', neon:'#ffd17b', id:'det' },
  { t: 'Biografie eines Pixels', d: 'Nenne Genre/Ära — ein Pixel erzählt.', neon:'#ffc6a8', id:'bio' },
  { t: 'NPC nach Feierabend', d: 'Gib Genre/Setting – ein Nebencharakter erzählt.', neon:'#a5ffc6', id:'npc' },
  { t: 'Heute neu', d: 'Tages‑Spotlight: KI‑Fund des Tages.', neon:'#b4ff8a', id:'daily' },
  { t: 'Farbsynästhetiker', d: 'Nenne zwei Songs – ich male dir die Farben.', neon:'#c7b6ff', id:'color' },
  { t: 'Interdimensionaler Markt', d: 'Sag, was du suchst – ich öffne einen Markt.', neon:'#8affde', id:'market' }
];

// --- Utilities ---
const el = sel => document.querySelector(sel);
function rand(min,max){ return Math.random()*(max-min)+min; }

// --- Bubble engine ---
const layer = el('#bubble-layer');
const MAX_VISIBLE = 7;
const LIFETIME_MS = 12000;

function spawnBubble(item){
  const b = document.createElement('button');
  b.className = 'bubble bubble--in bubble--pulse';
  b.style.left = `${rand(15,85)}%`;
  b.style.top  = `${rand(22,78)}%`;
  const neonIntensity = (loadSettings()?.neon) || 1.0; b.style.setProperty('--neon', item.neon); b.style.filter = `saturate(${neonIntensity})`;
  b.setAttribute('aria-label', item.t);
  b.innerHTML = `<div class="bubble__inner"><div class="bubble__title">${item.t}</div><div class="bubble__desc">${item.d}</div></div>`;
  layer.appendChild(b);

  const timer = setTimeout(()=>{
    b.classList.remove('bubble--in'); b.classList.add('bubble--out');
    setTimeout(()=> b.remove(), 800);
  }, LIFETIME_MS);

  b.addEventListener('click', ()=>{
    clearTimeout(timer);
    openItem(item);
  });
}

function maintainLoop(){
  // keep up to MAX_VISIBLE bubbles alive, add one every 2.2s
  spawnBubble(items[Math.floor(Math.random()*items.length)]);
  setTimeout(maintainLoop, 2200);
}
maintainLoop();

function openItem(item){
  const map = {
    det: { title:item.t, placeholder:'Ort, Zeit, Personen, 3–5 Hinweise …', prompt:'Rekonstruiere folgenden Fall rückwärts (Timeline, präzise, deutsch): ' },
    emp: { title:item.t, placeholder:'Sequenz nennen …', prompt:'Erkläre folgende Sequenz in klaren Etappen: ' },
    color: { title:item.t, placeholder:'2 Songs …', prompt:'Erzeuge eine synästhetische Farbanalyse zu: ' },
    npc: { title:item.t, placeholder:'Genre/Setting …', prompt:'Erzähle als Nebenfigur in ' },
    bio: { title:item.t, placeholder:'Genre/Ära …', prompt:'Biografie eines Pixels – Kontext: ' },
    market: { title:item.t, placeholder:'Was suchst du …', prompt:'Interdimensionaler Markt – Angebot skizzieren für: ' },
    zeit: { title:item.t, placeholder:'Beschreibe eine Welt …', prompt:'Erzeuge 5 divergierende Zeitlinien für: ' },
    daily: { title:item.t, placeholder:'Thema/Link …', prompt:'Fasst den heutigen Fund pointiert zusammen: ' }
  };
  const cfg = map[item.id] || { title:item.t, placeholder:'Frage …', prompt:'' };
  renderAnswerPopup({
    title: cfg.title,
    placeholder: cfg.placeholder,
    onAsk: (q, sink)=> streamSSE(cfg.prompt + q, sink)
  });
}

// --- SSE fallback (server has /chat-sse) ---
async function streamSSE(message, { onChunk, onDone, onError }){
  try{
    const url = `/chat-sse?` + new URLSearchParams({ message });
    const r = await fetch(url, { headers:{ 'Accept':'text/event-stream' } });
    if (!r.ok) throw new Error('HTTP '+r.status);
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    while (true){
      const {value, done} = await reader.read();
      if (done) break;
      const text = decoder.decode(value, {stream:true});
      // parse SSE frames (very small protocol here)
      text.split("\n\n").forEach(frame=>{
        if (!frame.trim()) return;
        const data = frame.replace(/^data:\s*/,'').trim();
        try{
          const evt = JSON.parse(data);
          if (evt.delta) onChunk(evt.delta);
          if (evt.done) onDone?.();
        }catch{ /* ignore */ }
      });
    }
  }catch(e){ onError?.(e); }
}

// --- Nav binding ---
document.addEventListener('click', (ev)=>{
  const btn = ev.target.closest('.pill');
  if (!btn) return;
  const id = btn.dataset.nav;
  if (id === 'news') openNews();
  if (id === 'prompts') openPrompts();
  if (id === 'projects') openProjects();
  if (id === 'about') openAbout();
});

// Minimal About/Prompts/Projects
function openAbout(){
  const root = document.getElementById('popup-root');
  root.innerHTML = `<div class="popup">
    <div class="popup__head"><h3>Über</h3><button class="btn btn--ghost" data-close>Schließen</button></div>
    <div class="popup__body">
      <p>hohl.rocks – experimentelle KI‑Werkstatt. Klicke auf Bubbles, frag was, und erhalte eine gestreamte Antwort.</p>
    </div>
  </div>`;
  root.querySelector('[data-close]').addEventListener('click', ()=> root.innerHTML='');
}

function openPrompts(){
  const root = document.getElementById('popup-root');
  root.innerHTML = `<div class="popup">
    <div class="popup__head"><h3>Prompts</h3><button class="btn btn--ghost" data-close>Schließen</button></div>
    <div class="popup__body">
      <article class="card"><h4>Meeting → Aktionsliste</h4><p>Situation: Nach dem Call. Nutzen: klare To‑Dos.</p><button class="btn btn--ghost" data-copy="Wandle folgende Meeting-Notizen in To-Dos um:">Kopieren</button></article>
      <article class="card"><h4>LinkedIn‑Post (120 W.)</h4><p>Situation: Thought Leadership kompakt.</p><button class="btn btn--ghost" data-copy="Schreibe einen prägnanten LinkedIn-Post (120 Wörter) über:">Kopieren</button></article>
    </div>
  </div>`;
  const rootEl = root.querySelector('.popup'); 
  root.querySelector('[data-close]').addEventListener('click', ()=> root.innerHTML='');
  rootEl.addEventListener('click', (e)=>{
    const t = e.target.closest('[data-copy]'); if (!t) return;
    navigator.clipboard.writeText(t.getAttribute('data-copy')); t.textContent='Kopiert';
    setTimeout(()=> t.textContent='Kopieren', 1200);
  });
}

function openProjects(){
  const root = document.getElementById('popup-root');
  root.innerHTML = `<div class="popup">
    <div class="popup__head"><h3>Projekte</h3><button class="btn btn--ghost" data-close>Schließen</button></div>
    <div class="popup__body">
      <article class="card"><a href="https://ki-sicherheit.jetzt/" target="_blank" rel="noopener"><h4>KI‑Sicherheit.jetzt</h4><p>TÜV‑zertifizierter KI‑Manager: EU AI Act sauber umsetzen.</p></a></article>
      <article class="card"><a href="https://achtung.live/" target="_blank" rel="noopener"><h4>achtung.live</h4><p>Smarter Begleiter: erkennt sensible Daten live und hilft, sie zu schützen.</p></a></article>
    </div>
  </div>`;
  root.querySelector('[data-close]').addEventListener('click', ()=> root.innerHTML='');
}


// ensure settings pill exists
const nav = document.querySelector('.nav');
if (nav && !nav.querySelector('[data-nav="settings"]')){
  const btn = document.createElement('button');
  btn.className = 'pill'; btn.setAttribute('data-nav','settings'); btn.textContent = '⚙︎';
  nav.appendChild(btn);
}

// news badge
import { loadSettings as __ls, saveSettings as __ss } from '/js/settings-store.js';
const newsBtn = document.querySelector('[data-nav="news"]');
if (newsBtn){
  const last = __ls().newsLastOpened || 0;
  const sixH = 6*60*60*1000;
  if (Date.now() - last > sixH) newsBtn.classList.add('badge-dot');
  document.addEventListener('news-opened', ()=>{
    newsBtn.classList.remove('badge-dot');
    __ss({ newsLastOpened: Date.now() });
  });
}
