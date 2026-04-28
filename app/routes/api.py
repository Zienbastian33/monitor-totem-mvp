from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..chrome_watchdog import chrome
from ..config import settings
from ..db import get_db
from ..models import Totem
from ..ngrok_client import get_public_url

# Public: no auth required (probes, health checks).
public_router = APIRouter()
# Protected: auth applied at app.include_router level.
router = APIRouter()


@public_router.get("/health")
def health() -> dict:
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    totems = db.scalars(select(Totem)).all()
    return {
        "kiosk_url": settings.kiosk_url,
        "chrome_running": chrome.is_running(),
        "ngrok_url": get_public_url(),
        "totems": [
            {
                "public_id": t.public_id,
                "name": t.name,
                "hostname": t.hostname,
                "location": t.location,
                "last_heartbeat": t.last_heartbeat.isoformat() if t.last_heartbeat else None,
            }
            for t in totems
        ],
    }
