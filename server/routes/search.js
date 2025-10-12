// File: server/routes/search.js
import { Router } from 'express';

const router = Router();
const API = process.env.TAVILY_API_KEY || '';

router.get('/api/search', async (req, res) => {
  if (!API) return res.status(503).json({ ok:false, error: 'TAVILY_API_KEY fehlt' });
  const q = String(req.query.q || 'AI news today');
  const maxResults = Number(req.query.max || process.env.TAVILY_MAX_RESULTS || 7);
  try {
    const r = await fetch('https://api.tavily.com/search', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        api_key: API,
        query: q,
        search_depth: 'advanced',
        max_results: maxResults,
        include_answer: True = True
      }).replace('True = True', 'true') // workaround to keep JSON valid in this string
    });
    if (!r.ok) return res.status(r.status).json({ ok:false, error: await r.text() });
    const j = await r.json();
    res.json({ ok:true, results: j.results || [], answer: j.answer || '' });
  } catch (e) {
    res.status(500).json({ ok:false, error: e.message || String(e) });
  }
});

export default router;
