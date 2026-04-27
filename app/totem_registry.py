"""Maneja el registro auto-mágico del tótem local en la BBDD.

El MVP corre en una sola PC; en el primer arranque crea el registro `Totem`
usando el hostname como identidad estable. En arranques siguientes lo encuentra
y actualiza nombre/ubicación si cambiaron en la config.
"""

import socket
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Totem, utcnow


def _slugify(value: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in value).strip("-")


def derive_public_id(hostname: str) -> str:
    slug = _slugify(hostname) or "totem"
    suffix = uuid.uuid5(uuid.NAMESPACE_DNS, hostname).hex[:8]
    return f"{slug}-{suffix}"


def ensure_local_totem(db: Session) -> Totem:
    hostname = socket.gethostname()
    public_id = derive_public_id(hostname)
    name = settings.totem_name or hostname
    location = settings.totem_location

    totem = db.scalar(select(Totem).where(Totem.public_id == public_id))
    if totem is None:
        totem = Totem(
            public_id=public_id,
            hostname=hostname,
            name=name,
            location=location,
            last_heartbeat=utcnow(),
        )
        db.add(totem)
        db.flush()
        return totem

    changed = False
    if totem.name != name:
        totem.name = name
        changed = True
    if totem.location != location:
        totem.location = location
        changed = True
    if totem.hostname != hostname:
        totem.hostname = hostname
        changed = True
    if changed:
        db.flush()
    return totem


def touch_heartbeat(db: Session, totem_id: int) -> None:
    totem = db.get(Totem, totem_id)
    if totem is not None:
        totem.last_heartbeat = utcnow()


def get_local_totem(db: Session) -> Optional[Totem]:
    hostname = socket.gethostname()
    public_id = derive_public_id(hostname)
    return db.scalar(select(Totem).where(Totem.public_id == public_id))
