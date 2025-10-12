// File: public/js/consent.js
// Very small, no-cookie banner. Stores in localStorage.
(function init(){
  const KEY = 'consent_analytics_v1';
  if (localStorage.getItem(KEY)) return; // already decided
  const bar = document.createElement('div');
  bar.style.position = 'fixed';
  bar.style.inset = 'auto 0 0 0';
  bar.style.background = 'rgba(16,18,24,.92)';
  bar.style.color = '#dde3ea';
  bar.style.padding = '12px';
  bar.style.display = 'flex';
  bar.style.gap = '8px';
  bar.style.alignItems = 'center';
  bar.style.justifyContent = 'space-between';
  bar.style.zIndex = '1000';
  bar.innerHTML = '<div style="max-width:70ch">Wir verwenden eine schlanke, datensparsame Analytics (umami). Nur mit deiner Zustimmung.</div>' +
    '<div style="display:flex; gap:8px;"><button id="c-accept" class="btn btn-primary">Einverstanden</button><button id="c-deny" class="btn btn-secondary">Ablehnen</button></div>';
  document.body.appendChild(bar);
  bar.querySelector('#c-accept').addEventListener('click', () => { localStorage.setItem(KEY, 'granted'); bar.remove(); document.dispatchEvent(new CustomEvent('consent-granted')); });
  bar.querySelector('#c-deny').addEventListener('click', () => { localStorage.setItem(KEY, 'denied'); bar.remove(); });
})();
