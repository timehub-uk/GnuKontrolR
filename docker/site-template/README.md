# docker/site-template/

Base Docker image for per-domain customer site containers.

## How it works

The panel creates one container per domain using `docker run` (see `backend/app/routers/docker_mgr.py`).
Each container is isolated — no shared filesystem, no shared process namespace.

## Directory layout inside each container

```
/var/www/html/          Public web root (customer-owned, web-accessible)
/var/customer/
  uploads/              Customer file uploads (private)
  private/              Private data (private)
  backups/              Customer backups (private)
/var/config/            SECURE area — managed by container API only
  nginx/                Nginx config fragments
  php/                  PHP ini overrides
  env/                  Env / secrets (chmod 700)
  ssl/                  SSL certificates
/var/db/                SSH keys + SQLite + API TLS cert (root-owned)
/home/www-data/.ssh/    SFTP authorized keys
```

## Security model

- `www-data` — customer SSH/SFTP/PHP process. Can write to `/var/www/html` and `/var/customer`. Cannot read `/var/config`.
- `gnukontrolr-admin` — system account that runs the container API. Owns `/var/config`. Cannot log in via SSH.
- SSH is chroot'd — `/var/config` is never inside the chroot jail.
- Container API uses per-container self-signed TLS cert + shared Bearer token.

## Building the image

```bash
cd docker/site-template
docker build -t webpanel/php-site:8.2 .
```

Or let `docker compose up --build` handle it via the `docker-compose.yml`.

## Container API (port 9000)

Internal-only Flask API run by `gnukontrolr-admin` via supervisord.
Exposed on `webpanel_net` Docker network only — never mapped to the host.
Endpoints: `/health`, `/info`, `/services/*`, `/files`, `/exec`, `/backups/*`, `/restore/*`, `/sftp/*`, `/secure/*`
