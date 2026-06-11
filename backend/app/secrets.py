"""Secrets Vault — runtime access for the panel API.

The secrets vault is mounted at /run/secrets/ inside the webpanel container.
This module provides helpers to read secrets, resolve paths by UUID, and
expose the security matrix to the setup wizard.

Vault layout:
  /run/secrets/
  ├── install.id              # Installation UUID
  ├── secrets.json            # Security matrix manifest (JSON)
  ├── env/main.env            # Master environment file
  ├── config/pdns.conf        # PowerDNS config
  ├── tls/                    # TLS certificates
  ├── ssh/                    # SSH keypair
  └── dkim/                   # DKIM signing keys
"""
import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
VAULT_ROOT = Path(os.environ.get("SECRETS_VAULT", "/run/secrets"))

INSTALL_ID_PATH = VAULT_ROOT / "install.id"
MANIFEST_PATH   = VAULT_ROOT / "secrets.json"
MAIN_ENV_PATH   = VAULT_ROOT / "env" / "main.env"


# ── Vault status ─────────────────────────────────────────────────────────────
def vault_is_mounted() -> bool:
    """Return True if the secrets vault is mounted and accessible."""
    return VAULT_ROOT.is_dir() and INSTALL_ID_PATH.is_file()


def get_install_uuid() -> Optional[str]:
    """Read and return the installation UUID."""
    try:
        return INSTALL_ID_PATH.read_text().strip()
    except (FileNotFoundError, PermissionError, OSError) as exc:
        logger.warning("Cannot read install UUID: %s", exc)
        return None


def get_manifest() -> Optional[Dict[str, Any]]:
    """Parse and return the security matrix manifest (secrets.json)."""
    try:
        return json.loads(MANIFEST_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError, PermissionError) as exc:
        logger.warning("Cannot read secrets manifest: %s", exc)
        return None


# ── .env variable reader ─────────────────────────────────────────────────────
def read_env_var(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read a variable from the vault's main.env file (not os.environ).

    This is the *canonical* source of truth — it reads from the file itself
    rather than relying on environment variables that may be default/placeholder
    values from docker-compose.
    """
    try:
        if not MAIN_ENV_PATH.is_file():
            return default
        for line in MAIN_ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
        return default
    except (FileNotFoundError, PermissionError, OSError) as exc:
        logger.warning("Cannot read %s from vault env: %s", key, exc)
        return default


# ── Service-to-secret mapping (from manifest) ────────────────────────────────
def get_service_secrets(service_name: str) -> list:
    """Return the list of secret paths for a given service (e.g. 'webpanel')."""
    manifest = get_manifest()
    if not manifest:
        return []
    svc = manifest.get("services", {}).get(service_name, {})
    return svc.get("secrets", [])


def resolve_secret_path(rel_path: str) -> Optional[Path]:
    """Resolve a relative secret path (e.g. 'env/main.env') to an absolute Path.

    Returns None if the vault is not mounted or the path doesn't exist.
    """
    if not vault_is_mounted():
        return None
    candidate = VAULT_ROOT / rel_path
    return candidate if candidate.exists() else None


# ── Vault summary (for setup wizard / diagnostics) ───────────────────────────
def vault_summary() -> Dict[str, Any]:
    """Return a summary dict suitable for the setup wizard /diagnostics endpoint."""
    if not vault_is_mounted():
        return {"status": "unavailable", "path": str(VAULT_ROOT)}

    uuid = get_install_uuid()
    manifest = get_manifest()

    # Count files by category
    categories: Dict[str, int] = {}
    total_files = 0
    if manifest:
        for entry in manifest.get("files", []):
            t = entry.get("type", "unknown")
            categories[t] = categories.get(t, 0) + 1
            total_files += 1

    return {
        "status":         "mounted",
        "path":           str(VAULT_ROOT),
        "install_uuid":   uuid,
        "secret_count":   total_files,
        "categories":     categories,
        "manifest_version": manifest.get("version") if manifest else None,
        "services_mapped": list(manifest.get("services", {}).keys()) if manifest else [],
    }
