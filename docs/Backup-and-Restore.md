# Backup & Restore

## Backup

### Via Host CLI

```bash
cd /opt/gnukontrolr
sudo bash setup.sh cmd_backup
```

This creates a timestamped backup directory at `/opt/gnukontrolr/backups/YYYYMMDD_HHMMSS/` containing:

| File | Contents |
|------|----------|
| `mysql_all.sql` | Full MySQL dump (all databases) |
| `env.bak` | Copy of `.env` |
| `volumes.txt` | List of Docker volumes |

### What's Not Included

- **Docker volumes** — MySQL data, PostgreSQL data, Redis data are NOT backed up by default
- **Customer site files** — stored in Docker volumes
- **SSL certificates** — managed by Traefik (stored in Traefik's volume)

For a full backup, also snapshot these Docker volumes:

```bash
docker run --rm -v mysql_data:/data -v /backup:/backup alpine tar czf /backup/mysql_data.tar.gz -C /data .
docker run --rm -v postgres_data:/data -v /backup:/backup alpine tar czf /backup/postgres_data.tar.gz -C /data .
```

## Restore

### Via Host CLI

```bash
cd /opt/gnukontrolr
sudo bash setup.sh cmd_restore
```

1. List of available backups is shown
2. Enter the backup folder name
3. Confirm the restore (this overwrites all databases!)
4. MySQL dump is restored

### Manual Restore Steps

If the automated restore fails:

```bash
# Restore MySQL
MYSQL_ROOT_PASSWORD="$(grep ^MYSQL_ROOT_PASSWORD= .env | cut -d= -f2-)"
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" docker compose exec -T mysql mysql -u root < /path/to/backup/mysql_all.sql

# Restore .env
cp /path/to/backup/env.bak .env

# Restart panel
docker compose up -d
```

## Automation

For automated backups, add a cron job:

```bash
# Daily at 3 AM
0 3 * * * cd /opt/gnukontrolr && /usr/bin/bash setup.sh cmd_backup

# Keep only last 7 days of backups
0 4 * * * find /opt/gnukontrolr/backups -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;
```
