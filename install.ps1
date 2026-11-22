$ErrorActionPreference = "Stop"

$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Dir ".venv"

Write-Host "Instalando ResoNexuz en $Dir..."
python -m venv $Venv
& "$Venv\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
& "$Venv\Scripts\pip.exe" install -e "$Dir[audio]"

$Launcher = Join-Path $Dir "resonexuz.bat"
"@echo off`r`n`"$Venv\Scripts\python.exe`" -m resonexuz %*" | Set-Content -Path $Launcher -Encoding ASCII

Write-Host ""
Write-Host "Listo. Ejecuta:"
Write-Host "  .\resonexuz.bat --windowed --with-ui   # visualizador + configurador web"
Write-Host "  .\resonexuz.bat --ui                   # solo configurador web"
Write-Host "  .\resonexuz.bat --wallpaper            # modo fondo en Windows"
