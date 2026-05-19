# IoT Home Air Quality Monitor

FastAPI + SQLite backend, Flet desktop UI, optional IoT simulator.

## Features

- **Login** — admin / operator roles (RBAC)
- **Dashboard** — summary cards, PM2.5 trend chart, recent readings, auto-refresh every 5s
- **Devices** — paginated CRUD (admin), search & sort
- **Alerts** — view and acknowledge
- **Settings** (admin) — per-device thresholds, CSV export
- **UI** — AppBar, MenuBar, BottomAppBar, BottomSheet (quick add reading)
- **Simulator** — background fake sensor POSTs

## Setup

```powershell
cd air_quality_project
py -m pip install -r requirements.txt
py seed.py
```

## Run

**Terminal 1 — API:**

```powershell
py -m uvicorn api:app --reload --port 8000
```

**Terminal 2 — UI:**

```powershell
py main.py
```

**Optional — simulator (Terminal 3):**

```powershell
py simulator.py
```

Or use `.\run.ps1` to start API + UI on Windows.



