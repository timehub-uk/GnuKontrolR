# Domain Management

## Adding a Domain

### Via Web UI

1. Navigate to **Domains** → **Add Domain**
2. Fill in:
   - **Domain name** — the full domain (e.g., `example.com`)
   - **Owner** — the user responsible for this domain
   - **Plan** — hosting plan (if configured)
3. Click **Save**

### Via CLI

```bash
panel domain list
```

## DNS Management

### Zone Management

Each domain gets a DNS zone in PowerDNS automatically.

```bash
panel dns zones          # List all zones
panel dns records example.com  # View DNS records
```

### Record Types

| Type | Use Case |
|------|----------|
| **A** | Map domain to IPv4 address |
| **AAAA** | Map domain to IPv6 address |
| **CNAME** | Alias one domain to another |
| **MX** | Mail server for the domain |
| **TXT** | Verification records, SPF, DKIM, DMARC |
| **NS** | Name server delegation |
| **SRV** | Service location records |

### Via Web UI

1. Go to **DNS**
2. Select the zone
3. Click **Add Record** to add a new record
4. Click a record to edit or delete

## SSL/TLS Certificates

### Automatic (Let's Encrypt via Traefik)

When a domain is added, Traefik automatically:
1. Detects the new domain
2. Requests a Let's Encrypt certificate
3. Configures the reverse proxy
4. Auto-renews certificates before expiry

### Custom Certificate Upload

1. Go to the **SSL** section in domain settings
2. Upload your certificate (PEM format)
3. Upload the private key (PEM format)
4. The panel validates the PEM before saving

### Certificate Validation

Uploaded certificates are validated:
- Correct PEM header/footer
- Valid base64-encoded body
- Private key matches certificate

## Email Configuration

When adding a domain, email settings are auto-configured:

| Setting | Value |
|---------|-------|
| **DKIM** | Auto-generated key pair |
| **SPF** | `v=spf1 mx a:mail.yourdomain.com ~all` |
| **DMARC** | `v=DMARC1; p=none` (configurable) |
| **MX** | Points to your mail server |
