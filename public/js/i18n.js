
const STORE_KEY = 'hohl_lang';
let _lang = (localStorage.getItem(STORE_KEY) || (navigator.language || 'de').slice(0,2)).toLowerCase();
if (_lang !== 'de' && _lang !== 'en') _lang = 'de';
export function lang(){ return _lang; }
export function setLang(l){ _lang = (l === 'de' || l === 'en') ? l : 'en'; localStorage.setItem(STORE_KEY, _lang); document.dispatchEvent(new CustomEvent('lang-changed', { detail: { lang: _lang } })); }

const STR = {
  de: {
    ask: 'Fragen',
    close: 'Schließen',
    copy: 'Kopieren',
    copied: 'Kopiert',
    your_input: 'Dein Input…',
    about_html: '<p><strong>hohl.rocks — Neon Gold UX++</strong><br>Ein spielerisches Interface für Prompts, Ideen und KI‑Experimente.</p><p>Wähle eine Bubble, lies die Micro‑Anleitung und probiere aus. Antworten streamen live (/chat-sse).</p><p><em>Tipp:</em> Über ⚙︎ kannst du Modell, System‑Prompt und Temperatur einstellen.</p>',
    news: 'News',
    prompts: 'Prompts',
    projects_html: '<div class="list">\
<article class="card"><h4>KI‑Sicherheit.jetzt</h4><p><strong>Claim:</strong> Als TÜV‑zertifizierter KI‑Manager begleite ich Ihr Unternehmen dabei, sämtliche Anforderungen des EU AI Acts transparent, nachvollziehbar und rechtssicher umzusetzen.</p><div class="actions"><a class="btn btn-primary" href="https://ki-sicherheit.jetzt/" target="_blank" rel="noopener">Öffnen</a></div></article>\
<article class="card"><h4>achtung.live</h4><p><strong>Idee:</strong> Dein stiller, smarter Begleiter, der live erkennt, wenn du sensible Daten preisgibst — warnt, verschleiert oder souverän ersetzt. Für alle, die keine Ahnung von Datenschutz haben – aber online geschützt sein wollen.</p><div class="actions"><a class="btn btn-primary" href="https://achtung.live/" target="_blank" rel="noopener">Öffnen</a></div></article>\
</div>',
    consent_text: 'Dürfen wir anonyme Nutzungsdaten (Umami) erheben, um die Experience zu verbessern?',
    accept: 'Akzeptieren',
    decline: 'Ablehnen',
    settings: 'Einstellungen',
    save: 'Speichern',
    system_prompt: 'System-Prompt',
    model: 'Modell',
    temperature: 'Temperatur',
    maxtokens: 'Max Tokens',
    api_base: 'API-Basis (leer = gleiche Origin)',
    language: 'Sprache'
  },
  en: {
    ask: 'Ask',
    close: 'Close',
    copy: 'Copy',
    copied: 'Copied',
    your_input: 'Your input…',
    about_html: '<p><strong>hohl.rocks — Neon Gold UX++</strong><br>A playful interface for prompts, ideas and AI experiments.</p><p>Pick a bubble, read the micro‑guide and try it. Answers stream live (/chat-sse).</p><p><em>Tip:</em> Use ⚙︎ to tune model, system prompt and temperature.</p>',
    news: 'News',
    prompts: 'Prompts',
    projects_html: '<div class="list">\
<article class="card"><h4>KI‑Sicherheit.jetzt</h4><p><strong>Claim:</strong> TÜV‑certified AI manager — we help your org comply with the EU AI Act in a transparent, auditable, lawful way.</p><div class="actions"><a class="btn btn-primary" href="https://ki-sicherheit.jetzt/" target="_blank" rel="noopener">Open</a></div></article>\
<article class="card"><h4>achtung.live</h4><p><strong>Idea:</strong> A quiet, smart companion that detects sensitive data in real time — warns you, obfuscates or replaces it on request.</p><div class="actions"><a class="btn btn-primary" href="https://achtung.live/" target="_blank" rel="noopener">Open</a></div></article>\
</div>',
    consent_text: 'May we collect anonymous usage data (Umami) to improve the experience?',
    accept: 'Accept',
    decline: 'Decline',
    settings: 'Settings',
    save: 'Save',
    system_prompt: 'System prompt',
    model: 'Model',
    temperature: 'Temperature',
    maxtokens: 'Max tokens',
    api_base: 'API base (empty = same origin)',
    language: 'Language'
  }
};
export function t(key){ return (STR[_lang] && STR[_lang][key]) || key; }
