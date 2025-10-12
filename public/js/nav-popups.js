// News popup
import { markNewsOpened } from '/js/settings-store.js';

export async function openNews(){
  const root = document.getElementById('popup-root');
  root.innerHTML = '';
  const el = document.createElement('div');
  el.className = 'popup';
  el.innerHTML = `<div class="popup__head"><h3>News</h3><button class="btn btn--ghost" data-close>Schließen</button></div>
                  <div class="popup__body"><div id="news">Lade…</div></div>`;
  root.appendChild(el);
  document.dispatchEvent(new Event('news-opened')); markNewsOpened();
  el.addEventListener('click', e=>{ if (e.target.matches('[data-close]')||e.target===el) root.innerHTML=''; });

  
  // topic chips
  const chips = document.createElement('div'); chips.className='chips';
  const defs = [
    {key:'ai', label:'Allgemein'}, {key:'policy', label:'Policy'},
    {key:'research', label:'Research'}, {key:'product', label:'Product'},
    {key:'security', label:'Security'}
  ];
  let active = 'ai';
  defs.forEach(d=>{
    const b = document.createElement('button'); b.className='chip'; b.textContent=d.label; b.setAttribute('data-topic', d.key);
    if (d.key===active) b.setAttribute('aria-pressed','true');
    b.addEventListener('click', ()=>{
      active = d.key;
      chips.querySelectorAll('.chip').forEach(x=>x.removeAttribute('aria-pressed'));
      b.setAttribute('aria-pressed','true');
      loadAll(d.key);
    });
    chips.appendChild(b);
  });
  el.querySelector('.popup__body').prepend(chips);

  const endpoints = [
    ['/api/news/live','Tavily'],
    ['/api/ai-weekly?time_range=day','Perplexity Daily'],
    ['/api/ai-weekly?topic=security&time_range=week','Perplexity Security Weekly']
  ];
  const newsEl = el.querySelector('#news');

  const get = async (url) => {
    const r = await fetch(url);
    const data = await r.json().catch(()=>({}));
    if (!r.ok || data.ok === false) {
      const reason = data?.error || r.statusText || `HTTP ${r.status}`;
      throw new Error(reason);
    }
    return data;
  };

  try{
    const results = await Promise.allSettled(endpoints.map(([url])=>get(url)));
    const items = results.flatMap(r=> r.status==='fulfilled' && Array.isArray(r.value.items) ? r.value.items : []);
    if (items.length===0){
      const why = results.map((r,i)=> r.status==='rejected' ? `Quelle ${i+1}: ${r.reason.message||r.reason}` : null).filter(Boolean).join(' • ');
      newsEl.innerHTML = `<p>Keine News verfügbar.</p><small>${why||''}</small>`;
    }else{
      newsEl.innerHTML = items.slice(0,18).map(it => `<article class="card">
        <a href="${it.url}" target="_blank" rel="noopener">
          <h4>${it.title}</h4>
          <p>${it.snippet||''}</p>
          <div class="meta">${[it.tag,it.severity,it.published_time].filter(Boolean).join(' • ')}</div>
        </a>
      </article>`).join('');
    }
  }catch(e){
    newsEl.textContent = 'Fehler beim Laden: ' + (e?.message||e);
      }
  }
}

  await loadAll('ai');
}
