# filename: ops/railway-metrics.md
# Railway: /metrics Scrape Quick Guide

1. **Endpoint bereitstellen**  
   Das Backend exponiert jetzt `/metrics` (Prometheus Textformat) und `/healthz` (JSON).  
   Beide sind **ohne Auth** verfügbar – ideal für Railway/Grafana Dashboards.

2. **Railway Projekt – Service Check (optional, aber empfohlen)**  
   - Healthcheck: `GET /healthz` (200 = OK)  
   - Timeout: 10s, Interval: 30s

3. **Scraping mit externer Prometheus/Grafana**  
   Verwende `ops/prometheus.yml` als Vorlage und setze:
   ```yaml
   targets: ['<dein-host>.up.railway.app']
   metrics_path: /metrics
   scheme: https
   ```

4. **Alarme**  
   Beobachte die Metriken:
   - `alert_5xx_rate_over_threshold` (== 1 → Alarm)
   - `alert_429_rate_over_threshold` (== 1 → Alarm)

5. **Schnelltest**
   ```bash
   curl -s https://<dein-host>.up.railway.app/metrics | head
   curl -s https://<dein-host>.up.railway.app/healthz | jq
   ```
