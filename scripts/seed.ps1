# Loads the demo dataset into Postgres. Run once after run-local.ps1's
# migrations have applied (or any time you want to reset demo data).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location "$root/backend"
& "$root/backend/.venv/Scripts/python.exe" -m scripts.seed
Pop-Location
