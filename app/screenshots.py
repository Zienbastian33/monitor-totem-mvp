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


def capture_primary_screen() -> Optional[Image.Image]:
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            raw = sct.grab(monitor)
            return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    except Exception:
        log.exception("Falló captura de pantalla")
        return None


def save_screenshot(db: Session, totem_id: int) -> Optional[Screenshot]:
    img = capture_primary_screen()
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
