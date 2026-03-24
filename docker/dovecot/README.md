# docker/dovecot/

Dovecot IMAP/POP3 mail server configuration.

## Configuration

Dovecot uses its built-in default configuration from the `dovecot/dovecot` Docker image.
Environment variables and volume mounts can be used to customise it.

## Ports

| Port | Protocol |
|---|---|
| 143 | IMAP |
| 993 | IMAPS (TLS) |
| 110 | POP3 |
| 995 | POP3S (TLS) |

## Customisation

To override Dovecot settings, create a `dovecot.conf` file here and mount it:

```yaml
volumes:
  - dovecot_data:/var/mail
  - ./docker/dovecot/dovecot.conf:/etc/dovecot/dovecot.conf:ro
```

## Mail storage

Mail is stored in the `dovecot_data` Docker volume at `/var/mail` inside the container.

## Integration with Postfix

Postfix delivers mail; Dovecot handles retrieval (IMAP/POP3). In a production
deployment you will need to configure Dovecot's auth backend to match your
user database and set up Postfix → Dovecot LMTP delivery.
