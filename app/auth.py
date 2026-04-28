import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import settings

_security = HTTPBasic(auto_error=False)
_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": 'Basic realm="RDx Totem"'}


def require_auth(creds: HTTPBasicCredentials | None = Depends(_security)) -> None:
    """Dependencia FastAPI: 401 si PANEL_PASSWORD está set y las creds no calzan.

    Si PANEL_PASSWORD está vacío, no se exige nada (modo dev abierto).
    """
    if not settings.panel_password:
        return
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth required",
            headers=_UNAUTHORIZED_HEADERS,
        )
    user_ok = secrets.compare_digest(creds.username, settings.panel_username)
    pass_ok = secrets.compare_digest(creds.password, settings.panel_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers=_UNAUTHORIZED_HEADERS,
        )
