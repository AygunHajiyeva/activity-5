import csv
import io
import sqlite3
from pathlib import Path
from contextlib import closing
from typing import Annotated

import bcrypt
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from auth import create_session, get_session, revoke_session
from config import (
    CORS_ORIGINS,
    DB_PATH,
    DEFAULT_CO2_THRESHOLD,
    DEFAULT_PM25_THRESHOLD,
    MAX_PAGE_SIZE,
    PAGE_SIZE,
)
from models import DeviceCreate, LoginRequest, ReadingCreate, ThresholdUpdate

app = FastAPI(title="Air Quality Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SORT_COLUMNS = {
    "id": "d.id",
    "device_id": "d.device_id",
    "model": "d.model",
    "status": "d.status",
    "room_name": "r.name",
}

READING_SORT_COLUMNS = {
    "reading_id": "rd.reading_id",
    "device_id": "rd.device_id",
    "pm25": "rd.pm25",
    "co2": "rd.co2",
    "timestamp": "rd.timestamp",
}


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _add_column_if_missing(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with closing(get_connection()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                room_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS devices (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL UNIQUE,
                model     TEXT NOT NULL,
                status    TEXT NOT NULL,
                room_id   INTEGER NOT NULL,
                FOREIGN KEY (room_id) REFERENCES rooms (room_id)
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','operator')),
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS readings (
                reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                pm25 REAL NOT NULL,
                co2 REAL NOT NULL,
                temperature REAL,
                humidity REAL,
                timestamp TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (device_id) REFERENCES devices (device_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS alerts (
                alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                reading_id INTEGER NOT NULL,
                alert_type TEXT NOT NULL CHECK(alert_type IN ('pm25','co2')),
                value REAL NOT NULL,
                threshold REAL NOT NULL,
                timestamp TEXT DEFAULT (datetime('now')),
                acknowledged INTEGER DEFAULT 0,
                FOREIGN KEY (device_id) REFERENCES devices (device_id) ON DELETE CASCADE,
                FOREIGN KEY (reading_id) REFERENCES readings (reading_id) ON DELETE CASCADE
            );
            """
        )
        _add_column_if_missing(
            conn, "devices", "pm25_threshold", f"REAL DEFAULT {DEFAULT_PM25_THRESHOLD}"
        )
        _add_column_if_missing(
            conn, "devices", "co2_threshold", f"REAL DEFAULT {DEFAULT_CO2_THRESHOLD}"
        )
        conn.commit()


init_db()


def get_bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    return authorization[7:].strip()


def get_current_user(token: Annotated[str, Depends(get_bearer_token)]) -> dict:
    user = get_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {**user, "token": token}


def require_admin(user: Annotated[dict, Depends(get_current_user)]) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _search_clause(search: str) -> tuple[str, list]:
    if not search.strip():
        return "", []
    term = f"%{search.strip()}%"
    return (
        """
        WHERE d.device_id LIKE ?
           OR d.model LIKE ?
           OR d.status LIKE ?
           OR r.name LIKE ?
        """,
        [term, term, term, term],
    )


def _check_thresholds(
    conn: sqlite3.Connection, device_id: str, reading_id: int, pm25: float, co2: float
) -> None:
    dev = conn.execute(
        "SELECT pm25_threshold, co2_threshold FROM devices WHERE device_id = ?",
        (device_id,),
    ).fetchone()
    if not dev:
        return
    if pm25 > dev["pm25_threshold"]:
        conn.execute(
            """
            INSERT INTO alerts (device_id, reading_id, alert_type, value, threshold)
            VALUES (?, ?, 'pm25', ?, ?)
            """,
            (device_id, reading_id, pm25, dev["pm25_threshold"]),
        )
    if co2 > dev["co2_threshold"]:
        conn.execute(
            """
            INSERT INTO alerts (device_id, reading_id, alert_type, value, threshold)
            VALUES (?, ?, 'co2', ?, ?)
            """,
            (device_id, reading_id, co2, dev["co2_threshold"]),
        )


def _sync_alerts_for_device_thresholds(
    conn: sqlite3.Connection,
    device_id: str,
    pm25_threshold: float,
    co2_threshold: float,
) -> dict[str, int]:
    removed_pm25 = conn.execute(
        """
        DELETE FROM alerts
        WHERE device_id = ?
          AND alert_type = 'pm25'
          AND value <= ?
        """,
        (device_id, pm25_threshold),
    ).rowcount
    removed_co2 = conn.execute(
        """
        DELETE FROM alerts
        WHERE device_id = ?
          AND alert_type = 'co2'
          AND value <= ?
        """,
        (device_id, co2_threshold),
    ).rowcount

    updated_pm25 = conn.execute(
        """
        UPDATE alerts
        SET threshold = ?
        WHERE device_id = ?
          AND alert_type = 'pm25'
        """,
        (pm25_threshold, device_id),
    ).rowcount
    updated_co2 = conn.execute(
        """
        UPDATE alerts
        SET threshold = ?
        WHERE device_id = ?
          AND alert_type = 'co2'
        """,
        (co2_threshold, device_id),
    ).rowcount

    created_pm25 = conn.execute(
        """
        INSERT INTO alerts (device_id, reading_id, alert_type, value, threshold, timestamp)
        SELECT r.device_id, r.reading_id, 'pm25', r.pm25, ?, r.timestamp
        FROM readings r
        WHERE r.device_id = ?
          AND r.pm25 > ?
          AND NOT EXISTS (
              SELECT 1
              FROM alerts a
              WHERE a.reading_id = r.reading_id
                AND a.alert_type = 'pm25'
          )
        """,
        (pm25_threshold, device_id, pm25_threshold),
    ).rowcount
    created_co2 = conn.execute(
        """
        INSERT INTO alerts (device_id, reading_id, alert_type, value, threshold, timestamp)
        SELECT r.device_id, r.reading_id, 'co2', r.co2, ?, r.timestamp
        FROM readings r
        WHERE r.device_id = ?
          AND r.co2 > ?
          AND NOT EXISTS (
              SELECT 1
              FROM alerts a
              WHERE a.reading_id = r.reading_id
                AND a.alert_type = 'co2'
          )
        """,
        (co2_threshold, device_id, co2_threshold),
    ).rowcount

    return {
        "created": created_pm25 + created_co2,
        "updated": updated_pm25 + updated_co2,
        "removed": removed_pm25 + removed_co2,
    }


@app.get("/health")
def health():
    db_path = get_connection().database
    db_size = "—"
    try:
        sz = Path(db_path).stat().st_size
        if sz < 1024:
            db_size = f"{sz} B"
        elif sz < 1024 * 1024:
            db_size = f"{sz // 1024} KB"
        else:
            db_size = f"{sz / (1024 * 1024):.1f} MB"
    except Exception:  # noqa: BLE001
        pass
    return {"status": "ok", "database_size": db_size}


@app.post("/auth/login")
def login(body: LoginRequest):
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT user_id, username, password_hash, role FROM users WHERE username = ?",
            (body.username,),
        ).fetchone()
    if not row or not bcrypt.checkpw(
        body.password.encode(), row["password_hash"].encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_session(row["user_id"], row["username"], row["role"])
    return {"token": token, "role": row["role"], "username": row["username"]}


@app.post("/auth/logout")
def logout(user: Annotated[dict, Depends(get_current_user)]):
    revoke_session(user["token"])
    return {"message": "Logged out"}


@app.get("/rooms")
def list_rooms(user: Annotated[dict, Depends(get_current_user)]):
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT room_id, name FROM rooms ORDER BY room_id"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/rooms", status_code=201)
def create_room(name: dict, user: Annotated[dict, Depends(require_admin)]):
    room_name = name.get("name", "").strip()
    if not room_name:
        raise HTTPException(status_code=400, detail="Room name is required")
    with closing(get_connection()) as conn:
        cur = conn.execute("INSERT INTO rooms (name) VALUES (?)", (room_name,))
        conn.commit()
        return {"room_id": cur.lastrowid, "name": room_name}


@app.delete("/rooms/{room_id}")
def delete_room(room_id: int, user: Annotated[dict, Depends(require_admin)]):
    with closing(get_connection()) as conn:
        dev = conn.execute(
            "SELECT COUNT(*) FROM devices WHERE room_id = ?", (room_id,)
        ).fetchone()[0]
        if dev > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete room: {dev} device(s) still assigned",
            )
        cur = conn.execute("DELETE FROM rooms WHERE room_id = ?", (room_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Room not found")
    return {"message": "Room deleted"}


@app.get("/devices")
def list_devices(
    user: Annotated[dict, Depends(get_current_user)],
    limit: int = PAGE_SIZE,
    offset: int = 0,
    search: str = "",
    sort_by: str = "id",
    order: str = "asc",
):
    limit = min(max(1, limit), MAX_PAGE_SIZE)
    offset = max(0, offset)
    sort_col = SORT_COLUMNS.get(sort_by, SORT_COLUMNS["id"])
    order_dir = "DESC" if order.lower() == "desc" else "ASC"
    where_sql, params = _search_clause(search)
    base_from = """
        FROM devices d
        LEFT JOIN rooms r ON d.room_id = r.room_id
    """
    with closing(get_connection()) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) {base_from} {where_sql}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT d.id, d.device_id, d.model, d.status, d.room_id,
                   d.pm25_threshold, d.co2_threshold, r.name AS room_name
            {base_from}
            {where_sql}
            ORDER BY {sort_col} {order_dir}
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [dict(row) for row in rows],
    }


@app.get("/devices/{record_id}")
def get_device(record_id: int, user: Annotated[dict, Depends(get_current_user)]):
    with closing(get_connection()) as conn:
        row = conn.execute(
            """
            SELECT d.id, d.device_id, d.model, d.status, d.room_id,
                   d.pm25_threshold, d.co2_threshold, r.name AS room_name
            FROM devices d
            LEFT JOIN rooms r ON d.room_id = r.room_id
            WHERE d.id = ?
            """,
            (record_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    return dict(row)


@app.post("/devices", status_code=201)
def create_device(
    device: DeviceCreate, user: Annotated[dict, Depends(require_admin)]
):
    with closing(get_connection()) as conn:
        room = conn.execute(
            "SELECT room_id FROM rooms WHERE room_id = ?", (device.room_id,)
        ).fetchone()
        if room is None:
            raise HTTPException(status_code=400, detail=f"Room {device.room_id} not found")
        try:
            cur = conn.execute(
                """
                INSERT INTO devices (device_id, model, status, room_id)
                VALUES (?, ?, ?, ?)
                """,
                (device.device_id, device.model, device.status, device.room_id),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=400, detail=f"Device '{device.device_id}' already exists"
            )
        return {"id": cur.lastrowid, **device.model_dump()}


@app.put("/devices/{record_id}")
def update_device(
    record_id: int,
    device: DeviceCreate,
    user: Annotated[dict, Depends(require_admin)],
):
    with closing(get_connection()) as conn:
        if not conn.execute(
            "SELECT id FROM devices WHERE id = ?", (record_id,)
        ).fetchone():
            raise HTTPException(status_code=404, detail="Device not found")
        if not conn.execute(
            "SELECT room_id FROM rooms WHERE room_id = ?", (device.room_id,)
        ).fetchone():
            raise HTTPException(status_code=400, detail=f"Room {device.room_id} not found")
        # Check uniqueness excluding the current device itself
        if conn.execute(
            "SELECT id FROM devices WHERE device_id = ? AND id != ?",
            (device.device_id, record_id),
        ).fetchone():
            raise HTTPException(
                status_code=400, detail=f"Device '{device.device_id}' already exists"
            )
        conn.execute(
            """
            UPDATE devices
            SET device_id = ?, model = ?, status = ?, room_id = ?
            WHERE id = ?
            """,
            (
                device.device_id,
                device.model,
                device.status,
                device.room_id,
                record_id,
            ),
        )
        conn.commit()
        return {"id": record_id, **device.model_dump()}


@app.put("/devices/{record_id}/thresholds")
def update_thresholds(
    record_id: int,
    body: ThresholdUpdate,
    user: Annotated[dict, Depends(require_admin)],
):
    with closing(get_connection()) as conn:
        device = conn.execute(
            "SELECT device_id FROM devices WHERE id = ?", (record_id,)
        ).fetchone()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        conn.execute(
            """
            UPDATE devices SET pm25_threshold = ?, co2_threshold = ?
            WHERE id = ?
            """,
            (body.pm25_threshold, body.co2_threshold, record_id),
        )
        alert_changes = _sync_alerts_for_device_thresholds(
            conn,
            device["device_id"],
            body.pm25_threshold,
            body.co2_threshold,
        )
        conn.commit()
    return {
        "message": "Thresholds updated",
        "alert_changes": alert_changes,
        **body.model_dump(),
    }


@app.delete("/devices/{record_id}")
def delete_device(record_id: int, user: Annotated[dict, Depends(require_admin)]):
    with closing(get_connection()) as conn:
        cur = conn.execute("DELETE FROM devices WHERE id = ?", (record_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Device not found")
    return {"message": "Device deleted successfully"}


@app.get("/readings")
def list_readings(
    user: Annotated[dict, Depends(get_current_user)],
    limit: int = PAGE_SIZE,
    offset: int = 0,
    search: str = "",
    sort_by: str = "timestamp",
    order: str = "desc",
):
    limit = min(max(1, limit), MAX_PAGE_SIZE)
    offset = max(0, offset)
    sort_col = READING_SORT_COLUMNS.get(sort_by, READING_SORT_COLUMNS["timestamp"])
    order_dir = "DESC" if order.lower() == "desc" else "ASC"
    where_sql, params = "", []
    if search.strip():
        term = f"%{search.strip()}%"
        where_sql = "WHERE rd.device_id LIKE ? OR CAST(rd.pm25 AS TEXT) LIKE ?"
        params = [term, term]
    with closing(get_connection()) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM readings rd {where_sql}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT rd.reading_id, rd.device_id, rd.pm25, rd.co2,
                   rd.temperature, rd.humidity, rd.timestamp
            FROM readings rd
            {where_sql}
            ORDER BY {sort_col} {order_dir}
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [dict(r) for r in rows],
    }


@app.post("/readings", status_code=201)
def create_reading(
    reading: ReadingCreate,
    user: Annotated[dict, Depends(get_current_user)],
):
    with closing(get_connection()) as conn:
        dev = conn.execute(
            "SELECT device_id FROM devices WHERE device_id = ?", (reading.device_id,)
        ).fetchone()
        if not dev:
            raise HTTPException(status_code=400, detail="Device not found")
        cur = conn.execute(
            """
            INSERT INTO readings (device_id, pm25, co2, temperature, humidity)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                reading.device_id,
                reading.pm25,
                reading.co2,
                reading.temperature,
                reading.humidity,
            ),
        )
        reading_id = cur.lastrowid
        _check_thresholds(
            conn, reading.device_id, reading_id, reading.pm25, reading.co2
        )
        conn.commit()
    return {"reading_id": reading_id, **reading.model_dump()}


@app.get("/alerts")
def list_alerts(
    user: Annotated[dict, Depends(get_current_user)],
    acknowledged: str | None = None,
    limit: int = PAGE_SIZE,
    offset: int = 0,
):
    limit = min(max(1, limit), MAX_PAGE_SIZE)
    offset = max(0, offset)
    where, params = "", []
    if acknowledged in ("0", "1"):
        where = "WHERE a.acknowledged = ?"
        params = [int(acknowledged)]
    with closing(get_connection()) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM alerts a {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT a.alert_id, a.device_id, a.reading_id, a.alert_type,
                   a.value, a.threshold, a.timestamp, a.acknowledged
            FROM alerts a
            {where}
            ORDER BY a.timestamp DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [dict(r) for r in rows],
    }


@app.put("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int, user: Annotated[dict, Depends(get_current_user)]
):
    with closing(get_connection()) as conn:
        cur = conn.execute(
            "UPDATE alerts SET acknowledged = 1 WHERE alert_id = ?", (alert_id,)
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert acknowledged"}


@app.get("/dashboard/summary")
def dashboard_summary(user: Annotated[dict, Depends(get_current_user)]):
    with closing(get_connection()) as conn:
        active = conn.execute(
            "SELECT COUNT(*) FROM devices WHERE status = 'online'"
        ).fetchone()[0]
        avg = conn.execute(
            "SELECT AVG(pm25), AVG(co2) FROM readings"
        ).fetchone()
        alerts = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE acknowledged = 0"
        ).fetchone()[0]
    return {
        "active_devices": active,
        "avg_pm25": round(avg[0], 2) if avg[0] is not None else 0,
        "avg_co2": round(avg[1], 2) if avg[1] is not None else 0,
        "alert_count": alerts,
    }


@app.get("/dashboard/chart")
def dashboard_chart(user: Annotated[dict, Depends(get_current_user)]):
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """
            SELECT reading_id, pm25, co2, timestamp
            FROM readings
            WHERE timestamp >= datetime('now', '-24 hours')
            ORDER BY timestamp ASC
            LIMIT 200
            """
        ).fetchall()
    points = []
    for i, row in enumerate(rows):
        points.append(
            {
                "x": i,
                "pm25": row["pm25"],
                "co2": row["co2"],
                "timestamp": row["timestamp"],
            }
        )
    return {"points": points}


@app.get("/export/readings")
def export_readings(user: Annotated[dict, Depends(get_current_user)]):
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """
            SELECT reading_id, device_id, pm25, co2, temperature, humidity, timestamp
            FROM readings ORDER BY timestamp DESC
            """
        ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["reading_id", "device_id", "pm25", "co2", "temperature", "humidity", "timestamp"]
    )
    for row in rows:
        writer.writerow(
            [
                row["reading_id"],
                row["device_id"],
                row["pm25"],
                row["co2"],
                row["temperature"],
                row["humidity"],
                row["timestamp"],
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=readings.csv"},
    )
