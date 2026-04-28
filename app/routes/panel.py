from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..chrome_watchdog import chrome
from ..config import settings
from ..db import get_db
from ..disk_usage import screenshots_disk_usage
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

    disk_bytes, disk_files = screenshots_disk_usage()

    return request.app.state.templates.TemplateResponse(
        request,
        "index.html",
        {
            "cards": cards,
            "chrome_running": chrome.is_running(),
            "kiosk_url": settings.kiosk_url,
            "ngrok_url": get_public_url(),
            "disk_bytes": disk_bytes,
            "disk_files": disk_files,
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
        request,
        "totem_detail.html",
        {
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


@router.get("/screenshots/{path:path}")
def serve_screenshot(path: str) -> FileResponse:
    base = settings.screenshots_path.resolve()
    target = (base / path).resolve()
    if not target.is_relative_to(base):
        raise HTTPException(status_code=404, detail="Not found")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)
