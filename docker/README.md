# docker/

Per-service configuration files for the GnuKontrolR stack.

## Subdirectories

| Directory | Purpose |
|---|---|
| `traefik/` | Traefik static config — entrypoints, ACME/Let's Encrypt, Docker provider |
| `site-template/` | Customer site container image (`webpanel/php-site:8.2`) |
| `mysql/` | MySQL initialisation SQL — creates the `webpanel` schema |
| `powerdns/` | PowerDNS config — SQLite backend, API, DNS settings |
| `postfix/` | Postfix outbound SMTP — configured via environment variables |
| `dovecot/` | Dovecot IMAP/POP3 — configured via environment variables |
| `prometheus/` | Prometheus scrape config — panel API, node-exporter, cAdvisor |
| `grafana/` | Grafana provisioning — datasource (Prometheus) + dashboards |

## Site template container (`site-template/`)

This is the base Docker image for every customer's hosting container.
One container per domain is created by the panel on demand.

**Pre-installed per container:**
- PHP-FPM 8.2 with common extensions (GD, PDO, ZIP, intl, opcache…)
- Nginx (default), Apache2, Lighttpd (switchable via supervisor)
- Node.js 20 + PM2 (optional, disabled by default)
- SQLite3, Composer, WP-CLI
- OpenSSH server (SFTP/SSH chroot to public_html only)
- Container internal API on port 9000 (Flask, TLS, token-authenticated)

**Key files:**
- `Dockerfile` — builds the base image
- `entrypoint.sh` — runs on container start: sets up SSH host keys, generates
  per-container TLS cert for the internal API, configures web server selector
- `container_api.py` — Flask API (port 9000) for panel-to-container communication:
  file management, config updates, service control, SFTP key management, backups
- `conf/supervisord.conf` — manages php-fpm, nginx/apache/lighttpd, sshd, container-api
- `conf/nginx.conf` / `conf/apache.conf` / `conf/lighttpd.conf` — web server configs
- `conf/php-fpm.conf` — PHP-FPM pool config
- `conf/sshd_config` — SSH hardened config (chroot, key-only auth)
- `conf/opcache.ini` — PHP OPcache settings
