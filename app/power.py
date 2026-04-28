import ctypes
import logging
import platform

log = logging.getLogger(__name__)

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def keep_awake() -> bool:
    """Pide a Windows que no suspenda ni apague el display mientras el proceso vive.

    Idempotente y no-op fuera de Windows. El flag dura hasta que el proceso
    termine, no requiere job recurrente.
    """
    if platform.system() != "Windows":
        return False
    try:
        result = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
        )
        if result == 0:
            log.warning("SetThreadExecutionState devolvió 0 — flag no aplicado")
            return False
        log.info("Display + system keep-awake activado (Windows)")
        return True
    except Exception:
        log.exception("Falló SetThreadExecutionState")
        return False
