// File: public/js/analytics.js
// Load umami script after consent and if configured by backend
async function loadConfig(){
  try {
    const r = await fetch('/api/config');
    if (!r.ok) return null;
    return r.json();
  } catch { return null; }
}
(async function(){
  const cfg = await loadConfig();
  if (!cfg || !cfg.analytics || !cfg.analytics.enabled) return;
  const KEY = 'consent_analytics_v1';
  const consent = localStorage.getItem(KEY);
  const ready = () => {
    const s = document.createElement('script');
    s.defer = true;
    s.src = cfg.analytics.scriptUrl;
    s.setAttribute('data-website-id', cfg.analytics.websiteId);
    document.head.appendChild(s);
  };
  if (consent === 'granted') return ready();
  if (consent === 'denied') return;
  document.addEventListener('consent-granted', ready, { once: true });
})();
