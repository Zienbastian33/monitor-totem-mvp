import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import require_auth
from .chrome_watchdog import chrome
from .config import settings
from .db import init_db, session_scope
from .filters import register_filters
from .jobs import build_scheduler
from .power import keep_awake
from .routes import api as api_routes
from .routes import panel
from .totem_registry import ensure_local_totem

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def setup_logging() -> None:
    settings.logs_path.mkdir(parents=True, exist_ok=True)
    log_file = settings.logs_path / "rdx-totem.log"

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    stream_handler = logging.StreamHandler()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=[stream_handler, file_handler],
    )
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Uvicorn's own loggers don't propagate to root by default, so attach our
    # handlers directly so 500 tracebacks land in rdx-totem.log.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = [stream_handler, file_handler]
        uv_logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    log = logging.getLogger("rdx-totem")
    log.info("Iniciando RDx Totem MVP")

    keep_awake()

    init_db()

    with session_scope() as db:
        totem = ensure_local_totem(db)
        log.info("Tótem local registrado: %s (%s)", totem.public_id, totem.name)

    chrome.kill_existing()
    chrome.launch(settings.kiosk_url)

    scheduler = build_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    log.info(
        "Scheduler iniciado · screenshot=%ds · watchdog=%ds · retention=%ds",
        settings.screenshot_interval_seconds,
        settings.watchdog_interval_seconds,
        settings.retention_interval_seconds,
    )

    try:
        yield
    finally:
        log.info("Apagando RDx Totem MVP")
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    settings.data_path.mkdir(parents=True, exist_ok=True)
    settings.screenshots_path.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="RDx Totem MVP", version="0.1.0", lifespan=lifespan)

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    register_filters(templates.env)
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(api_routes.public_router, prefix="/api")
    app.include_router(panel.router, dependencies=[Depends(require_auth)])
    app.include_router(api_routes.router, prefix="/api", dependencies=[Depends(require_auth)])

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
