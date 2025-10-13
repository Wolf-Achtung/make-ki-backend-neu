# filename: ops/railway-config.md
## Railway – empfohlene Variablen
```
# CORS
CORS_ALLOW_ORIGINS=https://ki-sicherheit.jetzt,https://www.ki-sicherheit.jetzt,https://make.ki-sicherheit.jetzt,https://www.make.ki-sicherheit.jetzt,https://ki-foerderung.jetzt
CORS_ALLOW_REGEX=^https?://([a-z0-9-]+\.)?(ki-sicherheit\.jetzt|ki-foerderung\.jetzt)$
CORS_ALLOW_CREDENTIALS=0

# PDF
PDF_SERVICE_URL=https://<pdf-service-host>
PDF_TIMEOUT=45000
PDF_MAX_BYTES=33554432
PDF_MINIFY_HTML=1
PDF_STRIP_SCRIPTS=1

# Live-Layer
SEARCH_PROVIDER=hybrid
LLM_PROVIDER=anthropic
PPLX_USE_CHAT=0
TOOL_MATRIX_LIVE_ENRICH=1

# SMTP (Beispiel)
SMTP_HOST=smtp.postmarkapp.com
SMTP_PORT=587
SMTP_USER=xyz
SMTP_PASS=xyz
SMTP_FROM=reports@ki-sicherheit.jetzt
SMTP_FROM_NAME=KI‑Sicherheit
ADMIN_EMAIL=wolf@ki-sicherheit.jetzt

# DB (Railway setzt meist DATABASE_URL automatisch)
DATABASE_URL=postgresql://user:pass@host:port/dbname
ADMIN_SEED_USERS=[{"email":"wolf.hohl@web.de","password":"<setze_ein_pw>"}]
```

## Prometheus Scrape
```
scrape_configs:
  - job_name: 'ki-status-report'
    metrics_path: /metrics
    scheme: https
    static_configs:
      - targets: ['<railway-service>.up.railway.app']
```

## Alerts (prometheus/alerts.yml)
- Hohe 5xx‑Rate
- Latenz p95 über Schwelle
```
groups:
- name: ki-status-report-alerts
  rules:
  - alert: HighErrorRate
    expr: sum(rate(app_requests_total{status=~"5.."}[5m])) / sum(rate(app_requests_total[5m])) > 0.05
    for: 5m
    labels: {severity: warning}
    annotations:
      summary: "5xx > 5% (5m)"
  - alert: HighLatencyP95
    expr: histogram_quantile(0.95, sum(rate(app_request_latency_seconds_bucket[5m])) by (le)) > 2
    for: 10m
    labels: {severity: warning}
    annotations:
      summary: "p95 latency > 2s (10m)"
```
