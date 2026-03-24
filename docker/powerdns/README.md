# docker/powerdns/

PowerDNS authoritative DNS server configuration.

## pdns.conf

| Setting | Value | Notes |
|---|---|---|
| `launch` | `gsqlite3` | SQLite backend |
| `gsqlite3-database` | `/var/lib/powerdns/pdns.sqlite3` | Stored in `powerdns_data` volume |
| `webserver` | `yes` | REST API on port 8081 |
| `webserver-allow-from` | `172.30.0.0/16` | Internal Docker network only |
| `api` | `yes` | REST API enabled |
| `allow-recursion` | `172.30.0.0/16` | Recursion for internal containers only |

## API authentication

The API key is set via the `PDNS_AUTH_API_KEY` environment variable (sourced from `.env`).
PowerDNS reads this automatically from the environment.

## DNS management

The panel's DNS page (`/api/dns/*` — not yet implemented as a dedicated router, use PowerDNS
API directly or via the frontend DNS page) manages zones and records via the PowerDNS REST API
at `http://powerdns:8081`.

## Adding a DNS record manually

```bash
# Example: add an A record via PowerDNS API
curl -X PATCH http://localhost:8081/api/v1/servers/localhost/zones/example.com. \
  -H "X-API-Key: your_pdns_api_key" \
  -H "Content-Type: application/json" \
  -d '{"rrsets": [{"name": "www.example.com.", "type": "A", "ttl": 300,
       "changetype": "REPLACE", "records": [{"content": "1.2.3.4", "disabled": false}]}]}'
```
