# Start API + Flet UI (run from air_quality_project folder)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: Virtual environment Python not found at $venvPython"
    Write-Host "Create the venv with: py -m venv .venv"
    Write-Host "Then install dependencies with: .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

Write-Host "Using Python: $venvPython"

Write-Host "Seeding database (if needed)..."
& $venvPython seed.py

Write-Host "Starting API on http://127.0.0.1:8000 ..."
$api = Start-Process -FilePath $venvPython -ArgumentList "-m", "uvicorn", "api:app", "--reload", "--port", "8000" -PassThru -WindowStyle Normal

Start-Sleep -Seconds 3

try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5
    if ($r.status -ne "ok") { throw "Health check failed" }
} catch {
    Write-Host "ERROR: API did not start. Close anything using port 8000 and try again."
    if ($api -and -not $api.HasExited) {
        Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
    }
    exit 1
}

Write-Host "Starting Flet app..."
& $venvPython main.py

if ($api -and -not $api.HasExited) {
    Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
}
