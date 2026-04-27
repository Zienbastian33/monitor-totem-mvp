from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..chrome_watchdog import chrome
from ..config import settings
from ..db import get_db
from ..models import Screenshot, Totem
from ..ngrok_client import get_public_url

router = APIRouter()


def _status_for(totem: Totem) -> str:
    if totem.last_heartbeat is None:
        return "unknown"
    aware = totem.last_heartbeat if totem.last_heartbeat.tzinfo else totem.last_heartbeat.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - aware).total_seconds()
    return "offline" if age > settings.offline_threshold_seconds else "online"


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    totems = db.scalars(select(Totem).order_by(Totem.name)).all()
    cards = []
    for t in totems:
        last = db.scalar(
            select(Screenshot)
            .where(Screenshot.totem_id == t.id)
            .order_by(desc(Screenshot.taken_at))
            .limit(1)
        )
        cards.append(
            {
                "totem": t,
                "last_screenshot": last,
                "status": _status_for(t),
            }
        )

    return request.app.state.templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "cards": cards,
            "chrome_running": chrome.is_running(),
            "kiosk_url": settings.kiosk_url,
            "ngrok_url": get_public_url(),
        },
    )


@router.get("/totems/{public_id}", response_class=HTMLResponse)
def totem_detail(public_id: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    totem = db.scalar(select(Totem).where(Totem.public_id == public_id))
    if totem is None:
        raise HTTPException(status_code=404, detail="Tótem no encontrado")

    recent = db.scalars(
        select(Screenshot)
        .where(Screenshot.totem_id == totem.id, Screenshot.is_archive.is_(False))
        .order_by(desc(Screenshot.taken_at))
        .limit(50)
    ).all()

    archive = db.scalars(
        select(Screenshot)
        .where(Screenshot.totem_id == totem.id, Screenshot.is_archive.is_(True))
        .order_by(desc(Screenshot.taken_at))
        .limit(30)
    ).all()

    return request.app.state.templates.TemplateResponse(
        "totem_detail.html",
        {
            "request": request,
            "totem": totem,
            "status": _status_for(totem),
            "last_screenshot": recent[0] if recent else None,
            "recent": recent,
            "archive": archive,
            "chrome_running": chrome.is_running(),
            "kiosk_url": settings.kiosk_url,
            "ngrok_url": get_public_url(),
        },
    )
