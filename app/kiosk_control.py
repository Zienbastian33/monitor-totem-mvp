import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

log = logging.getLogger(__name__)


def _state_file() -> Path:
    return settings.data_path / "control.json"


def _read() -> dict:
    path = _state_file()
    if not path.exists():
        return {"kiosk_enabled": True, "updated_at": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("control.json corrupto, reseteando a enabled")
        return {"kiosk_enabled": True, "updated_at": None}


def _write(data: dict) -> None:
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replace: tempfile in same dir + os.replace to avoid partial reads
    # if the watchdog tick fires mid-write.
    fd, tmp = tempfile.mkstemp(prefix=".control.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def is_enabled() -> bool:
    return bool(_read().get("kiosk_enabled", True))


def get_state() -> dict:
    data = _read()
    return {
        "kiosk_enabled": bool(data.get("kiosk_enabled", True)),
        "updated_at": data.get("updated_at"),
    }


def set_enabled(enabled: bool) -> dict:
    data = {
        "kiosk_enabled": bool(enabled),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(data)
    log.info("Kiosko %s", "habilitado" if enabled else "pausado")
    return data
