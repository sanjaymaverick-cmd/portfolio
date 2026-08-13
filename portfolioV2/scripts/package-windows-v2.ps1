# Build a local MERIDIAN-V2 folder for Windows. Advisor only — no broker.
# From portfolioV2/:
#   .\scripts\package-windows-v2.ps1
# Output: dist\MERIDIAN-V2\MERIDIAN-V2.exe
# Does not touch v1 scripts or dist\MERIDIAN.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }

& $python -m pip install -e ".[desktop]" pyinstaller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$sep = ";"
& $python -m PyInstaller --noconfirm --clean --name MERIDIAN-V2 --onedir --noconsole `
  --add-data "meridian_v2/ui/templates${sep}meridian_v2/ui/templates" `
  --add-data "meridian_v2/ui/static${sep}meridian_v2/ui/static" `
  --add-data "config/default.yaml${sep}config" `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import meridian_v2.app `
  meridian_v2/__main__.py

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Built dist\MERIDIAN-V2\MERIDIAN-V2.exe"
Write-Host "V2 data lives at ~/MeridianV2/meridian_v2.db — never v1 meridian.db"
