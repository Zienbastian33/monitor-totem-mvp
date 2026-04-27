import logging
from typing import Optional

import httpx

from .config import settings

log = logging.getLogger(__name__)


def get_public_url(timeout: float = 1.0) -> Optional[str]:
    """Consulta la API local de ngrok para obtener la URL pública del túnel."""
    url = f"{settings.ngrok_local_api.rstrip('/')}/api/tunnels"
    try:
        resp = httpx.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    tunnels = data.get("tunnels", [])
    for tunnel in tunnels:
        public_url = tunnel.get("public_url", "")
        if public_url.startswith("https://"):
            return public_url
    for tunnel in tunnels:
        public_url = tunnel.get("public_url", "")
        if public_url:
            return public_url
    return None
