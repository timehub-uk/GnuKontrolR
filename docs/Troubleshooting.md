# Troubleshooting

## Services Won't Start

### Port 53 Already in Use

```bash
# Check what's using port 53
sudo ss -tulpn | grep ':53 '

# If it's systemd-resolved:
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved
# Or run setup.sh which can handle this automatically
```

### Docker Socket GID Mismatch

```bash
# Check the actual GID
stat -c '%g' /var/run/docker.sock

# Update in .env
sudo sed -i "s/DOCKER_SOCK_GID=.*/DOCKER_SOCK_GID=$(stat -c '%g' /var/run/docker.sock)/" /opt/gnukontrolr/.env

# Restart panel
docker compose up -d webpanel
```

### MySQL Won't Start

```bash
docker compose logs mysql
# Common: permission issues on data directory
sudo chown -R 999:999 /var/lib/docker/volumes/gnukontrolr_mysql_data
```

## Panel Not Loading

### Check service status

```bash
panel service status
# or
docker compose ps
```

### Check logs

```bash
panel log view panel --lines 100
# or
docker compose logs webpanel_api --tail 100
```

### Frontend not loading

```bash
# Rebuild frontend
cd /opt/gnukontrolr/frontend
npm install && npm run build
```

### DNS resolution from panel

If the panel can't resolve service names (e.g., `mysql`, `postgres`), ensure Docker's embedded DNS is in the DNS list:

```yaml
# docker-compose.yml — webpanel service
dns:
  - 127.0.0.11    # Docker embedded DNS (required)
  - 8.8.8.8       # fallback
```

## Terminal Issues

### Permission Denied

If the terminal shows permission errors:
- Ensure `panelapi` user has `/bin/bash` as shell in the Dockerfile
- Ensure `HOME` is set to `/app` and `USER` to `panelapi` in `terminal.py`

### Bash Job Control Warnings

If you see `bash: cannot set terminal process group` warnings, the `+m` flag is missing:
- In `terminal.py`, ensure bash is invoked as `bash --login +m`

## DNS Issues

### PowerDNS API Connection

```bash
# Verify the API key matches between .env and pdns.conf
grep PDNS_API_KEY /opt/gnukontrolr/.env
grep api-key /opt/gnukontrolr/docker/powerdns/pdns.conf
```

### DNS Not Resolving

```bash
# Check PowerDNS is running
panel service status

# Test query
dig @localhost example.com

# Check logs
docker compose logs powerdns --tail 50
```

## Email Issues

### SMTP Not Sending

```bash
# Check Postfix logs
docker compose logs postfix --tail 50

# Test sending
echo "Test" | mail -s "Test" user@example.com

# Check DKIM
docker compose logs opendkim --tail 20
```

### IMAP Not Receiving

```bash
# Check Dovecot logs
docker compose logs dovecot --tail 50

# Test connection
telnet localhost 143
```

## SSL Certificate Issues

### Let's Encrypt Rate Limited

If you get rate-limited by Let's Encrypt, certificates can be stalled for a week. Use the staging server for testing:

```bash
# In docker-compose.yml, add to Traefik args:
- --certificatesresolvers.letsencrypt.acme.caserver=https://acme-staging-v02.api.letsencrypt.org/directory
```

### Manual Certificate Upload Fails

Ensure certificates are in PEM format and include the full chain:

```bash
# Validate PEM
openssl x509 -in cert.pem -text -noout
openssl rsa -in key.pem -check
```
