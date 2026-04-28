<#
.SYNOPSIS
    Wrapper que la Scheduled Task ejecuta al logon: arranca ngrok y el servicio FastAPI.

.DESCRIPTION
    Lanza ngrok como proceso detached, espera 2s, y arranca el servicio FastAPI en
    foreground. Si FastAPI muere, este script termina y la Scheduled Task lo
    relanza tras 1 minuto.
#>

$ErrorActionPreference = "Continue"
$InstallDir = Split-Path -Parent $PSScriptRoot
Set-Location $InstallDir

$LogsDir = Join-Path $InstallDir "data\logs"
New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null

# Mata ngrok zombie de runs anteriores (idempotente).
Get-Process -Name "ngrok" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# Lee puerto desde .env (default 8000).
$port = 8000
$envFile = Join-Path $InstallDir ".env"
if (Test-Path $envFile) {
    $portMatch = Select-String -Path $envFile -Pattern "^PORT=(\d+)" -ErrorAction SilentlyContinue
    if ($portMatch) {
        $port = [int]$portMatch.Matches[0].Groups[1].Value
    }
}

# Lanza ngrok detached.
Start-Process -FilePath "ngrok" `
    -ArgumentList @("http", "$port", "--log=stdout") `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogsDir "ngrok.log") `
    -RedirectStandardError (Join-Path $LogsDir "ngrok-err.log") | Out-Null

Start-Sleep -Seconds 2

# Lanza FastAPI en foreground.
$venvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "No encontre $venvPython. Corre primero install.ps1."
    exit 1
}

# stderr se redirige a app-stderr.log para capturar tracebacks de import-time
# (los que ocurren antes de que setup_logging() configure el RotatingFileHandler).
$stderrLog = Join-Path $LogsDir "app-stderr.log"
& $venvPython -m app.main 2>> $stderrLog

# Propagamos el exit code de python para que la Scheduled Task vea las fallas
# y aplique RestartInterval. Sin esto el wrapper terminaria con 0 aunque
# python haya crasheado, y el scheduler considera la corrida exitosa.
exit $LASTEXITCODE
