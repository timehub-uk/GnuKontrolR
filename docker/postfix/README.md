# docker/postfix/

Postfix outbound SMTP relay configuration.

## Configuration

Postfix is configured entirely via **environment variables** passed through `docker-compose.yml`:

| Variable | Description |
|---|---|
| `HOSTNAME` | Mail hostname (e.g. `mail.example.com`) |
| `RELAYHOST` | Optional upstream relay (leave empty to send direct) |
| `ALLOWED_SENDER_DOMAINS` | Space-separated list of allowed sender domains |

The `boky/postfix` Docker image generates `main.cf` and `master.cf` from these
environment variables at container startup — no manual config file is needed.

## Customisation

To override Postfix settings, add a `main.cf` file here and mount it in `docker-compose.yml`:

```yaml
volumes:
  - postfix_data:/var/spool/postfix
  - ./docker/postfix/main.cf:/etc/postfix/main.cf:ro
```

Make sure the file is complete — it will replace the image's auto-generated config.

## Testing mail delivery

```bash
# Send a test mail from inside the container
docker compose exec postfix sendmail -v your@email.com < /dev/stdin
```
