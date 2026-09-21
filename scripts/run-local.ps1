# Runs SeatRush locally without Docker.
# Prerequisites: PostgreSQL 16 and Redis installed as native Windows services
# (see docs/local-setup.md), Python 3.12 venv created in backend/.venv,
# and `npm install` already run in frontend/.
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts/run-local.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "Applying database migrations..."
Push-Location "$root/backend"
& "$root/backend/.venv/Scripts/python.exe" -m alembic upgrade head
Pop-Location

Write-Host "Starting API server..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root/backend'; .venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000"

Write-Host "Starting background workers..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root/backend'; .venv\Scripts\Activate.ps1; python -m app.workers.run_workers"

Write-Host "Starting frontend dev server..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root/frontend'; npm run dev"

Write-Host ""
Write-Host "SeatRush is starting in three windows: API (localhost:8000), workers, and frontend (localhost:3000)."
Write-Host "Run scripts/seed.ps1 once to load demo data."
