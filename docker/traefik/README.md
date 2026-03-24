# docker/traefik/

Traefik v3 reverse proxy configuration.

## traefik.yml

Static configuration file. Key sections:

- **entryPoints**: `web` (80, redirects to HTTPS) and `websecure` (443)
- **certificatesResolvers.le**: Let's Encrypt ACME with HTTP challenge
- **providers.docker**: Auto-discovers services via Docker labels on `webpanel_net`
- **providers.file**: Watches `/etc/traefik/dynamic/` for dynamic config (not currently used)

## Dynamic configuration

Place `.yml` files in `docker/traefik/dynamic/` (mounted at `/etc/traefik/dynamic/`)
to add middleware, TLS options, or additional routers without restarting Traefik.

## How customer domains get SSL

When the panel creates a customer container (`docker_mgr.py`), it adds Traefik labels:

```
traefik.enable=true
traefik.http.routers.<name>.rule=Host(`example.com`)
traefik.http.routers.<name>.tls=true
traefik.http.routers.<name>.tls.certresolver=le
```

Traefik picks these up via the Docker provider and automatically requests + renews
a Let's Encrypt certificate for that domain. No manual config needed.

## Dashboard

Available at `http://traefik.panel.local:8080/dashboard/` on the internal network.
Do **not** expose port 8080 publicly — restrict it in production with IP whitelist middleware.
