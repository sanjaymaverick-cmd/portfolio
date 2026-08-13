# Build a local MERIDIAN folder for Windows. Advisor only — no broker.
# From the repo root:
#   .\scripts\package-windows.ps1
# Output: dist\MERIDIAN\MERIDIAN.exe

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }

& $python -m pip install -e ".[desktop]" pyinstaller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$sep = ";"
& $python -m PyInstaller --noconfirm --clean --name MERIDIAN --onedir --noconsole `
  --add-data "meridian/ui/templates${sep}meridian/ui/templates" `
  --add-data "meridian/ui/static${sep}meridian/ui/static" `
  --add-data "config/default.yaml${sep}config" `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import meridian.app `
  --collect-all plotly `
  meridian/__main__.py

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Built dist\MERIDIAN\MERIDIAN.exe"
Write-Host "Data still lives next to the working directory as .\data"
