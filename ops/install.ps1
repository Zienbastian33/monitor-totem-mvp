<#
.SYNOPSIS
    Instala el MVP de RDx Totem en una PC Windows.

.DESCRIPTION
    Pasos:
      1. Verifica permisos de administrador y winget.
      2. Instala Python 3.12 y ngrok vía winget si faltan.
      3. Descarga el proyecto desde GitHub (ZIP).
      4. Crea entorno virtual e instala dependencias.
      5. Configura .env con la URL kiosko.
      6. Configura ngrok auth token.
      7. Ajusta plan de energía (sin sleep, pantalla siempre encendida).
      8. Crea Scheduled Task que se dispara al logon.
      9. Inicia el servicio y muestra la URL pública de ngrok.

    Para auto-arranque tras corte de luz, AutoLogon debe configurarse
    manualmente con Sysinternals AutoLogon (link al final del script).

.PARAMETER GithubUser
    Usuario de GitHub donde está alojado el repo.
    Si dejas el placeholder, debes pasar -GithubUser <tu-usuario>.

.PARAMETER RepoName
    Nombre del repositorio. Default: monitor-totem-mvp

.PARAMETER Branch
    Rama a descargar. Default: main

.PARAMETER InstallDir
    Carpeta de instalación. Default: C:\rdx-totem-mvp

.PARAMETER KioskUrl
    URL que el tótem mostrará en Chrome kiosko. Default: https://app.rdx.center

.PARAMETER NgrokAuthToken
    Auth token de ngrok. Si no se pasa, lo pide interactivamente.

.PARAMETER PanelUsername
    Usuario para HTTP Basic auth del panel. Default: admin.

.PARAMETER PanelPassword
    Password compartido para el panel. Vacío = panel abierto (modo dev).
    Recomendado al exponer por ngrok.

.EXAMPLE
    .\install.ps1 -GithubUser bastian
    .\install.ps1 -GithubUser bastian -KioskUrl https://otra.com -NgrokAuthToken 2abc...
    .\install.ps1 -KioskUrl https://app.rdx.social -NgrokAuthToken 2abc... -PanelPassword "S3cret-Pass"
#>

#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$GithubUser = "zienbastian33",
    [string]$RepoName = "monitor-totem-mvp",
    [string]$Branch = "main",
    [string]$InstallDir = "C:\rdx-totem-mvp",
    [string]$KioskUrl = "https://app.rdx.social",
    [string]$NgrokAuthToken = "",
    [string]$PanelUsername = "admin",
    [string]$PanelPassword = ""
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host ""
    Write-Host "→ $msg" -ForegroundColor Cyan
}
function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Test-CmdAvail($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}
function Refresh-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

# --- Banner ---
Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "  RDx Totem MVP -- Instalacion Windows"          -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan

# --- Validaciones ---
$RepoUrl = "https://github.com/$GithubUser/$RepoName"
$ZipUrl  = "$RepoUrl/archive/refs/heads/$Branch.zip"

# --- 1. winget ---
Write-Step "Verificando winget"
if (-not (Test-CmdAvail "winget")) {
    Write-Host "winget no esta disponible. Instala 'App Installer' desde Microsoft Store." -ForegroundColor Red
    exit 1
}
Write-Ok "winget disponible"

# --- 2. Python 3.12 o 3.13 ---
# Forzamos 3.12 o 3.13. Python 3.14 rompe librerías con C extensions
# (ej. Pillow no tiene wheels prebuilt todavía).
Write-Step "Verificando Python 3.12 o 3.13"
$pythonExe = $null

function Resolve-PythonExe {
    param([string]$Cmd, [string[]]$ArgsBefore = @())
    try {
        $invoke = @($Cmd) + $ArgsBefore + @("-c", "import sys; print(sys.executable)")
        $exe = & $invoke[0] $invoke[1..($invoke.Length - 1)] 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) {
            $exe = $exe.Trim()
            if (Test-Path $exe) { return $exe }
        }
    } catch {}
    return $null
}

# Probar py launcher con versión explícita
foreach ($ver in @("3.12", "3.13")) {
    if (Test-CmdAvail "py") {
        $exe = Resolve-PythonExe -Cmd "py" -ArgsBefore @("-$ver")
        if ($exe) {
            $pythonExe = $exe
            Write-Ok "Python $ver encontrado: $exe"
            break
        }
    }
}

# Fallback: python / python3 en PATH si tienen 3.12 o 3.13
if (-not $pythonExe) {
    foreach ($candidate in @("python", "python3")) {
        if (Test-CmdAvail $candidate) {
            try {
                $version = & $candidate -V 2>&1
                if ($version -match "Python 3\.(12|13)") {
                    $exe = Resolve-PythonExe -Cmd $candidate
                    if ($exe) {
                        $pythonExe = $exe
                        Write-Ok "Python encontrado: $version ($exe)"
                        break
                    }
                }
            } catch {}
        }
    }
}

# No hay 3.12/3.13 → instalar 3.12
if (-not $pythonExe) {
    Write-Host "  Instalando Python 3.12 via winget..."
    winget install --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements | Out-Null
    Refresh-Path
    Start-Sleep -Seconds 2

    if (Test-CmdAvail "py") {
        $pythonExe = Resolve-PythonExe -Cmd "py" -ArgsBefore @("-3.12")
    }

    if (-not $pythonExe) {
        Write-Host "Python instalado pero no detectado en PATH. Reinicia PowerShell y reintenta." -ForegroundColor Red
        exit 1
    }
    Write-Ok "Python 3.12 instalado: $pythonExe"
}

# --- 3. ngrok ---
Write-Step "Verificando ngrok"
if (-not (Test-CmdAvail "ngrok")) {
    Write-Host "  Instalando ngrok via winget..."
    winget install --id Ngrok.Ngrok --silent --accept-source-agreements --accept-package-agreements | Out-Null
    Refresh-Path
    if (-not (Test-CmdAvail "ngrok")) {
        Write-Warn "ngrok instalado pero no detectado. Reinicia PowerShell y reintenta."
        exit 1
    }
}
Write-Ok "ngrok disponible"

# --- 4. Descargar codigo ---
Write-Step "Descargando codigo desde $RepoUrl ($Branch)"
$tempZip     = Join-Path $env:TEMP "rdx-totem-mvp.zip"
$tempExtract = Join-Path $env:TEMP "rdx-totem-extract"
if (Test-Path $tempZip)     { Remove-Item $tempZip -Force }
if (Test-Path $tempExtract) { Remove-Item $tempExtract -Recurse -Force }

try {
    Invoke-WebRequest -Uri $ZipUrl -OutFile $tempZip -UseBasicParsing
} catch {
    Write-Host "Falle bajando $ZipUrl. Revisa que el repo sea publico y exista la rama $Branch." -ForegroundColor Red
    Write-Host "Detalle: $_" -ForegroundColor Red
    exit 1
}
Write-Ok "ZIP descargado"

Expand-Archive -Path $tempZip -DestinationPath $tempExtract -Force
$extracted = Get-ChildItem $tempExtract | Where-Object { $_.PSIsContainer } | Select-Object -First 1
if (-not $extracted) {
    Write-Host "El ZIP no tiene la estructura esperada." -ForegroundColor Red
    exit 1
}

if (Test-Path $InstallDir) {
    Write-Warn "Carpeta $InstallDir ya existe. Conservando data/, .env y .venv; reemplazando codigo."
    Get-ChildItem $InstallDir -Force | Where-Object { $_.Name -notin @("data", ".env", ".venv") } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
} else {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

Get-ChildItem $extracted.FullName -Force | Copy-Item -Destination $InstallDir -Recurse -Force
Remove-Item $tempZip, $tempExtract -Recurse -Force -ErrorAction SilentlyContinue
Write-Ok "Codigo copiado a $InstallDir"

# --- 5. venv + dependencias ---
Write-Step "Creando entorno virtual"
$venvDir    = Join-Path $InstallDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip    = Join-Path $venvDir "Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    & $pythonExe -m venv $venvDir
}
Write-Ok "venv listo"

Write-Step "Instalando dependencias Python"
& $venvPython -m pip install --upgrade pip --quiet
& $venvPip install -r (Join-Path $InstallDir "requirements.txt") --quiet
Write-Ok "Dependencias instaladas"

# --- 6. .env ---
Write-Step "Configurando .env"
$envPath = Join-Path $InstallDir ".env"
if (-not (Test-Path $envPath)) {
    Copy-Item (Join-Path $InstallDir ".env.example") $envPath
    $content = Get-Content $envPath
    $content = $content -replace "^KIOSK_URL=.*", "KIOSK_URL=$KioskUrl"
    $content = $content -replace "^PANEL_USERNAME=.*", "PANEL_USERNAME=$PanelUsername"
    $content = $content -replace "^PANEL_PASSWORD=.*", "PANEL_PASSWORD=$PanelPassword"
    $content | Set-Content $envPath -Encoding utf8
    if ($PanelPassword) {
        Write-Ok ".env creado con KIOSK_URL=$KioskUrl + auth (user=$PanelUsername)"
    } else {
        Write-Ok ".env creado con KIOSK_URL=$KioskUrl"
        Write-Warn "PANEL_PASSWORD vacio: panel queda ABIERTO. Editar $envPath y reiniciar tarea para activar auth."
    }
} else {
    Write-Ok ".env existente conservado (no se sobreescriben credenciales)"
}

# --- 7. ngrok auth token ---
Write-Step "Configurando ngrok auth token"
if (-not $NgrokAuthToken) {
    Write-Host ""
    Write-Host "  Necesitas un auth token gratuito de ngrok:" -ForegroundColor Yellow
    Write-Host "    https://dashboard.ngrok.com/get-started/your-authtoken"
    Write-Host ""
    $NgrokAuthToken = Read-Host "  Pega tu authtoken (ENTER para configurar despues)"
}
if ($NgrokAuthToken) {
    & ngrok config add-authtoken $NgrokAuthToken | Out-Null
    Write-Ok "ngrok configurado"
} else {
    Write-Warn "Sin authtoken. Configuralo despues con: ngrok config add-authtoken <token>"
}

# --- 8. Power Plan ---
Write-Step "Ajustando plan de energia (sin sleep, pantalla siempre activa)"
try {
    powercfg -change -standby-timeout-ac 0 | Out-Null
    powercfg -change -standby-timeout-dc 0 | Out-Null
    powercfg -change -monitor-timeout-ac 0 | Out-Null
    powercfg -change -monitor-timeout-dc 0 | Out-Null
    powercfg -change -hibernate-timeout-ac 0 | Out-Null
    powercfg -change -hibernate-timeout-dc 0 | Out-Null
    Write-Ok "Power plan ajustado"
} catch {
    Write-Warn "No pude ajustar power plan: $_"
}

# --- 9. Scheduled Task ---
Write-Step "Creando Scheduled Task 'RDxTotem'"
$taskName  = "RDxTotem"
$runScript = Join-Path $InstallDir "ops\run.ps1"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runScript`"" `
    -WorkingDirectory $InstallDir

$trigger = New-ScheduledTaskTrigger -AtLogOn

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "RDx Totem MVP -- servicio FastAPI + ngrok + Chrome kiosko" | Out-Null

Write-Ok "Scheduled Task '$taskName' creado (trigger: AtLogOn, restart c/1min)"

# --- 10. Iniciar ahora ---
Write-Step "Iniciando servicio"
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 5

Write-Step "Esperando URL publica de ngrok (max 30s)..."
$ngrokUrl = $null
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp   = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -TimeoutSec 1 -ErrorAction Stop
        $tunnel = $resp.tunnels | Where-Object { $_.public_url -like "https://*" } | Select-Object -First 1
        if ($tunnel) { $ngrokUrl = $tunnel.public_url; break }
    } catch {}
    Start-Sleep -Seconds 1
}

# --- Resumen ---
Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "  Instalacion completa" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Carpeta:     $InstallDir"
Write-Host "URL local:   http://localhost:8000"
if ($ngrokUrl) {
    Write-Host "URL publica: $ngrokUrl" -ForegroundColor Cyan
} else {
    Write-Warn "ngrok aun no expuso URL publica."
    Write-Host "         Revisa http://localhost:4040 o el log: $InstallDir\data\logs\ngrok.log"
}
Write-Host "Logs app:    $InstallDir\data\logs\rdx-totem.log"
Write-Host "URL kiosko:  $KioskUrl"
if ($PanelPassword) {
    Write-Host "Auth panel:  user=$PanelUsername / password=*** (definido en .env)" -ForegroundColor Cyan
} else {
    Write-Warn "Panel SIN auth. Definir PANEL_PASSWORD en $envPath y reiniciar la tarea."
}
Write-Host ""
Write-Host "COMANDOS UTILES:" -ForegroundColor Yellow
Write-Host "  Detener:    Stop-ScheduledTask -TaskName RDxTotem"
Write-Host "  Iniciar:    Start-ScheduledTask -TaskName RDxTotem"
Write-Host "  Estado:     Get-ScheduledTask -TaskName RDxTotem"
Write-Host "  Desinstalar: .\ops\uninstall.ps1"
Write-Host ""
Write-Host "PROXIMO PASO -- AutoLogon:" -ForegroundColor Yellow
Write-Host "  Para que el totem vuelva solo tras corte de luz, configura AutoLogon:"
Write-Host "    https://learn.microsoft.com/en-us/sysinternals/downloads/autologon"
Write-Host "  Descarga, ejecuta como admin, y configura el usuario actual."
Write-Host ""
