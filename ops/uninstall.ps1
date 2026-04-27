<#
.SYNOPSIS
    Desinstala el MVP de RDx Totem.

.DESCRIPTION
    Detiene la Scheduled Task, mata procesos (ngrok, python, chrome del kiosko)
    y opcionalmente borra la carpeta de instalación.

.PARAMETER InstallDir
    Carpeta de instalación. Default: C:\rdx-totem-mvp

.PARAMETER RemoveFiles
    Si se pasa, también borra la carpeta de instalación con todos los datos.
#>

#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$InstallDir = "C:\rdx-totem-mvp",
    [switch]$RemoveFiles
)

$ErrorActionPreference = "Continue"
$taskName = "RDxTotem"

Write-Host ""
Write-Host "Desinstalando RDx Totem MVP..." -ForegroundColor Cyan

# Detener Scheduled Task
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "  [OK] Scheduled Task removido" -ForegroundColor Green
} else {
    Write-Host "  [--] Scheduled Task no existia" -ForegroundColor Yellow
}

# Matar ngrok
Get-Process -Name "ngrok" -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] ngrok PID $($_.Id) terminado" -ForegroundColor Green
}

# Matar python.exe que use el venv del install dir
$venvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -eq $venvPython } catch { $false }
} | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] python (venv) PID $($_.Id) terminado" -ForegroundColor Green
}

# Matar Chrome que use nuestro user-data-dir
$kioskoProfile = Join-Path $InstallDir "data\chrome-profile"
Get-Process -Name "chrome" -ErrorAction SilentlyContinue | Where-Object {
    try {
        $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
        $cmdline -and $cmdline.Contains($kioskoProfile)
    } catch { $false }
} | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] chrome (kiosko) PID $($_.Id) terminado" -ForegroundColor Green
}

if ($RemoveFiles) {
    if (Test-Path $InstallDir) {
        Remove-Item $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK] $InstallDir eliminado" -ForegroundColor Green
    }
} else {
    Write-Host ""
    Write-Host "Carpeta conservada: $InstallDir" -ForegroundColor Yellow
    Write-Host "Para borrarla: .\uninstall.ps1 -RemoveFiles" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Desinstalacion completa." -ForegroundColor Green
