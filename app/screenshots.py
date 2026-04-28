import logging
from datetime import datetime, timezone
from typing import Optional

import mss
from PIL import Image
from sqlalchemy.orm import Session

from .config import settings
from .models import Screenshot

log = logging.getLogger(__name__)

MAX_WIDTH = 1920
JPEG_QUALITY = 75
THUMB_WIDTH = 480
THUMB_QUALITY = 60


def _select_monitor(sct: "mss.base.MSSBase") -> Optional[dict]:
    """Resuelve el monitor a capturar según settings.screenshot_monitor.

    mss.monitors[0] = bounding box de TODOS los monitores combinados.
    mss.monitors[1] = monitor primario.
    mss.monitors[2+] = monitores secundarios.
    """
    monitors = sct.monitors
    if not monitors:
        return None

    setting = (settings.screenshot_monitor or "primary").strip().lower()

    if setting == "all":
        return monitors[0]
    if setting == "primary":
        return monitors[1] if len(monitors) > 1 else monitors[0]

    try:
        idx = int(setting)
        if 0 <= idx < len(monitors):
            return monitors[idx]
        log.warning("SCREENSHOT_MONITOR=%s fuera de rango (hay %d). Usando primario.", setting, len(monitors))
    except ValueError:
        log.warning("SCREENSHOT_MONITOR=%s no reconocido. Usando primario.", setting)

    return monitors[1] if len(monitors) > 1 else monitors[0]


def capture_screen() -> Optional[Image.Image]:
    try:
        with mss.mss() as sct:
            monitor = _select_monitor(sct)
            if monitor is None:
                log.warning("No hay monitores disponibles")
                return None
            raw = sct.grab(monitor)
            return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    except Exception:
        log.exception("Falló captura de pantalla")
        return None


def save_screenshot(db: Session, totem_id: int) -> Optional[Screenshot]:
    img = capture_screen()
    if img is None:
        return None

    now = datetime.now(timezone.utc)
    daily_dir = settings.screenshots_path / now.strftime("%Y-%m-%d")
    daily_dir.mkdir(parents=True, exist_ok=True)
    full_path = daily_dir / f"{now.strftime('%H-%M-%S')}.jpg"

    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        img = img.resize((MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)

    img.save(full_path, "JPEG", quality=JPEG_QUALITY, optimize=True)

    try:
        thumb = img.copy()
        if thumb.width > THUMB_WIDTH:
            ratio = THUMB_WIDTH / thumb.width
            thumb = thumb.resize((THUMB_WIDTH, int(thumb.height * ratio)), Image.LANCZOS)
        thumb_path = full_path.with_name(full_path.stem + ".thumb.jpg")
        thumb.save(thumb_path, "JPEG", quality=THUMB_QUALITY, optimize=True)
    except Exception:
        log.exception("Falló generación de thumb para %s", full_path)

    relative_path = full_path.relative_to(settings.screenshots_path).as_posix()

    screenshot = Screenshot(
        totem_id=totem_id,
        path=relative_path,
        width=img.width,
        height=img.height,
        bytes=full_path.stat().st_size,
        is_archive=False,
        taken_at=now,
    )
    db.add(screenshot)
    db.flush()
    log.info("Screenshot guardado: %s (%d bytes)", relative_path, screenshot.bytes)
    return screenshot
