from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from .config import settings


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def to_local(dt: Optional[datetime]) -> Optional[datetime]:
    aware = _aware(dt)
    if aware is None:
        return None
    return aware.astimezone(ZoneInfo(settings.display_timezone))


def format_local(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M") -> str:
    local = to_local(dt)
    return local.strftime(fmt) if local else "—"


def relative_time(dt: Optional[datetime]) -> str:
    aware = _aware(dt)
    if aware is None:
        return "—"
    delta = (datetime.now(timezone.utc) - aware).total_seconds()
    if delta < 60:
        return f"hace {int(delta)}s"
    if delta < 3600:
        return f"hace {int(delta // 60)} min"
    if delta < 86400:
        return f"hace {int(delta // 3600)} h"
    return f"hace {int(delta // 86400)} d"


def humanbytes(n: Optional[int]) -> str:
    if n is None:
        return "—"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def screenshot_thumb(path: Optional[str]) -> Optional[str]:
    """Convierte 'YYYY-MM-DD/HH-MM-SS.jpg' → 'YYYY-MM-DD/HH-MM-SS.thumb.jpg'.

    Si el thumb no existe (capturas viejas previas a la migración), cae al
    full path para no romper el <img>. El stat() por render es barato y
    desaparece cuando todas las capturas tienen thumb.
    """
    if not path or not path.endswith(".jpg") or path.endswith(".thumb.jpg"):
        return path
    thumb = path[:-4] + ".thumb.jpg"
    if not (settings.screenshots_path / thumb).exists():
        return path
    return thumb


def register_filters(env) -> None:
    env.filters["to_local"] = to_local
    env.filters["format_local"] = format_local
    env.filters["relative_time"] = relative_time
    env.filters["humanbytes"] = humanbytes
    env.filters["screenshot_thumb"] = screenshot_thumb
