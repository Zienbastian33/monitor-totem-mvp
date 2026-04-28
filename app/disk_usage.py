import time

from .config import settings

_TTL_SECONDS = 60.0
_cache: dict = {"ts": 0.0, "bytes": 0, "files": 0}


def screenshots_disk_usage() -> tuple[int, int]:
    """Suma bytes y archivos JPG bajo data/screenshots/ con cache TTL 60s."""
    now = time.time()
    if now - _cache["ts"] < _TTL_SECONDS:
        return _cache["bytes"], _cache["files"]
    total_bytes = 0
    total_files = 0
    base = settings.screenshots_path
    if base.exists():
        for p in base.rglob("*.jpg"):
            try:
                total_bytes += p.stat().st_size
                total_files += 1
            except OSError:
                continue
    _cache.update(ts=now, bytes=total_bytes, files=total_files)
    return total_bytes, total_files
