// File: public/js/news-search.js
import { t } from './i18n.js';

function panel(title, contentNode){
  const root = document.getElementById('popup-root');
  const wrap = document.createElement('div'); wrap.className = 'popup';
  const inner = document.createElement('div'); inner.className = 'popup-inner';
  const head = document.createElement('div'); head.className = 'popup-header';
  const h3 = document.createElement('h3'); h3.textContent = title;
  const close = document.createElement('button'); close.className = 'btn btn-secondary'; close.textContent = '×'; close.addEventListener('click', () => wrap.remove());
  head.appendChild(h3); head.appendChild(close);
  const body = document.createElement('div'); body.className = 'popup-body';
  body.appendChild(contentNode);
  inner.appendChild(head); inner.appendChild(body);
  wrap.appendChild(inner); root.appendChild(wrap);
  return { wrap, body };
}

async function doSearch(q, out){
  out.textContent = '…';
  try {
    const r = await fetch('/api/search?q=' + encodeURIComponent(q));
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || 'Search error');
    const ul = document.createElement('ul');
    for (const it of (j.results || [])){
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = it.url; a.textContent = it.title || it.url; a.target = '_blank'; a.rel='noopener';
      li.appendChild(a);
      if (it.snippet) { const p = document.createElement('div'); p.textContent = ' – ' + it.snippet; li.appendChild(p); }
      ul.appendChild(li);
    }
    out.innerHTML = '';
    out.appendChild(ul);
    if (j.answer){
      const ans = document.createElement('p'); ans.textContent = j.answer; ans.style.fontStyle='italic';
      out.insertBefore(ans, ul);
    }
  } catch (e) {
    out.textContent = 'Fehler: ' + (e.message || e);
  }
}

document.addEventListener('click', (ev) => {
  const btn = ev.target.closest('.nav-btn[data-action="news"]');
  if (!btn) return;
  const node = document.createElement('div');
  node.innerHTML = `
    <div style="display:flex; gap:8px;">
      <input id="q" type="search" placeholder="AI news today" style="flex:1; padding:8px; border-radius:8px; border:1px solid rgba(255,255,255,.15); background:rgba(0,0,0,.2); color:inherit;">
      <button id="go" class="btn btn-primary">Search</button>
    </div>
    <div id="out" style="margin-top:12px;"></div>
  `;
  const { wrap } = panel(t('nav.news'), node);
  const q = node.querySelector('#q');
  const go = node.querySelector('#go');
  const out = node.querySelector('#out');
  go.addEventListener('click', () => doSearch(q.value || 'AI news today', out));
});
