import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from .chrome_watchdog import chrome
from .config import settings
from .db import session_scope
from .models import Screenshot
from .screenshots import save_screenshot
from .totem_registry import ensure_local_totem, touch_heartbeat

log = logging.getLogger(__name__)


def screenshot_job() -> None:
    try:
        with session_scope() as db:
            totem = ensure_local_totem(db)
            save_screenshot(db, totem.id)
            touch_heartbeat(db, totem.id)
    except Exception:
        log.exception("Falló screenshot_job")


def watchdog_job() -> None:
    try:
        chrome.ensure_running(settings.kiosk_url)
    except Exception:
        log.exception("Falló watchdog_job")


def retention_job() -> None:
    """Borra screenshots > 24h, conservando 1 por día como archivo."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.retention_hours_full)
        with session_scope() as db:
            old = db.scalars(
                select(Screenshot)
                .where(Screenshot.taken_at < cutoff, Screenshot.is_archive.is_(False))
                .order_by(Screenshot.taken_at.asc())
            ).all()

            if not old:
                return

            archived_days: set[str] = set()
            if settings.keep_daily_archive:
                already = db.scalars(select(Screenshot).where(Screenshot.is_archive.is_(True))).all()
                archived_days = {s.taken_at.date().isoformat() for s in already}

            kept = 0
            deleted = 0
            for ss in old:
                day = ss.taken_at.date().isoformat()
                if settings.keep_daily_archive and day not in archived_days:
                    ss.is_archive = True
                    archived_days.add(day)
                    kept += 1
                    continue
                full_path = settings.screenshots_path / ss.path
                thumb_path = full_path.with_name(full_path.stem + ".thumb.jpg")
                for p in (full_path, thumb_path):
                    if p.exists():
                        try:
                            p.unlink()
                        except OSError:
                            log.exception("No pude borrar %s", p)
                db.delete(ss)
                deleted += 1
            log.info("Retención → %d archivados, %d borrados", kept, deleted)
    except Exception:
        log.exception("Falló retention_job")


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    now = datetime.now(timezone.utc)
    scheduler.add_job(
        screenshot_job,
        "interval",
        seconds=settings.screenshot_interval_seconds,
        id="screenshot",
        next_run_time=now + timedelta(seconds=15),
    )
    scheduler.add_job(
        watchdog_job,
        "interval",
        seconds=settings.watchdog_interval_seconds,
        id="watchdog",
        next_run_time=now + timedelta(seconds=5),
    )
    scheduler.add_job(
        retention_job,
        "interval",
        seconds=settings.retention_interval_seconds,
        id="retention",
        next_run_time=now + timedelta(minutes=2),
    )
    return scheduler
