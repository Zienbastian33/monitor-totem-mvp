# HOWTO — RDx Totem MVP

Manual práctico para instalar, operar y desinstalar el MVP en un tótem Windows.

## 0. Requisitos previos (una sola vez)

- PC Windows 10 u 11 con permisos de administrador.
- Acceso a internet (para descargar Python, ngrok y el código).
- Una cuenta gratuita en [ngrok.com](https://dashboard.ngrok.com/signup) — copiar el [auth token](https://dashboard.ngrok.com/get-started/your-authtoken).
- El repositorio público del MVP ya pusheado a tu GitHub (ej. `https://github.com/<tu-usuario>/rdx-totem-mvp`).

## 1. Primera instalación

Conéctate a la PC vía AnyDesk y abre **PowerShell como administrador** (clic derecho → "Ejecutar como administrador").

```powershell
iwr https://raw.githubusercontent.com/<tu-usuario>/rdx-totem-mvp/main/ops/install.ps1 -OutFile install.ps1
.\install.ps1 -GithubUser <tu-usuario>
```

El script:

1. Verifica winget.
2. Instala Python 3.12 si falta.
3. Instala ngrok si falta.
4. Descarga el ZIP del repo.
5. Crea `C:\rdx-totem-mvp\` con el código.
6. Crea `.venv` e instala dependencias.
7. Pide tu ngrok authtoken (lo configura).
8. Ajusta el plan de energía (sin sleep, pantalla siempre activa).
9. Crea la Scheduled Task `RDxTotem` (trigger: AtLogon, restart cada 1 min).
10. Inicia el servicio y muestra la URL pública de ngrok.

Al finalizar verás algo como:

```
URL local:   http://localhost:8000
URL pública: https://abcd1234.ngrok-free.app
```

Esa **URL pública** es la que abres desde tu laptop para ver el panel.

### Parámetros opcionales

```powershell
.\install.ps1 `
    -GithubUser tu-usuario `
    -KioskUrl https://app.rdx.center `
    -InstallDir "C:\rdx-totem-mvp" `
    -NgrokAuthToken "2abc..."
```

## 2. Configurar AutoLogon (auto-arranque tras corte de luz)

Sin AutoLogon, la PC al prenderse queda en pantalla de login y la Scheduled Task **no se dispara** (el trigger es "AtLogon"). Para que el tótem vuelva solo:

1. Descarga **Sysinternals AutoLogon**: <https://learn.microsoft.com/en-us/sysinternals/downloads/autologon>
2. Ejecútalo como administrador.
3. Ingresa usuario, dominio (vacío para cuenta local) y contraseña.
4. Click **Enable**.

Reinicia para verificar que entra solo. La Scheduled Task arranca al login → ngrok + FastAPI + Chrome kiosko.

> AutoLogon de Sysinternals encripta la contraseña en LSA secrets (no la deja en plano en el registro).

## 3. Operación día a día

| Acción | Comando |
|---|---|
| Detener servicio | `Stop-ScheduledTask -TaskName RDxTotem` |
| Iniciar servicio | `Start-ScheduledTask -TaskName RDxTotem` |
| Estado | `Get-ScheduledTask -TaskName RDxTotem \| Format-List` |
| Ver URL ngrok actual | Abre <http://localhost:4040> en la PC del tótem |
| Logs del servicio | `Get-Content C:\rdx-totem-mvp\data\logs\rdx-totem.log -Tail 50 -Wait` |
| Logs de ngrok | `Get-Content C:\rdx-totem-mvp\data\logs\ngrok.log -Tail 50 -Wait` |

Desde la URL pública ngrok ves el panel:

- `/` — grilla de tótems con thumbnail de la última captura.
- `/totems/<public_id>` — detalle del tótem con captura grande, últimas 24 h e histórico diario.

## 4. Cambiar la URL del kiosko

Editar `C:\rdx-totem-mvp\.env`:

```env
KIOSK_URL=https://otra-url.com
```

Reiniciar el servicio:

```powershell
Stop-ScheduledTask -TaskName RDxTotem
Start-ScheduledTask -TaskName RDxTotem
```

El servicio mata el Chrome existente y lanza uno nuevo apuntando a la nueva URL.

## 5. Actualizar a una nueva versión

Tras pushear cambios al repo:

```powershell
.\ops\install.ps1 -GithubUser <tu-usuario>
```

El script preserva `data/`, `.env` y `.venv` y solo reemplaza el código. Al final reinicia el servicio.

Si quieres reinstalar dependencias también:

```powershell
Remove-Item C:\rdx-totem-mvp\.venv -Recurse -Force
.\ops\install.ps1 -GithubUser <tu-usuario>
```

## 6. Desinstalar

```powershell
cd C:\rdx-totem-mvp
.\ops\uninstall.ps1                 # detiene tarea y procesos, conserva archivos
.\ops\uninstall.ps1 -RemoveFiles    # también borra C:\rdx-totem-mvp\
```

## 7. Troubleshooting

### El panel no abre por la URL pública de ngrok

- Verifica en la PC del tótem que ngrok corre: <http://localhost:4040>.
- Verifica que el authtoken esté configurado: `ngrok config check`.
- Reinicia: `Stop-ScheduledTask` → `Start-ScheduledTask`.

### Chrome no abre o se cierra solo

- Logs: `C:\rdx-totem-mvp\data\logs\rdx-totem.log` — busca líneas "Chrome".
- Verifica que Chrome esté instalado en alguna ruta estándar:
  - `C:\Program Files\Google\Chrome\Application\chrome.exe`
  - `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`
- Si está en otra ruta, edita `.env` con `CHROME_PATH=C:\ruta\a\chrome.exe`.
- El watchdog reintenta cada 30s, espera un minuto.

### El servicio dice "online" pero el panel marca offline

- El campo `last_heartbeat` se actualiza cada 10 min (en cada captura). Si el servicio está corriendo recién, espera al primer screenshot.

### Los screenshots se ven en negro

- Esto pasa cuando el servicio corre como SYSTEM en sesión 0 (no interactiva). Verifica que la Scheduled Task esté corriendo como tu usuario interactivo, no como SYSTEM:
  ```powershell
  Get-ScheduledTask -TaskName RDxTotem | Select-Object -ExpandProperty Principal
  ```
  Debe mostrar `LogonType: Interactive` y tu `UserId`.

### Quiero exponer el panel en una URL fija (no la random de ngrok)

ngrok free regenera la URL en cada reinicio. Opciones:

- Plan ngrok pago ($8/mes) — URL estable.
- Migrar a **Cloudflare Tunnel** (gratis pero requiere dominio).
- Migrar a **Tailscale** — IP `100.x.x.x` estable, sin URL pública.

Cualquiera de las tres es trivial cambiar después; el servicio sigue escuchando en `localhost:8000`.

### Necesito ver qué está pasando en vivo

```powershell
# Logs en vivo
Get-Content C:\rdx-totem-mvp\data\logs\rdx-totem.log -Tail 50 -Wait

# Procesos
Get-Process | Where-Object { $_.Name -in @("python","ngrok","chrome") }

# Estado de la tarea
Get-ScheduledTaskInfo -TaskName RDxTotem
```

## 8. Limitaciones conocidas (MVP)

- **1 solo tótem** por instalación. La estructura permite N pero el panel todavía está pensado para 1.
- **ngrok free** rota la URL pública en cada reinicio.
- **Sin auth en el panel** — la única protección es que la URL ngrok es difícil de adivinar.
- **Solo monitor primario** — multi-monitor pendiente.
- **Auto-resume tras corte de luz** depende de AutoLogon configurado (paso 2).
