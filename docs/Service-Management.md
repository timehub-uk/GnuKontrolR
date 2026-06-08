# Service Management

## Service Status

### Via Web UI

The Dashboard shows all services with their current health status:
- **Green** — running and healthy
- **Yellow** — running but health check not configured
- **Red** — stopped or unhealthy

### Via CLI

```bash
panel service status
```

Example output:

```
Service     Status   Health
──────────────────────────────
traefik     running  —
mysql       running  healthy
postgres    running  healthy
redis       running  —
postfix     running  healthy
dovecot     running  —
powerdns    running  —
panel       running  healthy
```

## Restarting a Service

### Via CLI

```bash
panel service restart webpanel_api
panel service restart mysql
```

### Via Host

```bash
cd /opt/gnukontrolr
docker compose restart mysql
docker compose up -d webpanel   # rebuild and restart
```

## Container Management

### Via CLI

```bash
panel container list          # List all containers
panel container stats         # Live resource usage
panel container logs mysql    # View logs (--lines 100)
```

### Via Host

```bash
docker compose ps             # List all services
docker compose logs -f mysql  # Follow logs
docker compose top            # Show running processes
docker compose down           # Stop all services
docker compose up -d          # Start all services
```

## Common Operations

### Full Restart

```bash
cd /opt/gnukontrolr
docker compose restart
```

### Rebuild a Service

```bash
docker compose build webpanel
docker compose up -d webpanel
```

### Update Everything

```bash
# Inside WebPanel Terminal:
panel update

# Or from host:
sudo bash setup.sh cmd_update
```

This runs: `git pull` → `npm install` → `npm run build` → `docker compose build` → `docker compose up -d`

### View All Logs

```bash
panel log sources            # List available logs
panel log view panel         # View panel logs
panel log view mysql --lines 200
```
