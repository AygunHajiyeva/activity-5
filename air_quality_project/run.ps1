# Start API + Simulator + Flet UI
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Use venv if available, otherwise fall back to system py
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $py = $venvPython
    Write-Host "Using venv Python: $py"
} else {
    $py = (Get-Command py -ErrorAction SilentlyContinue).Source
    if (-not $py) { $py = (Get-Command python -ErrorAction SilentlyContinue).Source }
    if (-not $py) {
        Write-Host "ERROR: Python not found. Install Python or create a venv at .venv\"
        exit 1
    }
    Write-Host "Using system Python: $py"
}

Write-Host "Seeding database (if needed)..."
& $py seed.py

Write-Host "Starting API on http://127.0.0.1:8000 ..."
$api = Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "api:app", "--reload", "--port", "8000" -PassThru -WindowStyle Normal

Start-Sleep -Seconds 3

try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5
    if ($r.status -ne "ok") { throw "Health check failed" }
} catch {
    Write-Host "ERROR: API did not start. Close anything using port 8000 and try again."
    if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
    exit 1
}

Write-Host "Starting simulator..."
$sim = Start-Process -FilePath $py -ArgumentList "simulator.py" -PassThru -WindowStyle Normal

Write-Host "Starting Flet UI..."
& $py main.py

# Cleanup when UI closes
if ($sim -and -not $sim.HasExited) { Stop-Process -Id $sim.Id -Force -ErrorAction SilentlyContinue }
if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
Write-Host "All processes stopped."
