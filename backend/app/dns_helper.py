"""DNS provisioning helpers — PowerDNS sync for the domains database.

Every domain in the DB has a corresponding PowerDNS zone whose records
exactly reflect what is stored.  Call these helpers whenever a domain is
created, updated, or deleted, and use sync_all_domains() to reconcile the
full database state against PowerDNS (e.g. on startup or via admin endpoint).

Zone layout per domain type
───────────────────────────
main / addon / parked
  {domain}.               A      → SERVER_IP
  www.{domain}.           A      → SERVER_IP
  mail.{domain}.          A      → SERVER_IP
  {domain}.               MX     → mail.{PANEL_DOMAIN} (priority 10)
  {domain}.               TXT    → SPF record
  mail._domainkey.{domain}. TXT  → DKIM public key  (generated once, immutable)
  _dmarc.{domain}.        TXT    → DMARC policy

subdomain (e.g. sub.example.com)
  {domain}.               A      → SERVER_IP
  (no www / MX / DKIM — managed on the parent domain)

redirect
  {domain}.               A      → SERVER_IP
  www.{domain}.           A      → SERVER_IP

DKIM keys
─────────
A 2048-bit RSA key pair is generated once per domain and stored at:
  /etc/opendkim/keys/{domain}/mail.private  (chmod 600, owned by opendkim)
  /etc/opendkim/keys/{domain}/mail.public

The keys are NEVER regenerated unless an admin explicitly calls
regenerate_dkim_key(domain, force=True).  This prevents accidental mail
delivery failures caused by key rotation without DNS TTL propagation.
"""
from __future__ import annotations

import base64
import logging
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from app.http_client import panel_client
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

if TYPE_CHECKING:
    from app.models.domain import Domain

log = logging.getLogger(__name__)

PDNS_BASE    = os.getenv("PDNS_API_URL", "http://webpanel_powerdns:8081/api/v1/servers/localhost")
PDNS_KEY     = os.getenv("PDNS_API_KEY", "")
SERVER_IP    = os.getenv("SERVER_IP", "")
PANEL_DOMAIN = os.getenv("PANEL_DOMAIN", "")
DKIM_KEYS_DIR = Path(os.getenv("DKIM_KEYS_DIR", "/etc/opendkim/keys"))
DKIM_SELECTOR = "mail"   # standard selector name; matches DNS record mail._domainkey.{domain}

_HEADERS = {"X-API-Key": PDNS_KEY, "Content-Type": "application/json"}


# ── DKIM key management ───────────────────────────────────────────────────────

def _dkim_key_dir(domain: str) -> Path:
    return DKIM_KEYS_DIR / domain


def dkim_key_exists(domain: str) -> bool:
    """Return True if a DKIM private key already exists for *domain*."""
    return (_dkim_key_dir(domain) / "mail.private").exists()


def generate_dkim_keypair(domain: str, force: bool = False) -> str:
    """Generate a 2048-bit RSA DKIM key pair for *domain*.

    Writes:
      {DKIM_KEYS_DIR}/{domain}/mail.private  (mode 600)
      {DKIM_KEYS_DIR}/{domain}/mail.public

    Returns the base64-encoded public key suitable for a DNS TXT record.

    If a key already exists and *force* is False, the existing public key
    is returned without regenerating — keys are immutable by default.
    Only superadmins may pass force=True.
    """
    key_dir = _dkim_key_dir(domain)
    priv_path = key_dir / "mail.private"
    pub_path  = key_dir / "mail.public"

    if priv_path.exists() and not force:
        # Return the already-stored public key without touching the private key
        return pub_path.read_text().strip()

    key_dir.mkdir(parents=True, exist_ok=True)

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Write private key (mode 600 — only the process owner can read it)
    pem_private = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    priv_path.write_bytes(pem_private)
    priv_path.chmod(stat.S_IRUSR | stat.S_IWUSR)   # 0o600

    # Write public key (DER → base64 for DNS TXT)
    pub_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pub_b64 = base64.b64encode(pub_der).decode()
    pub_path.write_text(pub_b64)

    _update_opendkim_tables(domain)
    log.info("DKIM keypair %s for %s", "regenerated" if force else "generated", domain)
    return pub_b64


def _update_opendkim_tables(domain: str) -> None:
    """Rewrite OpenDKIM signing.table and key.table inside the shared volume.

    Both files live at DKIM_KEYS_DIR (the volume mount) so OpenDKIM can read
    them.  opendkim.conf must reference keys/signing.table and keys/key.table.
    """
    signing_table = DKIM_KEYS_DIR / "signing.table"
    key_table     = DKIM_KEYS_DIR / "key.table"

    try:
        # Collect all domains that have keys
        domains_with_keys = sorted(
            d.name for d in DKIM_KEYS_DIR.iterdir()
            if d.is_dir() and (d / "mail.private").exists()
        )
    except OSError as exc:
        log.warning("Could not read DKIM keys directory %s: %s", DKIM_KEYS_DIR, exc)
        return

    signing_lines = [f"*@{d} {DKIM_SELECTOR}._domainkey.{d}\n" for d in domains_with_keys]
    key_lines = [
        f"{DKIM_SELECTOR}._domainkey.{d} {d}:{DKIM_SELECTOR}:"
        f"{DKIM_KEYS_DIR}/{d}/mail.private\n"
        for d in domains_with_keys
    ]

    try:
        signing_table.write_text("".join(signing_lines))
        key_table.write_text("".join(key_lines))
    except OSError as exc:
        log.warning("Could not update OpenDKIM tables: %s", exc)


def _dkim_txt_record(domain: str, pub_b64: str) -> dict:
    """Build the PowerDNS rrset for the DKIM TXT record.

    RFC 6376 §3.6.2.2: TXT record strings must be ≤255 bytes each.
    A 2048-bit RSA public key is ~392 chars base64, so we split the p= value
    into 253-char chunks and emit each as a separate quoted string.
    PowerDNS and all compliant resolvers reassemble adjacent quoted strings.
    """
    prefix = "v=DKIM1; k=rsa; p="
    # First chunk contains the prefix; remaining chunks are pure key data
    chunk_size = 253
    first_chunk = pub_b64[: chunk_size - len(prefix)]
    rest = pub_b64[chunk_size - len(prefix):]
    chunks = [f'"{prefix}{first_chunk}"']
    for i in range(0, len(rest), chunk_size):
        chunks.append(f'"{rest[i:i + chunk_size]}"')
    content = " ".join(chunks)
    return {
        "name": _z(f"{DKIM_SELECTOR}._domainkey.{domain}"),
        "type": "TXT",
        "ttl": 3600,
        "changetype": "REPLACE",
        "records": [{"content": content, "disabled": False}],
    }


# ── DNS record builders ───────────────────────────────────────────────────────

def _z(name: str) -> str:
    """Return name with a trailing dot (PowerDNS canonical form)."""
    return name.rstrip(".") + "."


def _ns_rrset(domain: str, nameservers: list[str], ttl: int = 86400) -> dict:
    """Build a NS rrset for a zone."""
    return {
        "name": _z(domain),
        "type": "NS",
        "ttl": ttl,
        "changetype": "REPLACE",
        "records": [{"content": _z(ns), "disabled": False} for ns in nameservers],
    }


def _a(name: str, ip: str, ttl: int = 300) -> dict:
    return {
        "name": _z(name),
        "type": "A",
        "ttl": ttl,
        "changetype": "REPLACE",
        "records": [{"content": ip, "disabled": False}],
    }


def _mx(domain: str, mail_host: str, priority: int = 10, ttl: int = 300) -> dict:
    return {
        "name": _z(domain),
        "type": "MX",
        "ttl": ttl,
        "changetype": "REPLACE",
        "records": [{"content": f"{priority} {_z(mail_host)}", "disabled": False}],
    }


def _txt(name: str, value: str, ttl: int = 300) -> dict:
    return {
        "name": _z(name),
        "type": "TXT",
        "ttl": ttl,
        "changetype": "REPLACE",
        "records": [{"content": f'"{value}"', "disabled": False}],
    }


def _cname(name: str, target: str, ttl: int = 300) -> dict:
    return {
        "name": _z(name),
        "type": "CNAME",
        "ttl": ttl,
        "changetype": "REPLACE",
        "records": [{"content": _z(target), "disabled": False}],
    }


def _caa(domain: str, tag: str, value: str, flag: int = 0, ttl: int = 3600) -> dict:
    return {
        "name": _z(domain),
        "type": "CAA",
        "ttl": ttl,
        "changetype": "REPLACE",
        "records": [{"content": f'{flag} {tag} "{value}"', "disabled": False}],
    }


def _build_rrsets(domain: "Domain", ip: str, mail_host: str) -> list[dict]:
    """Return the canonical rrsets for a domain based on its type.

    Record order:
      1. NS  (zone delegation — must be first for resolvers)
      2. NS glue A records (ns1/ns2 inside this zone)
      3. Apex A + www A
      4. Mail A + MX
      5. Service CNAMEs (imap/smtp/pop/sftp)
      6. Email security TXT (SPF, DKIM, DMARC, MTA-STS, TLS-RPT)
      7. CAA (certificate authority authorisation)

    DKIM keys are generated once and never replaced unless forced by an admin.
    """
    from app.models.domain import DomainType

    name   = domain.name
    rrsets: list[dict] = []

    # ── NS records — every zone type needs these ───────────────────────────
    panel_domain = PANEL_DOMAIN or name
    domain_ns1   = f"ns1.{name}"
    domain_ns2   = f"ns2.{name}"
    master_ns    = [f"ns1.{panel_domain}", f"ns2.{panel_domain}", f"ns3.{panel_domain}"]
    # Deduplicate while preserving order (handles PANEL_DOMAIN == domain.name)
    all_ns = list(dict.fromkeys(master_ns + [domain_ns1, domain_ns2]))
    rrsets.append(_ns_rrset(name, all_ns))
    # Glue A records for the domain-specific NS entries
    rrsets.append(_a(domain_ns1, ip, ttl=86400))
    rrsets.append(_a(domain_ns2, ip, ttl=86400))

    if domain.domain_type == DomainType.subdomain:
        # Subdomains only get an A record — mail/DKIM is on the parent
        rrsets.append(_a(name, ip))

    elif domain.domain_type in (DomainType.main, DomainType.addon, DomainType.parked):
        rrsets.append(_a(name, ip))
        rrsets.append(_a(f"www.{name}", ip))

        if mail_host:
            rrsets.append(_a(f"mail.{name}", ip))
            rrsets.append(_mx(name, mail_host))

            # ── Service CNAMEs ─────────────────────────────────────────────
            # imap/smtp/pop → mail.{name}   sftp → {name}
            rrsets.append(_cname(f"imap.{name}",  f"mail.{name}"))
            rrsets.append(_cname(f"smtp.{name}",  f"mail.{name}"))
            rrsets.append(_cname(f"pop.{name}",   f"mail.{name}"))
            rrsets.append(_cname(f"sftp.{name}",  name))

            # ── Email security TXT records ─────────────────────────────────
            # SPF: authorise this server IP + the designated mail host
            rrsets.append(_txt(name, f"v=spf1 a mx ip4:{ip} include:{panel_domain} ~all"))

            # DMARC
            rrsets.append(_txt(
                f"_dmarc.{name}",
                f"v=DMARC1; p=quarantine; rua=mailto:dmarc@{name}; ruf=mailto:dmarc@{name}; fo=1",
                ttl=3600,
            ))

            # DKIM — generate key once; immutable unless admin forces rotation
            try:
                pub_b64 = generate_dkim_keypair(name, force=False)
                rrsets.append(_dkim_txt_record(name, pub_b64))
            except Exception as exc:
                log.error("DKIM key generation failed for %s: %s", name, exc)

            # MTA-STS: advertise that this server supports SMTP TLS
            rrsets.append(_txt(f"_mta-sts.{name}", "v=STSv1; id=1", ttl=3600))

            # SMTP TLS reporting
            rrsets.append(_txt(
                f"_smtp._tls.{name}",
                f"v=TLSRPTv1; rua=mailto:tlsrpt@{name}",
                ttl=3600,
            ))

        # ── CAA — only allow Let's Encrypt to issue certificates ──────────
        rrsets.append(_caa(name, "issue",     "letsencrypt.org"))
        rrsets.append(_caa(name, "issuewild", "letsencrypt.org"))
        rrsets.append(_caa(name, "iodef",     f"mailto:ssl@{name}"))

    elif domain.domain_type == DomainType.redirect:
        rrsets.append(_a(name, ip))
        rrsets.append(_a(f"www.{name}", ip))

    return rrsets


# ── Zone management ───────────────────────────────────────────────────────────

async def _pdns_patch_with_retry(
    client: httpx.AsyncClient,
    zone: str,
    rrsets: list[dict],
    retries: int = 2,
) -> bool:
    """PATCH rrsets into a zone, retrying on transient errors.

    On a 422 Unprocessable Entity (malformed rrset), logs the offending
    rrset and skips it so the rest still apply.  Returns True if all
    records were written without error.
    """
    url = f"{PDNS_BASE}/zones/{zone}"
    for attempt in range(retries + 1):
        try:
            resp = await client.patch(url, headers=_HEADERS, json={"rrsets": rrsets})
            if resp.status_code in (200, 204):
                return True
            if resp.status_code == 422:
                # PowerDNS validation error — try records one by one to isolate the bad one
                log.warning("PowerDNS 422 on bulk patch for %s — isolating bad records", zone)
                ok_count = 0
                for rrset in rrsets:
                    try:
                        r2 = await client.patch(url, headers=_HEADERS, json={"rrsets": [rrset]})
                        if r2.status_code in (200, 204):
                            ok_count += 1
                        else:
                            log.error(
                                "Bad rrset skipped for %s: type=%s name=%s — %s",
                                zone, rrset.get("type"), rrset.get("name"), r2.text[:200],
                            )
                    except httpx.HTTPError as e2:
                        log.error("rrset patch error for %s %s: %s", zone, rrset.get("name"), e2)
                return ok_count > 0
            # 5xx — retry
            if resp.status_code >= 500 and attempt < retries:
                import asyncio as _asyncio
                await _asyncio.sleep(1.5 ** attempt)
                continue
            resp.raise_for_status()
        except httpx.TimeoutException:
            if attempt < retries:
                import asyncio as _asyncio
                log.warning("PowerDNS timeout patching %s (attempt %d/%d)", zone, attempt + 1, retries + 1)
                await _asyncio.sleep(2)
                continue
            log.error("PowerDNS timeout patching %s after %d retries", zone, retries)
            return False
        except httpx.HTTPError as exc:
            log.error("PowerDNS patch failed for %s: %s", zone, exc)
            return False
    return False


async def _ensure_zone(client: httpx.AsyncClient, zone: str) -> bool:
    """Create zone if it does not exist.  Retries once on transient errors.

    Returns True on success.
    """
    for attempt in range(2):
        try:
            resp = await client.get(f"{PDNS_BASE}/zones/{zone}", headers=_HEADERS)
            if resp.status_code == 404:
                cr = await client.post(
                    f"{PDNS_BASE}/zones",
                    headers=_HEADERS,
                    json={"name": zone, "kind": "Native", "nameservers": [], "rrsets": []},
                )
                if cr.status_code in (200, 201, 204, 422):
                    # 422 here = zone already exists (race condition) — that's fine
                    return True
                cr.raise_for_status()
            elif resp.status_code in (200, 204):
                return True
            else:
                resp.raise_for_status()
            return True
        except httpx.TimeoutException:
            if attempt == 0:
                import asyncio as _asyncio
                log.warning("PowerDNS timeout checking zone %s — retrying", zone)
                await _asyncio.sleep(1)
                continue
            log.error("PowerDNS timeout ensuring zone %s", zone)
            return False
        except httpx.HTTPError as exc:
            log.error("PowerDNS zone ensure failed for %s: %s", zone, exc)
            return False
    return False


# ── Public API ────────────────────────────────────────────────────────────────

async def provision_domain_dns(domain: "Domain", server_ip: str = "") -> None:
    """Create or fully replace the PowerDNS zone for *domain*.

    Provisions in order: zone creation → NS + glue + A + MX + service CNAMEs
    + email security TXT (SPF/DKIM/DMARC/MTA-STS/TLS-RPT) + CAA.

    Also ensures the panel NS glue zone is up to date so all new domains
    immediately have working NS delegation.
    """
    ip = server_ip or SERVER_IP
    if not ip:
        log.warning("SERVER_IP not set — skipping DNS provisioning for %s", domain.name)
        return

    mail_host = f"mail.{PANEL_DOMAIN}" if PANEL_DOMAIN else ""
    zone      = _z(domain.name)
    rrsets    = _build_rrsets(domain, ip, mail_host)

    if not rrsets:
        return

    async with panel_client(timeout=15) as client:
        if not await _ensure_zone(client, zone):
            log.error("DNS provisioning aborted for %s — zone ensure failed", domain.name)
            return
        ok = await _pdns_patch_with_retry(client, zone, rrsets)
        if ok:
            log.info("DNS provisioned: %s → %s (%s) [%d rrsets]",
                     domain.name, ip, domain.domain_type, len(rrsets))
        else:
            log.error("DNS provisioning incomplete for %s — some records may be missing", domain.name)
            return

    # Ensure the panel's own NS glue zone is current so the delegation resolves
    await sync_panel_ns_zone(ip)


async def rotate_dkim_key(domain: "Domain") -> str:
    """Admin-only: regenerate the DKIM key pair and update PowerDNS.

    Returns the new public key base64.
    """
    ip        = SERVER_IP
    mail_host = f"mail.{PANEL_DOMAIN}" if PANEL_DOMAIN else ""
    pub_b64   = generate_dkim_keypair(domain.name, force=True)

    # Push the updated DKIM TXT record immediately
    if ip:
        zone = _z(domain.name)
        async with panel_client(timeout=10) as client:
            await _ensure_zone(client, zone)
            try:
                resp = await client.patch(
                    f"{PDNS_BASE}/zones/{zone}",
                    headers=_HEADERS,
                    json={"rrsets": [_dkim_txt_record(domain.name, pub_b64)]},
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.error("DKIM TXT update failed for %s: %s", domain.name, exc)

    log.warning("DKIM key rotated for %s (admin action)", domain.name)
    return pub_b64


async def deprovision_domain_dns(domain_name: str) -> None:
    """Delete the PowerDNS zone for *domain_name*.

    Called after a domain is deleted from the DB.
    """
    zone = _z(domain_name)
    async with panel_client(timeout=10) as client:
        try:
            resp = await client.delete(f"{PDNS_BASE}/zones/{zone}", headers=_HEADERS)
            if resp.status_code not in (200, 204, 404):
                resp.raise_for_status()
            log.info("DNS zone deleted: %s", domain_name)
        except httpx.HTTPError as exc:
            log.error("PowerDNS zone delete failed for %s: %s", domain_name, exc)


async def register_vdns(domain: str, subdomain: str, server_ip: str = "") -> str:
    """Add an A record *subdomain*.*domain* → SERVER_IP inside the domain's zone.

    Returns the fully-qualified virtual hostname (e.g. "wordpress.example.com").
    Creates the zone if it doesn't exist yet.
    """
    ip   = server_ip or SERVER_IP
    fqdn = f"{subdomain}.{domain}"
    zone = _z(domain)

    if not ip:
        log.warning("SERVER_IP not set — skipping VDNS registration for %s", fqdn)
        return fqdn

    async with panel_client(timeout=10) as client:
        await _ensure_zone(client, zone)
        try:
            resp = await client.patch(
                f"{PDNS_BASE}/zones/{zone}",
                headers=_HEADERS,
                json={"rrsets": [_a(fqdn, ip)]},
            )
            if resp.status_code not in (200, 204):
                resp.raise_for_status()
            log.info("VDNS registered: %s → %s", fqdn, ip)
        except httpx.HTTPError as exc:
            log.error("VDNS registration failed for %s: %s", fqdn, exc)

    return fqdn


async def get_external_ip() -> str:
    """Detect the server's external IP via a public IP echo service.

    Falls back to SERVER_IP env var if the request fails.
    """
    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://ipecho.net/plain",
    ]
    for url in services:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(url, headers={"Accept": "text/plain"})
                if r.status_code == 200:
                    ip = r.text.strip()
                    if ip:
                        return ip
        except Exception:
            continue
    return SERVER_IP


async def sync_zone_ns(domain_name: str, ip: str) -> bool:
    """Upsert NS records and glue A records for *domain_name* pointing to *ip*.

    Each zone gets 5 NS records:
      ns1/ns2/ns3.{PANEL_DOMAIN}  — master nameservers (shared, hosted on this server)
      ns1/ns2.{domain_name}       — domain-specific nameservers

    A records (glue) are written inside each zone for the domain-specific NS:
      ns1.{domain_name} → ip
      ns2.{domain_name} → ip

    Master NS glue (ns1-3.{PANEL_DOMAIN}) is maintained in the panel's own zone
    by sync_panel_ns_zone().

    The zone must already exist. Returns True on success.
    """
    panel_domain = PANEL_DOMAIN or domain_name  # fallback: use domain itself as master
    master_ns    = [f"ns1.{panel_domain}", f"ns2.{panel_domain}", f"ns3.{panel_domain}"]
    domain_ns1, domain_ns2 = f"ns1.{domain_name}", f"ns2.{domain_name}"

    # Deduplicate while preserving order (handles PANEL_DOMAIN == domain_name)
    all_ns = list(dict.fromkeys(master_ns + [domain_ns1, domain_ns2]))

    zone = _z(domain_name)
    rrsets = [
        # Domain-specific glue A records inside this zone
        _a(domain_ns1, ip, ttl=86400),
        _a(domain_ns2, ip, ttl=86400),
        # NS rrset for the zone
        _ns_rrset(domain_name, all_ns),
    ]
    async with panel_client(timeout=15) as client:
        if not await _ensure_zone(client, zone):
            log.error("NS sync skipped for %s — zone not available", domain_name)
            return False
        ok = await _pdns_patch_with_retry(client, zone, rrsets)
        if ok:
            log.info("NS sync: %s → %d NS records → %s", domain_name, len(all_ns), ip)
        else:
            log.error("NS sync failed for %s", domain_name)
        return ok


async def sync_panel_ns_zone(ip: str) -> bool:
    """Ensure ns1/ns2/ns3.{PANEL_DOMAIN} A records and NS rrset exist in the panel zone.

    The panel's own zone needs:
      - NS records pointing to ns1-3.PANEL_DOMAIN (the zone delegates to itself)
      - A records for ns1/ns2/ns3 so external resolvers can find the nameservers

    This is called on startup and whenever the external IP changes.
    """
    if not PANEL_DOMAIN:
        return False
    zone  = _z(PANEL_DOMAIN)
    ns1   = f"ns1.{PANEL_DOMAIN}"
    ns2   = f"ns2.{PANEL_DOMAIN}"
    ns3   = f"ns3.{PANEL_DOMAIN}"
    rrsets = [
        # NS delegation for the panel zone itself
        _ns_rrset(PANEL_DOMAIN, [ns1, ns2, ns3]),
        # Glue A records for ns1-3
        _a(ns1, ip, ttl=86400),
        _a(ns2, ip, ttl=86400),
        _a(ns3, ip, ttl=86400),
    ]
    async with panel_client(timeout=15) as client:
        if not await _ensure_zone(client, zone):
            log.error("Panel NS zone ensure failed for %s", PANEL_DOMAIN)
            return False
        ok = await _pdns_patch_with_retry(client, zone, rrsets)
        if ok:
            log.info("Panel NS zone synced: ns1-3.%s → %s", PANEL_DOMAIN, ip)
        else:
            log.error("Panel NS zone sync incomplete for %s", PANEL_DOMAIN)
        return ok


async def sync_all_ns(domains: list["Domain"], ip: str = "") -> dict:
    """Update NS1/NS2/NS3 records for every domain zone with *ip*.

    Returns {"updated": [...], "errors": [...]}
    """
    server_ip = ip or SERVER_IP
    if not server_ip:
        return {"updated": [], "errors": ["SERVER_IP not set"]}
    updated: list[str] = []
    errors:  list[str] = []
    for domain in domains:
        ok = await sync_zone_ns(domain.name, server_ip)
        (updated if ok else errors).append(domain.name)
    return {"updated": updated, "errors": errors, "ip": server_ip}


async def sync_all_domains(domains: list["Domain"], server_ip: str = "") -> dict:
    """Reconcile PowerDNS against the full list of domains from the DB.

    - Creates/updates zones for every domain in *domains*.
    - Deletes zones in PowerDNS that have no corresponding DB entry.

    Returns: {"provisioned": [...], "deleted": [...], "errors": [...]}
    """
    ip        = server_ip or SERVER_IP
    mail_host = f"mail.{PANEL_DOMAIN}" if PANEL_DOMAIN else ""

    provisioned: list[str] = []
    deleted:     list[str] = []
    errors:      list[str] = []

    # Fetch existing zones from PowerDNS.
    existing_zones: set[str] = set()
    async with panel_client(timeout=10) as client:
        try:
            resp = await client.get(f"{PDNS_BASE}/zones", headers=_HEADERS)
            resp.raise_for_status()
            for z in resp.json():
                existing_zones.add(z["id"].rstrip("."))
        except httpx.HTTPError as exc:
            log.error("PowerDNS zone list failed: %s", exc)
            errors.append(f"zone-list: {exc}")
            return {"provisioned": provisioned, "deleted": deleted, "errors": errors}

    db_names = {d.name for d in domains}

    # Provision every DB domain.
    for domain in domains:
        if not ip:
            errors.append(f"{domain.name}: SERVER_IP not set")
            continue
        zone   = _z(domain.name)
        rrsets = _build_rrsets(domain, ip, mail_host)
        if not rrsets:
            continue
        async with panel_client(timeout=15) as client:
            if not await _ensure_zone(client, zone):
                errors.append(f"{domain.name}: zone ensure failed")
                continue
            ok = await _pdns_patch_with_retry(client, zone, rrsets)
            if ok:
                provisioned.append(domain.name)
            else:
                errors.append(f"{domain.name}: patch failed after retries")

    # Delete zones that exist in PowerDNS but not in the DB.
    # Never delete the panel's own zone — it is not a customer domain.
    protected = {PANEL_DOMAIN} if PANEL_DOMAIN else set()
    stale = existing_zones - db_names - protected
    for name in stale:
        async with panel_client(timeout=10) as client:
            try:
                resp = await client.delete(f"{PDNS_BASE}/zones/{_z(name)}", headers=_HEADERS)
                if resp.status_code not in (200, 204, 404):
                    resp.raise_for_status()
                deleted.append(name)
                log.info("DNS sync: removed stale zone %s", name)
            except httpx.HTTPError as exc:
                log.error("DNS sync delete failed for %s: %s", name, exc)
                errors.append(f"{name} (delete): {exc}")

    # Sync panel NS glue zone once after all customer domains are provisioned
    if ip:
        await sync_panel_ns_zone(ip)

    log.info(
        "DNS sync complete — provisioned=%d deleted=%d errors=%d",
        len(provisioned), len(deleted), len(errors),
    )
    return {"provisioned": provisioned, "deleted": deleted, "errors": errors}
