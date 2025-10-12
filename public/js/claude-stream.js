
import { settings } from './settings.js';
const META_BASE = (() => { const meta = document.querySelector('meta[name="hohl-chat-base"]'); const raw = (meta && meta.content ? meta.content : '').trim(); return raw ? (raw.endsWith('/') ? raw.slice(0, -1) : raw) : ''; })();
function abs(path){ const base = (settings.apiBase || META_BASE || ''); return path.startsWith('/') ? `${base}${path}` : path; }
export async function streamClaude({ prompt, system = '', model = '', onToken, onDone, onError, maxTokens=1024, temperature=0.7 }) {
  try {
    await new Promise((resolve, reject) => {
      const q = new URLSearchParams({ message: prompt || '', systemPrompt: system || '', model: model || '', maxTokens: String(maxTokens), temperature: String(temperature) });
      const es = new EventSource(abs('/chat-sse?' + q.toString()));
      es.onmessage = (ev) => { try{ const data = JSON.parse(ev.data); if (data.delta) { onToken && onToken(data.delta); } if (data.done) { es.close(); onDone && onDone(); resolve(); } if (data.error) { es.close(); reject(new Error(data.error)); } }catch{} };
      es.onerror = () => { es.close(); reject(new Error('SSE failed')); };
    });
    return;
  } catch (sseErr) { if (onToken) onToken(`(SSE-Fallback: ${sseErr.message})\n`); }
  try {
    const r = await fetch(abs('/api/claude'), { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ prompt, system, model, maxTokens, temperature }) });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();
    const text = (j && j.text) || '';
    const chunks = text.match(/.{1,80}/g) || [];
    for (const c of chunks) { onToken && onToken(c); await new Promise(r => setTimeout(r, 8)); }
    onDone && onDone();
  } catch (e) { onError && onError(e); }
}
