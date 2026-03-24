# docker/grafana/

Grafana dashboard and datasource provisioning.

## provisioning/

Grafana auto-provisions datasources and dashboards from these directories on startup.

### datasources/prometheus.yml

Configures Prometheus as the default datasource (`http://prometheus:9090`).

### dashboards/dashboards.yml

Tells Grafana to scan for dashboard JSON files in `/etc/grafana/provisioning/dashboards/`.
Add `.json` dashboard files here to have them automatically loaded.

## Access

Grafana is accessible at `https://<panel-domain>/grafana` via Traefik.
Credentials are set via `GRAFANA_USER` and `GRAFANA_PASSWORD` in `.env`.

## Adding dashboards

1. Export a dashboard as JSON from any Grafana instance
2. Drop the `.json` file into `docker/grafana/provisioning/dashboards/`
3. Restart Grafana: `docker compose restart grafana`

Recommended dashboards to import:
- **Node Exporter Full** (ID: 1860) — host metrics
- **Docker Container & Host Metrics** (ID: 179) — container stats
