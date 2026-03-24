# docker/prometheus/

Prometheus metrics scraper configuration.

## prometheus.yml

Scrape targets:
- `webpanel:8000/api/metrics` — panel API (CPU, memory, disk gauges + HTTP request counter)
- `node-exporter:9100` — host-level metrics (CPU, memory, disk, network, filesystem)
- `cadvisor:8080` — per-container metrics (CPU, memory, network per Docker container)

## Retention

Data is retained for 30 days (set in `docker-compose.yml` via `--storage.tsdb.retention.time=30d`).

## Adding a new scrape target

Edit `prometheus.yml` and add a new job under `scrape_configs`, then:

```bash
docker compose restart prometheus
```

Or use the lifecycle API (enabled with `--web.enable-lifecycle`):

```bash
curl -X POST http://localhost:9090/-/reload
```
