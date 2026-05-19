# Air Quality Monitor

This is an IoT Home Air Quality Monitor project.

The project uses:

- FastAPI for the backend REST API
- SQLite for local data storage
- Flet for the desktop user interface
- Python requests for frontend-to-backend API calls

## Current Features

- SQLite database with rooms and air quality devices
- Seed script with sample room and device data
- FastAPI endpoint to list devices
- FastAPI endpoint to add a new device
- FastAPI endpoints to update and delete devices
- Flet desktop UI with a device records table
- Add New form with basic validation
- Search field for filtering device records
- Edit dialog for updating existing device records
- Delete confirmation dialog for removing device records
- NavigationBar for switching between Records and Add New views
- Success and error snackbar messages
- Data persistence using SQLite

## Project Files

```text
air_quality_project/
+-- api.py              # FastAPI backend
+-- main.py             # Flet desktop frontend
+-- models.py           # Pydantic request models
+-- config.py           # Shared configuration
+-- seed.py             # Recreates and fills the SQLite database
+-- air_quality.db      # SQLite database
+-- README.md
```

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/devices` | Returns the list of devices with room names |
| POST | `/devices` | Adds a new device |
| PUT | `/devices/{id}` | Updates an existing device |
| DELETE | `/devices/{id}` | Deletes an existing device |

Example POST body:

```json
{
  "device_id": "AQ-011",
  "model": "Air Quality Sensor",
  "status": "online",
  "room_id": 1
}
```
