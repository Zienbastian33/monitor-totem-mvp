# RDx Totem MVP — Arquitectura y operación

> Documento integral del MVP. Describe el flujo de la app, el modelo de datos,
> los procesos que corren en la PC tótem, los requisitos de hardware/SO, y
> cómo encajan todas las piezas. Pensado para que cualquiera (humano o agente)
> que llegue al repo pueda operarlo sin haber leído el código antes.

**Versión del documento:** 2026-04-27.
**Stack:** Python 3.12 / FastAPI / SQLite / Jinja2 / mss / Pillow / psutil / APScheduler / ngrok / Tailwind CDN v3.

---

## 1. ¿Qué es esto?

Una aplicación que se instala en una PC con Windows ("tótem") y hace tres cosas:

1. **Abre Chrome en pantalla completa** apuntando a una URL configurable (por defecto `https://app.rdx.social`). Si Chrome se cae o se cierra, lo relanza solo.
2. **Toma screenshots periódicos del escritorio** y los archiva en disco.
3. **Sirve un panel web** con la última captura, histórico de las últimas 24 h, archivo histórico (1 por día), y stats de salud. El panel se expone vía ngrok para que se pueda monitorear desde otra computadora o el celular.

El MVP está pensado para **un solo tótem por instalación**. La estructura del DB soporta N, pero el panel todavía no orquesta múltiples.

---

## 2. Procesos que corren en el tótem

Tras una instalación exitosa, hay **tres procesos** simultáneos en la PC:

| Proceso | Lanzado por | Qué hace |
|---|---|---|
| `python.exe -m app.main` | Scheduled Task `RDxTotem` (al login) → `ops\run.ps1` | Servidor FastAPI + scheduler de jobs |
| `chrome.exe` (con `--user-data-dir=...\chrome-profile`) | Hijo de python, vía `ChromeManager.launch()` | Kiosko mostrando la URL |
| `ngrok.exe` | Hijo de PowerShell, vía `ops\run.ps1` | Túnel público hacia `localhost:8000` |

Cualquier `chrome.exe` que **NO** tenga el flag `--user-data-dir=...\chrome-profile` no es nuestro y la app lo ignora. Esto permite usar Chrome normal en paralelo si la PC es compartida (no recomendado para producción).

---

## 3. Flujo de arranque (boot → operación)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Windows Boot                                                       │
└──────┬──────────────────────────────────────────────────────────────┘
       │
       │ AutoLogon (Sysinternals) auto-loguea al usuario configurado
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Logon de Windows                                                   │
└──────┬──────────────────────────────────────────────────────────────┘
       │
       │ Trigger AtLogOn dispara la Scheduled Task "RDxTotem"
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PowerShell: ops\run.ps1                                            │
│   1. mata ngrok zombies de corridas anteriores                      │
│   2. lee PORT del .env                                              │
│   3. lanza ngrok detached → bind a localhost:<port>                 │
│   4. invoca .venv\Scripts\python.exe -m app.main                    │
│   5. propaga el exit code de python al cerrar (para RestartInterval)│
└──────┬──────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  python -m app.main → app.main.create_app() → uvicorn               │
│                                                                     │
│  FastAPI lifespan startup:                                          │
│   1. setup_logging() — handlers a rdx-totem.log + stdout            │
│   2. keep_awake() — Win32 SetThreadExecutionState                   │
│      (sin sleep ni blanqueo de pantalla mientras viva el proceso)   │
│   3. init_db() — crea tablas si no existen                          │
│   4. ensure_local_totem() — registra/actualiza fila Totem por host  │
│   5. chrome.kill_existing() — mata Chromes viejos del kiosko        │
│   6. chrome.launch(KIOSK_URL) — abre Chrome en --kiosk              │
│   7. build_scheduler().start() — APScheduler en background          │
└──────┬──────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Estado estable (3 procesos vivos: python, chrome, ngrok)           │
│                                                                     │
│  Loops periódicos:                                                  │
│    every  30s  watchdog_job  → relanza Chrome si murió              │
│    every 900s  screenshot_job→ captura, comprime, persiste, latido  │
│    every 3600s retention_job → borra > 24h, guarda 1/día como arch  │
└─────────────────────────────────────────────────────────────────────┘
```

Si python crashea, `run.ps1` termina con exit code != 0, la Scheduled Task aplica `RestartInterval = 1 min` y vuelve a disparar el ciclo. Si Chrome se cierra, el watchdog lo detecta dentro de 30 s y lo relanza.

---

## 4. Modelo de datos (SQLite)

Archivo: `data\totems.db`. Engine SQLAlchemy 2.0 con WAL mode, foreign keys ON, sync NORMAL.

### 4.1. Tabla `totems`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | autoincrement |
| `public_id` | VARCHAR(64) UNIQUE INDEX | derivado del hostname (`<slug>-<uuid5_8>`) — estable entre reinicios |
| `name` | VARCHAR(120) | display name (default = hostname) |
| `hostname` | VARCHAR(120) | `socket.gethostname()` al primer registro |
| `location` | VARCHAR(120) | string libre desde `.env`, ej. "Recepción Las Condes" |
| `last_heartbeat` | TIMESTAMP (UTC, tz-aware) | actualizado en cada `screenshot_job` exitoso |
| `created_at` | TIMESTAMP (UTC, tz-aware) | al primer registro |

Cada PC tótem se registra una sola vez (la primera vez que arranca), y la misma entrada se reutiliza en todas las corridas siguientes (lookup por `public_id`).

### 4.2. Tabla `screenshots`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | autoincrement |
| `totem_id` | INTEGER FK → totems.id ON DELETE CASCADE, INDEX | |
| `path` | VARCHAR(500) | relativo a `data/screenshots/`, formato `YYYY-MM-DD/HH-MM-SS.jpg` |
| `width` | INTEGER | después del downscale (max 1920) |
| `height` | INTEGER | proporcional |
| `bytes` | INTEGER | tamaño del archivo full (no incluye thumb) |
| `is_archive` | BOOLEAN INDEX | `false` = capturas de las últimas 24 h; `true` = una por día, conservada |
| `taken_at` | TIMESTAMP (UTC, tz-aware) INDEX | |

### 4.3. Relación

```
totems (1) ───────< (N) screenshots
                 ON DELETE CASCADE
```

Borrar el tótem borra todos sus screenshots. En la práctica nunca se borra un tótem.

### 4.4. Archivos físicos asociados

Cada fila `screenshots` corresponde a **dos** archivos en disco:

```
data/screenshots/2026-04-27/14-30-00.jpg        ← full (≤1920w, q=75)
data/screenshots/2026-04-27/14-30-00.thumb.jpg  ← 480w, q=60 (~6× más liviano)
```

El thumb no se persiste en DB; se deriva del path full vía el filtro Jinja `screenshot_thumb`. Si el thumb no existe (capturas legacy pre-migración), el filtro cae al full transparentemente.

---

## 5. Flujo de un screenshot (cada 15 minutos)

```
APScheduler dispara screenshot_job
  └─> ensure_local_totem(db) — recupera fila Totem
  └─> save_screenshot(db, totem.id):
        ├─ mss.grab(monitor)         según SCREENSHOT_MONITOR
        ├─ Image.frombytes(...)      bgra → RGB
        ├─ resize si width > 1920
        ├─ save full     → data/screenshots/YYYY-MM-DD/HH-MM-SS.jpg
        ├─ resize a 480w
        ├─ save thumb    → data/screenshots/YYYY-MM-DD/HH-MM-SS.thumb.jpg
        └─ INSERT screenshots (path, width, height, bytes, taken_at)
  └─> touch_heartbeat(db, totem.id)  — UPDATE totem.last_heartbeat = now()
```

`last_heartbeat` se actualiza **solo cuando un screenshot se persiste con éxito**. Si la captura falla 3 veces seguidas (15 × 3 = 45 min), el panel marcará el tótem como `offline` (umbral configurable vía `OFFLINE_THRESHOLD_SECONDS`).

---

## 6. Retención y limpieza (cada hora)

`retention_job` corre cada `RETENTION_INTERVAL_SECONDS` (default 3600s).

Lógica:
- Calcula cutoff = `now() - RETENTION_HOURS_FULL` (default 24 h).
- Selecciona screenshots con `taken_at < cutoff AND is_archive = false`.
- Por cada uno:
  - Si `KEEP_DAILY_ARCHIVE=true` y aún no hay un archive de ese día → marca este como `is_archive=true`. Sobrevive.
  - Si ya hay archive del día → borra `.jpg` + `.thumb.jpg` + fila DB.

Resultado en estado estable: las últimas 24 h en detalle (96 capturas a 15 min/u) + una por día indefinidamente.

---

## 7. Endpoints

### Públicos (sin auth)

- `GET /api/health` → `{"status":"ok","ts":"<iso8601>"}`. Para load balancers / monitoring externo.
- `GET /static/...` → assets estáticos (logos, CSS si lo hubiera).

### Autenticados (HTTP Basic, controlado por `PANEL_PASSWORD`)

- `GET /` — index del panel (lista de tótems).
- `GET /totems/<public_id>` — detalle de un tótem.
- `GET /screenshots/<path>` — sirve un JPEG (full o thumb), con guard de path-traversal.
- `GET /api/status` — JSON estructurado equivalente al index.

Si `PANEL_PASSWORD=` está vacío en `.env`, **no se exige auth en ningún endpoint** (modo dev). Esto se decide por request, en runtime — cambiar el `.env` y reiniciar la tarea aplica el cambio.

---

## 8. Configuración (`.env`)

Toda la configuración vive en `C:\rdx-totem-mvp\.env`. Se lee una vez al arrancar python; cambios requieren `Restart-ScheduledTask -TaskName RDxTotem` (en realidad un Stop + Start).

> ⚠️ **Regla**: NUNCA usar comentarios inline (`VAR=valor # comentario`). pydantic-settings no los strippea y rompe el parseo. Comentarios siempre en su propia línea encima de la variable. Esto rompió la primera instalación del MVP.

Variables clave (resumen — la lista completa está en `.env.example`):

| Variable | Default | Significado |
|---|---|---|
| `KIOSK_URL` | `https://app.rdx.social` | Lo que muestra Chrome |
| `SCREENSHOT_INTERVAL_SECONDS` | `900` | 15 min entre capturas |
| `SCREENSHOT_MONITOR` | `primary` | `primary` \| `all` \| `1`/`2`/... |
| `OFFLINE_THRESHOLD_SECONDS` | `900` | Sin heartbeat por > esto = offline |
| `RETENTION_HOURS_FULL` | `24` | Ventana móvil de detalle completo |
| `KEEP_DAILY_ARCHIVE` | `true` | Conservar 1 captura por día |
| `PANEL_USERNAME` | `admin` | Usuario para HTTP Basic |
| `PANEL_PASSWORD` | (vacío) | Password compartido. Vacío = panel abierto |
| `DISPLAY_TIMEZONE` | `America/Santiago` | Solo afecta render del panel |
| `DATA_DIR` | (vacío = `./data`) | Override de carpeta de datos |
| `CHROME_PATH` | (vacío = autodetect) | Override de ruta a chrome.exe |

---

## 9. Estructura de archivos (post-instalación)

```
C:\rdx-totem-mvp\
├── app\                          (código Python)
│   ├── main.py                   entrypoint + lifespan
│   ├── config.py                 settings (pydantic-settings)
│   ├── db.py                     SQLAlchemy engine + session_scope
│   ├── models.py                 Totem, Screenshot
│   ├── auth.py                   HTTP Basic dependency
│   ├── power.py                  keep_awake() Win32
│   ├── disk_usage.py             scan cacheado de data/screenshots
│   ├── chrome_watchdog.py        ChromeManager (lanza/detecta/relanza)
│   ├── screenshots.py            captura + thumb
│   ├── jobs.py                   APScheduler jobs
│   ├── filters.py                filtros Jinja (timestamps, humanbytes, thumb)
│   ├── ngrok_client.py           consulta localhost:4040 para URL pública
│   ├── totem_registry.py         ensure_local_totem, touch_heartbeat
│   ├── routes\
│   │   ├── panel.py              rutas HTML + /screenshots auth-gated
│   │   └── api.py                /api/health (público) + /api/status (auth)
│   ├── templates\
│   │   ├── base.html             header + footer (RDx DS)
│   │   ├── index.html            grid de tótems + 4 stat cards
│   │   ├── totem_detail.html     captura grande + grids 24h + archivo
│   │   └── _status_pill.html     pill semántica (green/red/gray)
│   └── static\
│       └── images\               logos PNG (RDx + byRiolab)
├── ops\
│   ├── install.ps1               instalador one-shot
│   ├── run.ps1                   wrapper de la Scheduled Task
│   └── uninstall.ps1             limpieza
├── docs\
│   ├── HOWTO.md                  manual operativo
│   ├── ARCHITECTURE.md           ESTE archivo
│   └── DESIGN_SYSTEM.md          referencia visual RDx
├── data\                         (creado en runtime, en .gitignore)
│   ├── totems.db                 SQLite + WAL files
│   ├── screenshots\YYYY-MM-DD\   JPG + thumb por captura
│   ├── chrome-profile\           perfil aislado del Chrome del kiosko
│   └── logs\
│       ├── rdx-totem.log         (rotating, 5MB × 3)
│       ├── ngrok.log
│       ├── ngrok-err.log
│       └── app-stderr.log        crashes import-time de python
├── .venv\                        entorno virtual Python 3.12
├── .env                          configuración de runtime
├── .env.example                  template
├── requirements.txt
├── README.md
└── ...
```

---

## 10. Requisitos de la PC tótem (PC 2)

### Hardware (mínimos)

- CPU: cualquier x64 dual-core moderno. El consumo es bajo (mss + Pillow + uvicorn idle es ~50 MB RAM).
- RAM: 4 GB. Chrome es el componente más pesado (~300-500 MB para una pestaña).
- Disco: 5 GB libres garantizan ~1 año de operación holgada (cada captura full pesa ~80 KB, el thumb ~12 KB; 96/día × 92 KB ≈ 9 MB/día sin retención; con retención el archive a 1/día crece ~92 KB/día).
- 1 monitor mínimo. Multi-monitor soportado para captura (`SCREENSHOT_MONITOR=all` o índice).
- Conexión a internet (para Chrome, ngrok).

### Software

| Componente | Versión | Cómo se instala |
|---|---|---|
| Windows | 10 o 11 | preinstalado |
| PowerShell | 5.1+ (incluido) | preinstalado |
| `winget` | App Installer reciente | preinstalado en W10 ≥ 1709 / W11 |
| Python | **3.12 o 3.13 estrictamente** | `winget install Python.Python.3.12` (lo hace el installer) |
| ngrok | cualquier reciente | `winget install Ngrok.Ngrok` (lo hace el installer) |
| Google Chrome | reciente | usuario lo instala antes (no automatizado) |
| Sysinternals AutoLogon | opcional pero recomendado | descarga manual desde Microsoft |

> **Por qué Python 3.12/3.13 y no 3.14**: Pillow no tiene wheels prebuilt para 3.14 al momento de escribir este doc. El installer rechaza versiones fuera de 3.12-3.13.

### Permisos

- El instalador requiere PowerShell como **administrador** (manipula Scheduled Tasks, registro de power plan, instala paquetes con winget).
- La Scheduled Task corre como **el usuario interactivo** (no SYSTEM), porque mss necesita una sesión interactiva real para capturar el escritorio. SYSTEM/sesión 0 captura screens negras.

### Configuración de Windows recomendada

Hecho automáticamente por `install.ps1`:
- Power plan: nunca dormir, nunca apagar pantalla, nunca hibernar (AC y batería).
- Scheduled Task con `AtLogOn` + `RestartInterval 1 min` + `RestartCount 999`.

Hecho automáticamente por la app (en runtime):
- `SetThreadExecutionState(ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED)` evita el bloqueo del display y el sleep del sistema mientras python esté vivo.

Hecho **a mano** por el operador (una sola vez):
- **Sysinternals AutoLogon**: imprescindible para auto-recuperación tras corte de luz. Sin esto la PC bootea a la pantalla de login y nada arranca.
- **Deshabilitar screensaver**: si la cuenta tiene un screensaver con "Al reanudar mostrar pantalla de inicio de sesión", Windows ignora el flag de keep-awake y bloquea igual.

---

## 11. Operación día a día

| Acción | Comando |
|---|---|
| Estado del servicio | `Get-ScheduledTask -TaskName RDxTotem \| Format-List` |
| Detener (vuelve al próximo login) | `Stop-ScheduledTask -TaskName RDxTotem` |
| Iniciar | `Start-ScheduledTask -TaskName RDxTotem` |
| Reiniciar (post .env edit) | `Stop-ScheduledTask -TaskName RDxTotem; Start-ScheduledTask -TaskName RDxTotem` |
| **Pausar permanente** (sobrevive reboots) | `Disable-ScheduledTask -TaskName RDxTotem` + `Stop-ScheduledTask -TaskName RDxTotem` |
| **Reanudar permanente** | `Enable-ScheduledTask -TaskName RDxTotem; Start-ScheduledTask -TaskName RDxTotem` |
| URL pública actual | abrir `http://localhost:4040` |
| Tail logs app | `Get-Content C:\rdx-totem-mvp\data\logs\rdx-totem.log -Tail 50 -Wait` |
| Tail logs ngrok | `Get-Content C:\rdx-totem-mvp\data\logs\ngrok.log -Tail 50 -Wait` |
| Crashes import-time | `Get-Content C:\rdx-totem-mvp\data\logs\app-stderr.log -Tail 50` |
| Procesos del MVP | `Get-Process python,ngrok,chrome -ErrorAction SilentlyContinue` |

### Matar todo (force stop sin desinstalar)

```powershell
Stop-ScheduledTask -TaskName RDxTotem -ErrorAction SilentlyContinue
Get-Process -Name "python","ngrok" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name "chrome" -ErrorAction SilentlyContinue | Where-Object {
  $_.Path -like "*\rdx-totem-mvp\data\chrome-profile*" -or
  ($_.MainModule.ModuleName -eq "chrome.exe" -and $_.CommandLine -like "*chrome-profile*")
} | Stop-Process -Force
```

> Nota: `MainModule.CommandLine` puede dar `AccessDenied` para procesos de otro nivel de integridad. La forma robusta de matar **solo** el Chrome del kiosko es por su flag `--user-data-dir` en cmdline, lo cual no es trivial sin `psutil` o WMI. La aproximación "matar todos los chromes" es destructiva pero efectiva si la PC es solo para tótem.

### Desinstalar

```powershell
cd C:\rdx-totem-mvp
.\ops\uninstall.ps1                    # tarea + procesos, deja la carpeta y data\
.\ops\uninstall.ps1 -RemoveFiles       # también borra C:\rdx-totem-mvp\
```

---

## 12. Modelo de fallas

| Síntoma | Causa típica | Diagnóstico | Fix |
|---|---|---|---|
| Panel devuelve 500 al abrir `/` | Bug en route o DB rota | `Get-Content ...\rdx-totem.log` | depende — ahora todos los tracebacks van al log |
| `rdx-totem.log` no existe | python crashea durante import | `Get-Content ...\app-stderr.log` | leer el traceback ahí |
| URL pública no aparece en el panel | ngrok no levantó | `Get-Content ...\ngrok.log`, abrir `http://localhost:4040` | verificar authtoken con `ngrok config check` |
| Status del tótem = "offline" | sin heartbeat hace > 15 min | logs de `screenshot_job` | revisar permisos de captura, monitor disponible |
| Screenshots negros | Task corre como SYSTEM (no Interactive) | `Get-ScheduledTask -TaskName RDxTotem \| Select-Object -ExpandProperty Principal` | recrear con `LogonType: Interactive` |
| Display se sigue bloqueando | screensaver con "Al reanudar mostrar logon" activo | Settings → Lock screen → Screensaver | deshabilitar |
| Chrome muestra "Restaurar páginas" cada vez | crash sin shutdown limpio | logs | `ChromeManager.fix_session_crashed()` lo previene; si persiste, borrar `data\chrome-profile\Default\Preferences` |
| Re-instalación pierde configuración | borrar `.env` por error | -- | `install.ps1` preserva `data/`, `.env`, `.venv`. Si los borraste, restorear desde backup |

---

## 13. Decisiones de diseño que parecen raras pero tienen una razón

- **SQLite + WAL en lugar de Postgres**: el MVP corre offline en una PC, no necesita servidor. WAL evita locks durante reads concurrentes (panel + screenshot job).
- **`/screenshots` con `FileResponse` en lugar de `StaticFiles` mount**: para poder gatear las imágenes con la misma auth basic del panel. Pierdes sendfile pero los JPEGs son chicos (≤200 KB).
- **Identidad del tótem derivada del hostname**: estable entre reinicios, sin necesidad de un ID generado y persistido. El precio es que cambiar el hostname genera un Totem fantasma nuevo.
- **`SetThreadExecutionState` en lugar de mover el mouse fake**: limpio, soportado por Win32, no requiere permisos extra. Solo funciona mientras el proceso vive — al matar python, Windows recupera el control normal del display sleep.
- **ngrok manejado fuera de FastAPI** (en `run.ps1`): el ciclo de vida del túnel es independiente del servidor. Si reiniciamos uvicorn pero ngrok sigue, el túnel mantiene la URL.
- **Thumbs no persistidos en DB**: derivar el path es trivial (`screenshot_thumb` filter); persistirlos invitaría a que el filesystem y el DB se desincronicen. La caída a full si el thumb no existe cubre el caso legacy sin código de migración.
