// stream rendering popup
export function renderAnswerPopup(ctx){
  const { title, placeholder, onAsk } = ctx;
  const root = document.getElementById('popup-root');
  root.innerHTML = '';
  const el = document.createElement('div');
  el.className = 'popup';
  el.innerHTML = `
    <div class="popup__head">
      <h3>${title}</h3>
      <button class="btn btn--ghost" data-close>Schließen</button>
    </div>
    <div class="popup__body">
      <label class="field">
        <input class="input" placeholder="${placeholder||''}" />
      </label>
      <div class="prose" id="out" data-raw=""></div>
    </div>
    <div class="popup__foot">
      <div class="row gap-s">
        <button class="btn" data-ask>Fragen</button>
        <button class="btn btn--ghost" data-copy>Kopieren</button>
        <button class="btn btn--ghost" data-speak>Vorlesen</button>
      </div>
    </div>`;
  root.appendChild(el);
  const input = el.querySelector('input');
  const out = el.querySelector('#out');

  function speak(text){
    try{ const s = new SpeechSynthesisUtterance(text); speechSynthesis.cancel(); speechSynthesis.speak(s); }catch{}
  }

  el.addEventListener('click', (ev)=>{
    if (ev.target.matches('[data-close]') || ev.target === el) root.innerHTML = '';
    if (ev.target.matches('[data-copy]')) { navigator.clipboard.writeText(out.textContent||''); }
    if (ev.target.matches('[data-speak]')) { speak(out.textContent||''); }
    if (ev.target.matches('[data-ask]')) {
      out.innerHTML = ''; out.setAttribute('data-raw','');
      (async ()=> onAsk?.(input.value, {
        onChunk: (t)=>{ out.setAttribute('data-raw', (out.getAttribute('data-raw')||'') + t); out.textContent = out.getAttribute('data-raw'); },
        onDone: ()=>{},
        onError: (e)=>{ out.textContent = 'Fehler: ' + (e?.message||e); }
      }))();
    }
  });
  document.addEventListener('keydown', (e)=>{ if (e.key==='Escape') root.innerHTML=''; }, { once:true });
}
