import os
from contextlib import closing

from api import get_connection, init_db
from config import DB_PATH

ROOMS = [
    "Living Room",
    "Bedroom",
    "Kitchen",
    "Home Office",
    "Garage",
]

# (device_id, model, status, room_id) -- room_id 1..5 matches ROOMS order
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


def seed() -> None:
    """Recreate the database from scratch with rooms and devices."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    init_db()

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
            DEVICES,
        )
        conn.commit()

        room_count = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        device_count = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]

    print(f"Database created at: {DB_PATH}")
    print(f"Rooms inserted:   {room_count}")
    print(f"Devices inserted: {device_count}")


if __name__ == "__main__":
    seed()
