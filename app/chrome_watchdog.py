import json
import logging
import os
import platform
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

import psutil

from .config import settings

log = logging.getLogger(__name__)

WINDOWS_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

MACOS_CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UNIX_CHROME_BINS = ["google-chrome", "chrome", "chromium-browser", "chromium"]


def find_chrome_binary() -> Optional[Path]:
    if settings.chrome_path:
        p = Path(settings.chrome_path)
        return p if p.exists() else None

    system = platform.system()
    if system == "Windows":
        for path in WINDOWS_CHROME_PATHS:
            if Path(path).exists():
                return Path(path)
        return None

    if system == "Darwin" and Path(MACOS_CHROME_PATH).exists():
        return Path(MACOS_CHROME_PATH)

    for binary in UNIX_CHROME_BINS:
        found = shutil.which(binary)
        if found:
            return Path(found)
    return None


def kiosk_flags(url: str, user_data_dir: Path) -> list[str]:
    return [
        "--kiosk",
        "--noerrdialogs",
        "--disable-infobars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=TranslateUI",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-pinch",
        "--overscroll-history-navigation=0",
        "--start-fullscreen",
        "--disable-session-crashed-bubble",
        "--disable-restore-session-state",
        f"--user-data-dir={user_data_dir}",
        "--password-store=basic",
        "--check-for-update-interval=31536000",
        url,
    ]


class ChromeManager:
    def __init__(self) -> None:
        self.binary: Optional[Path] = find_chrome_binary()
        self.user_data_dir: Path = settings.chrome_user_data_path
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self._pid: Optional[int] = None
        self._marker = f"--user-data-dir={self.user_data_dir}"
        self._fallback_mode: bool = False

    def _matches_our_chrome(self, proc: psutil.Process) -> bool:
        try:
            cmdline = proc.cmdline()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
        return any(self._marker == arg or self._marker in arg for arg in cmdline)

    def _iter_our_chromes(self):
        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if "chrome" not in name:
                continue
            if self._matches_our_chrome(proc):
                yield proc

    def find_running(self) -> Optional[psutil.Process]:
        return next(iter(self._iter_our_chromes()), None)

    def is_running(self) -> bool:
        if self._fallback_mode:
            return True
        if self._pid is not None and psutil.pid_exists(self._pid):
            try:
                proc = psutil.Process(self._pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    return True
            except psutil.NoSuchProcess:
                pass
        proc = self.find_running()
        if proc is not None:
            self._pid = proc.pid
            return True
        return False

    def kill_existing(self) -> None:
        for proc in self._iter_our_chromes():
            try:
                proc.kill()
                log.info("Killed Chrome PID %s", proc.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def fix_session_crashed(self) -> None:
        """Evita el prompt 'Restore pages?' tras un crash anterior."""
        prefs = self.user_data_dir / "Default" / "Preferences"
        if not prefs.exists():
            return
        try:
            data = json.loads(prefs.read_text(encoding="utf-8"))
            data.setdefault("profile", {})
            data["profile"]["exit_type"] = "Normal"
            data["profile"]["exited_cleanly"] = True
            prefs.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            log.exception("No pude sanear Preferences de Chrome")

    def launch(self, url: str) -> bool:
        if self.binary is None:
            log.warning(
                "Chrome no encontrado. Abriendo %s con el navegador por defecto del sistema "
                "(modo degradado: sin kiosko, sin watchdog).",
                url,
            )
            try:
                webbrowser.open(url, new=1, autoraise=True)
                self._fallback_mode = True
                return True
            except Exception:
                log.exception("Falló apertura con navegador por defecto")
                return False
        self.fix_session_crashed()
        try:
            proc = subprocess.Popen(
                [str(self.binary), *kiosk_flags(url, self.user_data_dir)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            self._pid = proc.pid
            log.info("Chrome lanzado (PID %s) → %s", proc.pid, url)
            return True
        except Exception:
            log.exception("Falló lanzamiento de Chrome")
            return False

    def ensure_running(self, url: str) -> None:
        if not self.is_running():
            log.info("Chrome no detectado, relanzando…")
            self.launch(url)


chrome = ChromeManager()
