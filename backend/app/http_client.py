"""
Shared httpx client factory.
All outbound HTTP requests from the panel identify as GnuKontrolR-Browser.
"""
import httpx

PANEL_UA = "GnuKontrolR-Browser/1.0"
_DEFAULT_HEADERS = {"User-Agent": PANEL_UA}


def panel_client(**kwargs) -> httpx.AsyncClient:
    """Return an AsyncClient with the panel User-Agent pre-set."""
    headers = dict(kwargs.pop("headers", {}))
    headers.setdefault("User-Agent", PANEL_UA)
    return httpx.AsyncClient(headers=headers, **kwargs)
