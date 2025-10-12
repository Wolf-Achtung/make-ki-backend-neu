/* server/index.js — Express server with SSE, static hosting, healthz and content routes. */
import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import compression from 'compression';
import morgan from 'morgan';
import cors from 'cors';

import contentRoutes from './routes/content.js';
import searchRoutes from './routes/search.js';
import claudeRoutes from './routes/claude.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const app = express();

app.set('trust proxy', true);
app.disable('x-powered-by');
app.use(cors());
app.use(compression());
app.use((req, res, next) => {
  // Minimal security headers
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin');
  res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  res.setHeader('Content-Security-Policy',
    "default-src 'self'; img-src 'self' data: https:; media-src 'self' blob: https:; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://api.tavily.com https://api.perplexity.ai https://api.anthropic.com"
  );
  next();
});
app.use(morgan(process.env.NODE_ENV === 'production' ? 'combined' : 'dev'));
app.use(express.json({ limit:'1mb' }));

// Request ID
app.use((req, res, next)=>{
  req.id = (Math.random().toString(36).slice(2,10) + Date.now().toString(36)).toUpperCase();
  res.setHeader('X-Request-ID', req.id);
  next();
});

// Simple token-bucket rate limiter for /chat-sse (per IP)
const buckets = new Map();
function allow(ip){
  const now = Date.now();
  const refillMs = 5000;     // refill 1 token every 5s
  const cap = 10;            // bucket size
  const entry = buckets.get(ip) || { tokens: cap, ts: now };
  const delta = now - entry.ts;
  const refill = Math.floor(delta / refillMs);
  if (refill > 0){ entry.tokens = Math.min(cap, entry.tokens + refill); entry.ts = now; }
  if (entry.tokens <= 0) { buckets.set(ip, entry); return false; }
  entry.tokens -= 1; buckets.set(ip, entry); return true;
}
app.use('/chat-sse', (req, res, next)=>{
  const ip = req.headers['x-forwarded-for']?.split(',')[0]?.trim() || req.socket.remoteAddress || 'unknown';
  if (!allow(ip)) return res.status(429).json({ ok:false, error:'Rate limit exceeded' });
  next();
});

// Healthz
app.get('/healthz', (req, res)=> res.json({ ok:true, time: new Date().toISOString() }));

// Routes
app.use(contentRoutes);
app.use(searchRoutes);
app.use(claudeRoutes);

// Static
const pubDir = path.join(__dirname, '..', 'public');
app.use(express.static(pubDir, { extensions: ['html'] }));
app.get('*', (req, res, next) => {
  if (req.accepts('html')) return res.sendFile(path.join(pubDir, 'index.html'));
  next();
});

const port = process.env.PORT || 8080;
const server = app.listen(port, () => console.log('[info] server up on', port));

// Graceful shutdown
function shutdown(sig){
  console.log('[info] received', sig, '→ shutting down');
  try { server?.close(()=> process.exit(0)); } catch { process.exit(0); }
}
process.on('SIGTERM', ()=> shutdown('SIGTERM'));
process.on('SIGINT', ()=> shutdown('SIGINT'));
