import { Router } from 'express';

class HttpError extends Error { constructor(status, message){ super(message); this.status = status; } }

const API_KEY = process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_API_KEY || '';
const DEFAULT_MODEL = process.env.CLAUDE_MODEL || 'claude-3-5-sonnet-20240620';

function ensureKey(){
  if (!API_KEY) { throw new HttpError(503, 'ANTHROPIC_API_KEY fehlt'); }
}

async function anthropicJSON({ prompt, system = '', model = DEFAULT_MODEL, maxTokens = 1024, temperature = 0.7 }) {
  ensureKey();
  const body = { model, max_tokens: maxTokens, temperature, system: system || undefined, messages: [{ role: 'user', content: prompt || '' }] };
  const r = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-api-key': API_KEY, 'anthropic-version': '2023-06-01' },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new HttpError(r.status, `Claude HTTP ${r.status}: ${await r.text()}`);
  const j = await r.json();
  const text = Array.isArray(j.content) ? j.content.filter(x => x && x.type === 'text').map(x => x.text).join('') : (j.content?.text || '');
  return { text, raw: j };
}

const router = Router();

router.post('/api/claude', async (req, res) => {
  try {
    const {
      prompt = '',
      system = '',
      model: mInput,
      maxTokens: tInput = 1024,
      temperature: tempInput = 0.7
    } = req.body || {};

    const model = (typeof mInput === 'string' && mInput.trim()) ? mInput.trim() : DEFAULT_MODEL;
    const maxTokens = Math.max(1, Math.min(Number(tInput) || 1024, 8000));
    const temperature = Math.max(0, Math.min(Number(tempInput) || 0.7, 2));

    const { text, raw } = await anthropicJSON({ prompt, system, model, maxTokens, temperature });
    res.json({ ok: true, model, text, usage: raw?.usage || null });
  } catch (e) {
    const status = e.status && Number.isInteger(e.status) ? e.status : 500;
    res.status(status).json({ ok: false, error: e.message || String(e), status });
  }
});

router.get('/chat-sse', async (req, res) => {
  try{
    ensureKey();
    const message = String(req.query.message || '');
    const system = String(req.query.systemPrompt || '');
    const model = String(req.query.model || DEFAULT_MODEL) || DEFAULT_MODEL;
    const max_tokens = Math.max(1, Math.min(Number(req.query.maxTokens || 1024), 8000));
    const temperature = Math.max(0, Math.min(Number(req.query.temperature || 0.7), 2));

    res.writeHead(200, {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive'
    });
    const send = (obj) => res.write(`data: ${JSON.stringify(obj)}\n\n`);

    const body = { model, max_tokens, temperature, system: system || undefined, stream: true, messages: [{ role: 'user', content: message }] };
    const r = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-api-key': API_KEY, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify(body)
    });
    if (!r.ok || !r.body) { send({ error: `Claude HTTP ${r.status}` }); return res.end(); }

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf='';
    while (true) {
      const { value, done } = await reader.read(); if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const rawEvent = buf.slice(0, idx).trim(); buf = buf.slice(idx + 2);
        const lines = rawEvent.split('\n'); let ev='message'; let data='';
        for (const line of lines) { if (line.startsWith('event:')) ev = line.slice(6).trim(); else if (line.startsWith('data:')) data += line.slice(5).trim(); }
        if (!data) continue;
        try {
          const j = JSON.parse(data);
          if (ev === 'content_block_delta' && j.delta?.type === 'text_delta') send({ delta: j.delta.text });
          else if (ev === 'message_stop') send({ done: true });
        } catch { /* ignore partials */ }
      }
    }
    res.end();
  } catch (e) {
    res.write(`data: ${JSON.stringify({ error: e.message || String(e) })}\n\n`); res.end();
  }
});

export default router;
