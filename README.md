# hohl.rocks — Final (Streaming, Neon Bubbles, i18n)

- Frontend unter `public/` (inkl. **public/videos/road.mp4**).
- Backend (Express) unter `server/` mit **SSE** (`/chat-sse`) + Fallback `/api/claude`.
- Längere Micro‑Guides in allen Bubbles.
- CORS/CSP für hohl.rocks + Railway.

**Start lokal**
```
npm install
cp .env.example .env   # Keys setzen
npm start              # http://localhost:8080
```
