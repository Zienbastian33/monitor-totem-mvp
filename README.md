# RDx Totem MVP

Pequeña plataforma para tótems físicos Windows que muestran sitios web en kiosko, con panel remoto para supervisión.

## Qué hace

- Abre Chrome en pantalla completa apuntando a una URL configurable (por defecto `app.rdx.social`).
- Si Chrome se cae, lo relanza solo (watchdog).
- Toma screenshot del escritorio cada 10 minutos (monitor primario por defecto, configurable a `all` o un índice específico).
- Sirve un panel web para supervisar el tótem desde otra computadora vía ngrok.
- Se inicia automáticamente al boot de Windows.

## Stack

Python 3.12 · FastAPI · SQLite · Jinja2 · mss · psutil · APScheduler · ngrok

## Instalación rápida (Windows)

Desde PowerShell **como administrador** en la PC tótem:

```powershell
iwr https://raw.githubusercontent.com/zienbastian33/monitor-totem-mvp/main/ops/install.ps1 -OutFile install.ps1; .\install.ps1
```

El script:

1. Instala Python 3.12 (si falta) vía `winget`.
2. Descarga el código del repo.
3. Crea venv e instala dependencias.
4. Configura una Scheduled Task para auto-arranque al boot.
5. Configura Chrome con flags de kiosko + shortcut en Startup folder.
6. Instala ngrok (te pedirá tu auth token).
7. Inicia el servicio y muestra la URL pública.

## Desarrollo local (sin Windows / sin tótem real)

**Requiere Python 3.12 o 3.13** (Pillow todavía no tiene wheels prebuilt para 3.14).

```bash
# Linux / macOS
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

```powershell
# Windows (PowerShell o Git Bash)
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Visita http://localhost:8000.

> En Linux/macOS la captura de pantalla y el lanzamiento de Chrome funcionan, pero la integración completa (Scheduled Task, kiosko full) está pensada solo para Windows.

## Estructura

```
rdx-totem-mvp/
├── app/                  # código FastAPI
│   ├── main.py           # entrypoint
│   ├── config.py         # settings
│   ├── db.py             # SQLAlchemy + SQLite
│   ├── models.py         # Totem, Screenshot
│   ├── screenshots.py    # captura con mss + Pillow
│   ├── chrome_watchdog.py # detecta y relanza Chrome
│   ├── jobs.py           # tareas en background (APScheduler)
│   ├── ngrok_client.py   # consulta URL pública de ngrok
│   ├── routes/
│   │   ├── panel.py      # rutas HTML
│   │   └── api.py        # JSON
│   ├── templates/        # Jinja2
│   └── static/           # CSS
├── ops/
│   └── install.ps1       # instalador Windows
├── docs/
│   └── HOWTO.md          # operación día a día
├── requirements.txt
├── .env.example
└── README.md
```

## Operación

- **Panel local**: http://localhost:8000 (acceso desde la misma PC).
- **Panel remoto**: la URL pública de ngrok, mostrada en el panel local y en logs.
- **Logs**: `data/logs/rdx-totem.log`.
- **Datos**: `data/totems.db` + `data/screenshots/`.

## Limitaciones del MVP

- Diseñado para 1 tótem. La estructura permite N pero el panel todavía no orquesta múltiples.
- ngrok free: la URL pública cambia cada vez que reinicia ngrok (a menos que pagues plan fijo).
- Sin auth: cualquiera con la URL ngrok ve el panel. Mitigación: URL aleatoria es difícil de adivinar; no expongas datos sensibles en el panel.
- Multi-monitor soportado vía `SCREENSHOT_MONITOR` (`primary` | `all` | índice). Chrome siempre abre en el primario.

## Licencia

Privado / interno RioLab.
