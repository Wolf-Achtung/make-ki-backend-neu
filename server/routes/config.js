// File: server/routes/config.js
import { Router } from 'express';

const router = Router();

router.get('/api/config', (req, res) => {
  const cfg = {
    analytics: {
      enabled: Boolean(process.env.UMAMI_WEBSITE_ID),
      provider: 'umami',
      scriptUrl: process.env.UMAMI_SCRIPT_URL || 'https://analytics.umami.is/script.js',
      websiteId: process.env.UMAMI_WEBSITE_ID || ''
    },
    search: {
      tavilyEnabled: Boolean(process.env.TAVILY_API_KEY),
      maxResults: Number(process.env.TAVILY_MAX_RESULTS || 7)
    },
    chat: {
      sse: true,
      defaultModel: process.env.CLAUDE_MODEL || 'claude-3-5-sonnet-20240620'
    }
  };
  res.json(cfg);
});

export default router;
