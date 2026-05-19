import os
import random
from contextlib import closing
from datetime import datetime, timedelta

import bcrypt

from api import get_connection, init_db
from config import DB_PATH

ROOMS = [
    "Living Room",
    "Bedroom",
    "Kitchen",
    "Home Office",
    "Garage",
]

STATUSES = ["online", "offline", "maintenance"]
MODELS = [
    "PurpleAir PA-II",
    "Awair Element",
    "Airthings View Plus",
    "IKEA Vindstyrka",
    "Atmotube Pro",
]

DEVICES = [
    ("AQ-001", "PurpleAir PA-II", "online", 1),
    ("AQ-002", "Awair Element", "online", 1),
    ("AQ-003", "Airthings View Plus", "offline", 2),
    ("AQ-004", "IKEA Vindstyrka", "online", 2),
    ("AQ-005", "Atmotube Pro", "maintenance", 3),
    ("AQ-006", "uHoo Smart", "online", 3),
    ("AQ-007", "Qingping Air Monitor", "online", 4),
    ("AQ-008", "Aranet4 Home", "offline", 4),
    ("AQ-009", "SAF Aranet Pro", "online", 5),
    ("AQ-010", "Temtop M2000", "maintenance", 5),
]

USERS = [
    ("admin", "admin123", "admin"),
    ("operator", "operator123", "operator"),
]


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _extra_devices():
    extras = []
    for n in range(11, 101):
        extras.append(
            (
                f"AQ-{n:03d}",
                MODELS[(n - 1) % len(MODELS)],
                STATUSES[(n - 1) % len(STATUSES)],
                ((n - 1) % len(ROOMS)) + 1,
            )
        )
    return extras


def _seed_readings_and_alerts(conn, device_ids: list[str]) -> None:
    """Insert readings over the last 24h; some exceed thresholds for alerts."""
    now = datetime.now()
    for device_id in device_ids[:15]:
        for hours_ago in range(24, 0, -2):
            ts = (now - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")
            pm25 = round(random.uniform(5, 55), 1)
            co2 = round(random.uniform(400, 1400), 0)
            cur = conn.execute(
                """
                INSERT INTO readings (device_id, pm25, co2, temperature, humidity, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    pm25,
                    co2,
                    round(random.uniform(18, 26), 1),
                    round(random.uniform(30, 60), 1),
                    ts,
                ),
            )
            reading_id = cur.lastrowid
            dev = conn.execute(
                "SELECT pm25_threshold, co2_threshold FROM devices WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            if pm25 > dev["pm25_threshold"]:
                conn.execute(
                    """
                    INSERT INTO alerts (device_id, reading_id, alert_type, value, threshold, timestamp)
                    VALUES (?, ?, 'pm25', ?, ?, ?)
                    """,
                    (device_id, reading_id, pm25, dev["pm25_threshold"], ts),
                )
            if co2 > dev["co2_threshold"]:
                conn.execute(
                    """
                    INSERT INTO alerts (device_id, reading_id, alert_type, value, threshold, timestamp)
                    VALUES (?, ?, 'co2', ?, ?, ?)
                    """,
                    (device_id, reading_id, co2, dev["co2_threshold"], ts),
                )


def seed() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    init_db()
    all_devices = DEVICES + _extra_devices()

    with closing(get_connection()) as conn:
        conn.executemany(
            "INSERT INTO rooms (name) VALUES (?)",
            [(name,) for name in ROOMS],
        )
        conn.executemany(
            """
            INSERT INTO devices (device_id, model, status, room_id)
            VALUES (?, ?, ?, ?)
            """,
            all_devices,
        )
        conn.executemany(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
            """,
            [(u, _hash_password(p), r) for u, p, r in USERS],
        )
        device_ids = [d[0] for d in all_devices]
        _seed_readings_and_alerts(conn, device_ids)
        conn.commit()

        print(f"Database: {DB_PATH}")
        print(f"Rooms:    {conn.execute('SELECT COUNT(*) FROM rooms').fetchone()[0]}")
        print(f"Devices:  {conn.execute('SELECT COUNT(*) FROM devices').fetchone()[0]}")
        print(f"Users:    {conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]}")
        print(f"Readings: {conn.execute('SELECT COUNT(*) FROM readings').fetchone()[0]}")
        print(f"Alerts:   {conn.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]}")
        print("Login: admin / admin123  |  operator / operator123")


if __name__ == "__main__":
    seed()
