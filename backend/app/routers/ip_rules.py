"""
Per-domain IP and country access rules.

- Standard users can manage rules for domains they own.
- Admins and superadmins can manage any domain.
- Master IPs (Docker bridge + server external IP) are ALWAYS protected and
  can never be added to a block list.  Any country CIDR overlapping master
  ranges is silently excluded when writing the Traefik config.
"""
import ipaddress
import logging
import os
import re
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models.domain import Domain
from app.models.domain_ip_rule import DomainIPRule, DomainCountryBlock
from app.models.user import User, Role

log = logging.getLogger("webpanel")
router = APIRouter(prefix="/api/domains", tags=["access-rules"])

# ── Master IP whitelist — these CIDRs can NEVER be blocked ────────────────────
_DOCKER_BRIDGE = "172.30.0.0/16"
_LOOPBACK      = "127.0.0.0/8"

def _master_networks() -> list[ipaddress.IPv4Network]:
    nets = [
        ipaddress.ip_network(_DOCKER_BRIDGE, strict=False),
        ipaddress.ip_network(_LOOPBACK,      strict=False),
    ]
    ext = os.environ.get("SERVER_IP", "").strip()
    if ext:
        try:
            nets.append(ipaddress.ip_network(ext + "/32", strict=False))
        except ValueError:
            pass
    return nets


def _overlaps_master(cidr: str) -> bool:
    """Return True if *cidr* overlaps any master network."""
    try:
        net = ipaddress.ip_network(cidr, strict=False)
        return any(net.overlaps(m) for m in _master_networks())
    except ValueError:
        return False


def _filter_cidrs(raw_cidrs: list[str]) -> list[str]:
    """Strip any CIDR that overlaps with master networks."""
    result = []
    masters = _master_networks()
    for cidr in raw_cidrs:
        try:
            net = ipaddress.ip_network(cidr.strip(), strict=False)
            if not any(net.overlaps(m) for m in masters):
                result.append(str(net))
        except ValueError:
            pass
    return result


# ── Traefik dynamic config path ───────────────────────────────────────────────
_TRAEFIK_DYNAMIC_DIR = Path(
    os.environ.get("TRAEFIK_DYNAMIC_DIR", "/app/traefik_dynamic")
)


def _traefik_slug(domain_name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "-", domain_name).lower()


def _write_traefik_config(domain_name: str, deny_cidrs: list[str]) -> None:
    """Write (or delete) a Traefik ipDenyList middleware file for *domain_name*.

    Traefik's file provider watches the directory and picks up changes live.
    """
    _TRAEFIK_DYNAMIC_DIR.mkdir(parents=True, exist_ok=True)
    slug       = _traefik_slug(domain_name)
    cfg_path   = _TRAEFIK_DYNAMIC_DIR / f"domain-{slug}-access.yml"
    mw_name    = f"{slug}-ipblock"

    filtered = _filter_cidrs(deny_cidrs)

    if not filtered:
        # Remove the file if no rules — clean state
        cfg_path.unlink(missing_ok=True)
        return

    cfg = {
        "http": {
            "middlewares": {
                mw_name: {
                    "ipDenyList": {
                        "sourceRange": filtered,
                    }
                }
            },
            "routers": {
                f"{slug}-https": {
                    "middlewares": [mw_name],
                }
            },
        }
    }
    cfg_path.write_text(yaml.dump(cfg, default_flow_style=False))
    log.info("Traefik access config written: %s (%d CIDRs)", cfg_path.name, len(filtered))


# ── Country CIDR cache (in-process, keyed by country code) ───────────────────
_CIDR_CACHE: dict[str, tuple[list[str], datetime]] = {}
_CIDR_LOCK  = asyncio.Lock()
_CIDR_TTL   = timedelta(hours=24)

async def _fetch_country_cidrs(cc: str, db: Optional[AsyncSession] = None) -> list[str]:
    """Return CIDRs for *cc*.

    Lookup order:
      1. In-process memory cache (fastest, avoids DB hit on repeated calls)
      2. country_data DB row (populated by /api/geo/sync-countries)
      3. Live fetch from ipdeny.com (fallback, result stored in memory cache)
    """
    async with _CIDR_LOCK:
        cached = _CIDR_CACHE.get(cc)
        if cached and (datetime.utcnow() - cached[1]) < _CIDR_TTL:
            return cached[0]

    # Try DB first
    if db is not None:
        try:
            from app.models.country_data import CountryData
            from sqlalchemy import select as _sel
            row = (await db.execute(
                _sel(CountryData).where(CountryData.country_code == cc)
            )).scalar_one_or_none()
            if row and row.cidrs:
                cidrs = [c for c in row.cidrs.splitlines() if c.strip()]
                async with _CIDR_LOCK:
                    _CIDR_CACHE[cc] = (cidrs, datetime.utcnow())
                return cidrs
        except Exception as exc:
            log.debug("DB CIDR lookup failed for %s: %s", cc, exc)

    # Fallback: live fetch from ipdeny.com
    async with _CIDR_LOCK:
        url = f"https://www.ipdeny.com/ipblocks/data/aggregated/{cc.lower()}-aggregated.zone"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
            if resp.status_code == 200:
                cidrs = [line.strip() for line in resp.text.splitlines() if line.strip()]
                _CIDR_CACHE[cc] = (cidrs, datetime.utcnow())
                return cidrs
        except Exception as exc:
            log.warning("Country CIDR live-fetch failed for %s: %s", cc, exc)
        return []


# ── ISO 3166-1 country list ───────────────────────────────────────────────────
COUNTRIES: list[dict] = [
    {"code": "AF", "name": "Afghanistan"}, {"code": "AL", "name": "Albania"},
    {"code": "DZ", "name": "Algeria"}, {"code": "AO", "name": "Angola"},
    {"code": "AR", "name": "Argentina"}, {"code": "AM", "name": "Armenia"},
    {"code": "AU", "name": "Australia"}, {"code": "AT", "name": "Austria"},
    {"code": "AZ", "name": "Azerbaijan"}, {"code": "BH", "name": "Bahrain"},
    {"code": "BD", "name": "Bangladesh"}, {"code": "BY", "name": "Belarus"},
    {"code": "BE", "name": "Belgium"}, {"code": "BZ", "name": "Belize"},
    {"code": "BJ", "name": "Benin"}, {"code": "BO", "name": "Bolivia"},
    {"code": "BA", "name": "Bosnia and Herzegovina"}, {"code": "BW", "name": "Botswana"},
    {"code": "BR", "name": "Brazil"}, {"code": "BN", "name": "Brunei"},
    {"code": "BG", "name": "Bulgaria"}, {"code": "BF", "name": "Burkina Faso"},
    {"code": "BI", "name": "Burundi"}, {"code": "KH", "name": "Cambodia"},
    {"code": "CM", "name": "Cameroon"}, {"code": "CA", "name": "Canada"},
    {"code": "CF", "name": "Central African Republic"}, {"code": "TD", "name": "Chad"},
    {"code": "CL", "name": "Chile"}, {"code": "CN", "name": "China"},
    {"code": "CO", "name": "Colombia"}, {"code": "CD", "name": "Congo (DRC)"},
    {"code": "CG", "name": "Congo (Republic)"}, {"code": "CR", "name": "Costa Rica"},
    {"code": "CI", "name": "Cote d'Ivoire"}, {"code": "HR", "name": "Croatia"},
    {"code": "CU", "name": "Cuba"}, {"code": "CY", "name": "Cyprus"},
    {"code": "CZ", "name": "Czech Republic"}, {"code": "DK", "name": "Denmark"},
    {"code": "DJ", "name": "Djibouti"}, {"code": "DO", "name": "Dominican Republic"},
    {"code": "EC", "name": "Ecuador"}, {"code": "EG", "name": "Egypt"},
    {"code": "SV", "name": "El Salvador"}, {"code": "GQ", "name": "Equatorial Guinea"},
    {"code": "ER", "name": "Eritrea"}, {"code": "EE", "name": "Estonia"},
    {"code": "ET", "name": "Ethiopia"}, {"code": "FI", "name": "Finland"},
    {"code": "FR", "name": "France"}, {"code": "GA", "name": "Gabon"},
    {"code": "GE", "name": "Georgia"}, {"code": "DE", "name": "Germany"},
    {"code": "GH", "name": "Ghana"}, {"code": "GR", "name": "Greece"},
    {"code": "GT", "name": "Guatemala"}, {"code": "GN", "name": "Guinea"},
    {"code": "GW", "name": "Guinea-Bissau"}, {"code": "HT", "name": "Haiti"},
    {"code": "HN", "name": "Honduras"}, {"code": "HK", "name": "Hong Kong"},
    {"code": "HU", "name": "Hungary"}, {"code": "IN", "name": "India"},
    {"code": "ID", "name": "Indonesia"}, {"code": "IR", "name": "Iran"},
    {"code": "IQ", "name": "Iraq"}, {"code": "IE", "name": "Ireland"},
    {"code": "IL", "name": "Israel"}, {"code": "IT", "name": "Italy"},
    {"code": "JM", "name": "Jamaica"}, {"code": "JP", "name": "Japan"},
    {"code": "JO", "name": "Jordan"}, {"code": "KZ", "name": "Kazakhstan"},
    {"code": "KE", "name": "Kenya"}, {"code": "KW", "name": "Kuwait"},
    {"code": "KG", "name": "Kyrgyzstan"}, {"code": "LA", "name": "Laos"},
    {"code": "LV", "name": "Latvia"}, {"code": "LB", "name": "Lebanon"},
    {"code": "LY", "name": "Libya"}, {"code": "LT", "name": "Lithuania"},
    {"code": "LU", "name": "Luxembourg"}, {"code": "MK", "name": "North Macedonia"},
    {"code": "MG", "name": "Madagascar"}, {"code": "MW", "name": "Malawi"},
    {"code": "MY", "name": "Malaysia"}, {"code": "MV", "name": "Maldives"},
    {"code": "ML", "name": "Mali"}, {"code": "MT", "name": "Malta"},
    {"code": "MR", "name": "Mauritania"}, {"code": "MX", "name": "Mexico"},
    {"code": "MD", "name": "Moldova"}, {"code": "MN", "name": "Mongolia"},
    {"code": "ME", "name": "Montenegro"}, {"code": "MA", "name": "Morocco"},
    {"code": "MZ", "name": "Mozambique"}, {"code": "MM", "name": "Myanmar"},
    {"code": "NA", "name": "Namibia"}, {"code": "NP", "name": "Nepal"},
    {"code": "NL", "name": "Netherlands"}, {"code": "NZ", "name": "New Zealand"},
    {"code": "NI", "name": "Nicaragua"}, {"code": "NE", "name": "Niger"},
    {"code": "NG", "name": "Nigeria"}, {"code": "KP", "name": "North Korea"},
    {"code": "NO", "name": "Norway"}, {"code": "OM", "name": "Oman"},
    {"code": "PK", "name": "Pakistan"}, {"code": "PS", "name": "Palestine"},
    {"code": "PA", "name": "Panama"}, {"code": "PG", "name": "Papua New Guinea"},
    {"code": "PY", "name": "Paraguay"}, {"code": "PE", "name": "Peru"},
    {"code": "PH", "name": "Philippines"}, {"code": "PL", "name": "Poland"},
    {"code": "PT", "name": "Portugal"}, {"code": "QA", "name": "Qatar"},
    {"code": "RO", "name": "Romania"}, {"code": "RU", "name": "Russia"},
    {"code": "RW", "name": "Rwanda"}, {"code": "SA", "name": "Saudi Arabia"},
    {"code": "SN", "name": "Senegal"}, {"code": "RS", "name": "Serbia"},
    {"code": "SL", "name": "Sierra Leone"}, {"code": "SG", "name": "Singapore"},
    {"code": "SK", "name": "Slovakia"}, {"code": "SI", "name": "Slovenia"},
    {"code": "SO", "name": "Somalia"}, {"code": "ZA", "name": "South Africa"},
    {"code": "KR", "name": "South Korea"}, {"code": "SS", "name": "South Sudan"},
    {"code": "ES", "name": "Spain"}, {"code": "LK", "name": "Sri Lanka"},
    {"code": "SD", "name": "Sudan"}, {"code": "SE", "name": "Sweden"},
    {"code": "CH", "name": "Switzerland"}, {"code": "SY", "name": "Syria"},
    {"code": "TW", "name": "Taiwan"}, {"code": "TJ", "name": "Tajikistan"},
    {"code": "TZ", "name": "Tanzania"}, {"code": "TH", "name": "Thailand"},
    {"code": "TG", "name": "Togo"}, {"code": "TN", "name": "Tunisia"},
    {"code": "TR", "name": "Turkey"}, {"code": "TM", "name": "Turkmenistan"},
    {"code": "UG", "name": "Uganda"}, {"code": "UA", "name": "Ukraine"},
    {"code": "AE", "name": "United Arab Emirates"}, {"code": "GB", "name": "United Kingdom"},
    {"code": "US", "name": "United States"}, {"code": "UY", "name": "Uruguay"},
    {"code": "UZ", "name": "Uzbekistan"}, {"code": "VE", "name": "Venezuela"},
    {"code": "VN", "name": "Vietnam"}, {"code": "YE", "name": "Yemen"},
    {"code": "ZM", "name": "Zambia"}, {"code": "ZW", "name": "Zimbabwe"},
]

_COUNTRY_MAP = {c["code"]: c["name"] for c in COUNTRIES}


# ── Auth helpers ──────────────────────────────────────────────────────────────

async def _get_owned_domain(
    domain_id: int,
    current: User,
    db: AsyncSession,
) -> Domain:
    """Return the domain if the current user owns it (or is admin/superadmin)."""
    result = await db.execute(select(Domain).where(Domain.id == domain_id))
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(404, "Domain not found")
    if current.role not in (Role.superadmin, Role.admin):
        if domain.owner_id != current.id:
            raise HTTPException(403, "Access denied: domain not owned by you")
    return domain


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class IPRuleIn(BaseModel):
    ip_cidr: str
    reason: Optional[str] = ""

    @field_validator("ip_cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        v = v.strip()
        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError:
            raise ValueError(f"Invalid IP or CIDR: {v!r}")
        if _overlaps_master(v):
            raise ValueError("Cannot block master / Docker bridge IP range")
        return str(ipaddress.ip_network(v, strict=False))


class CountryBlockIn(BaseModel):
    active: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _rebuild_traefik_config(domain: Domain, db: AsyncSession) -> None:
    """Gather all active rules for *domain* and write the Traefik config file."""
    # Specific IP/CIDR rules
    ip_result = await db.execute(
        select(DomainIPRule).where(
            DomainIPRule.domain_id == domain.id,
            DomainIPRule.active == True,
        )
    )
    deny_cidrs: list[str] = [r.ip_cidr for r in ip_result.scalars().all()]

    # Country blocks — fetch CIDRs for each active block
    cc_result = await db.execute(
        select(DomainCountryBlock).where(
            DomainCountryBlock.domain_id == domain.id,
            DomainCountryBlock.active == True,
        )
    )
    country_blocks = cc_result.scalars().all()

    for cb in country_blocks:
        cidrs = await _fetch_country_cidrs(cb.country_code, db=db)
        deny_cidrs.extend(cidrs)

    _write_traefik_config(domain.name, deny_cidrs)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/{domain_id}/access-rules")
async def list_rules(
    domain_id: int,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    domain = await _get_owned_domain(domain_id, current, db)

    ip_result = await db.execute(
        select(DomainIPRule).where(DomainIPRule.domain_id == domain.id)
    )
    cc_result = await db.execute(
        select(DomainCountryBlock).where(DomainCountryBlock.domain_id == domain.id)
    )

    return {
        "domain": domain.name,
        "ip_rules": [
            {
                "id":         r.id,
                "ip_cidr":    r.ip_cidr,
                "reason":     r.reason,
                "active":     r.active,
                "created_at": r.created_at,
            }
            for r in ip_result.scalars().all()
        ],
        "country_blocks": [
            {
                "id":           cb.id,
                "country_code": cb.country_code,
                "country_name": cb.country_name,
                "active":       cb.active,
                "created_at":   cb.created_at,
            }
            for cb in cc_result.scalars().all()
        ],
        "countries": COUNTRIES,
        "master_whitelist": [_DOCKER_BRIDGE, _LOOPBACK]
        + ([os.environ.get("SERVER_IP") + "/32"] if os.environ.get("SERVER_IP") else []),
    }


@router.post("/{domain_id}/access-rules/ip", status_code=201)
async def add_ip_rule(
    domain_id: int,
    body: IPRuleIn,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    domain = await _get_owned_domain(domain_id, current, db)

    rule = DomainIPRule(
        domain_id  = domain.id,
        ip_cidr    = body.ip_cidr,
        reason     = body.reason or "",
        active     = True,
        created_by = current.id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    await _rebuild_traefik_config(domain, db)

    return {"id": rule.id, "ip_cidr": rule.ip_cidr, "reason": rule.reason}


@router.delete("/{domain_id}/access-rules/ip/{rule_id}", status_code=204)
async def delete_ip_rule(
    domain_id: int,
    rule_id: int,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    domain = await _get_owned_domain(domain_id, current, db)

    await db.execute(
        delete(DomainIPRule).where(
            DomainIPRule.id        == rule_id,
            DomainIPRule.domain_id == domain.id,
        )
    )
    await db.commit()
    await _rebuild_traefik_config(domain, db)


@router.patch("/{domain_id}/access-rules/country/{country_code}")
async def set_country_block(
    domain_id: int,
    country_code: str,
    body: CountryBlockIn,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    country_code = country_code.upper()
    if country_code not in _COUNTRY_MAP:
        raise HTTPException(400, f"Unknown country code: {country_code}")

    domain = await _get_owned_domain(domain_id, current, db)

    result = await db.execute(
        select(DomainCountryBlock).where(
            DomainCountryBlock.domain_id    == domain.id,
            DomainCountryBlock.country_code == country_code,
        )
    )
    cb = result.scalar_one_or_none()

    if cb:
        cb.active = body.active
        cb.updated = datetime.utcnow()
    else:
        cb = DomainCountryBlock(
            domain_id    = domain.id,
            country_code = country_code,
            country_name = _COUNTRY_MAP[country_code],
            active       = body.active,
            created_by   = current.id,
        )
        db.add(cb)

    await db.commit()

    # Rebuild Traefik config (fetches fresh CIDRs if needed)
    await _rebuild_traefik_config(domain, db)

    return {"country_code": country_code, "active": body.active}


@router.post("/{domain_id}/access-rules/apply")
async def apply_rules(
    domain_id: int,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Force-regenerate the Traefik config for this domain (e.g. after CIDR refresh)."""
    domain = await _get_owned_domain(domain_id, current, db)
    await _rebuild_traefik_config(domain, db)
    return {"status": "applied", "domain": domain.name}
