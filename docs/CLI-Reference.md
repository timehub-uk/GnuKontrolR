# CLI Reference — `panel`

The `panel` command is the administration CLI, available inside the WebPanel Terminal.

## Interactive Shell

```bash
panel
```

Opens an interactive REPL. Type commands directly:

```
panel> service status
panel> container list
panel> dns zones
panel> /list        # show all commands
panel> exit         # quit
```

## Command Reference

### `service`

Manage Docker services.

```bash
panel service                # alias for: service status
panel service status         # Show all services, health, uptime
panel service restart <name> # Restart a service by container name
```

### `container`

Manage Docker containers.

```bash
panel container              # alias for: container list
panel container list         # List all containers (name, image, status)
panel container stats        # Live CPU/memory stats for all containers
panel container logs <name>  # View container logs (--lines N, default 50)
```

### `user`

Manage panel users.

```bash
panel user                   # alias for: user list
panel user list              # List all users
panel user create <name> <email>   # Create user (--password, --role)
panel user reset-pass <name>       # Reset password (--password or auto)
panel user delete <name>           # Delete user
```

### `domain`

Manage customer domains.

```bash
panel domain                 # alias for: domain list
panel domain list            # List all domains (--user-id to filter)
```

### `dns`

Manage DNS zones and records.

```bash
panel dns                    # alias for: dns zones
panel dns zones              # List all DNS zones
panel dns records <zone>     # List DNS records for a zone
```

### `sys`

System information and diagnostics.

```bash
panel sys                    # alias for: sys info
panel sys info               # CPU, memory, disk, Docker info
panel sys port <number>      # Check if a port is in use
```

### `db`

Database connectivity tools.

```bash
panel db                     # alias for: db status
panel db status              # Test MySQL, PostgreSQL, Redis connections
panel db mysql               # Open interactive MySQL shell
panel db postgres            # Open interactive PostgreSQL shell
```

### `log`

Log viewer.

```bash
panel log                    # alias for: log sources
panel log sources            # List available log sources
panel log view <source>      # View log (--lines N, default 50)
```

### `update`

Run full update cycle.

```bash
panel update                 # git pull → npm install → build → rebuild Docker → restart
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid command or arguments |
