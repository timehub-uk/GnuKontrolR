# Security

## Authentication

### JWT Tokens

All API requests (except login) require a valid JWT token:
- Signed with `SECRET_KEY` from `.env`
- Expires after 24 hours by default
- Refreshed automatically by the frontend

### Password Storage

- Passwords are hashed with **bcrypt** using `passlib`
- Support PINs also use bcrypt hashing
- No plaintext passwords stored anywhere

### Default Credentials

The installer generates random passwords for:
- MySQL root password
- PostgreSQL password
- JWT SECRET_KEY
- PowerDNS API key

These are stored in `.env` (permissions 600).

## Network Security

### Container Isolation
- Customer site containers are fully isolated
- No host network access from customer containers
- Resource limits via Docker

### Firewall
- Fail2ban with custom jail rules
- Geo-blocking via iptables ipset (optional)
- Traefik middleware for IP whitelisting

### CVE Monitoring
- Built-in CVE feed from NVD and CVE.org
- Searchable, filterable by severity
- 6-hour cache to avoid rate limits

## API Security

### CSRF Protection
- Origin and Referer headers validated on all mutating requests
- Strict host comparison (not substring match)

### Rate Limiting
- 200 requests per 15-minute window by default
- Configurable via Traefik middleware

### Input Validation
- SQL identifiers sanitised (alphanumeric + underscore only)
- PEM certificates validated before writing
- PHP ini directives checked against security-critical keys
- No shell interpolation in admin account creation (env vars + single-quoted heredoc)

## Docker Security

### Socket Access
- Docker socket mounted read-only where possible
- Panel API user in `docker` group for container management
- Docker socket GID detected at deploy time

### cAdvisor
- Runs with `privileged: true` (required for host metrics)
- Only accessible on internal network

### Container Images
- Regular base image pulls (`docker compose pull`)
- Security updates applied via `panel update` or `setup.sh cmd_update`

## Secrets Management

| Secret | Location | Protection |
|--------|----------|------------|
| DB passwords | `.env` | File permissions 600 |
| JWT SECRET_KEY | `.env` | 600, never exposed in logs |
| PowerDNS API key | `.env` + `pdns.conf` | Overwritten by `setup.sh` |
| MySQL root password | `.env` | Passed via `MYSQL_PWD` env var (never in `ps aux`) |
| User passwords | Database | bcrypt hashed |

## Production Checklist

- [ ] Change all default secrets in `.env`
- [ ] Enable Fail2ban rules in Security → Fail2ban
- [ ] Configure geo-blocking if needed
- [ ] Review Grafana dashboards for anomalies
- [ ] Set up regular backups
- [ ] Monitor CVE feed weekly
- [ ] Keep system updated (`panel update`)
- [ ] Use strong admin passwords
- [ ] Disable unused services in `docker-compose.yml`
