"""Background IoT simulator — POSTs random readings every 5–10 seconds."""

import random
import time

import requests

from config import API_BASE_URL

INTERVAL_MIN = 4
INTERVAL_MAX = 7


def login() -> str:
    resp = requests.post(
        f"{API_BASE_URL}/auth/login",
        json={"username": "admin", "password": "admin123"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def fetch_device_ids(token: str) -> list[str]:
    resp = requests.get(
        f"{API_BASE_URL}/devices",
        headers={"Authorization": f"Bearer {token}"},
        params={"limit": 100, "offset": 0},
        timeout=10,
    )
    resp.raise_for_status()
    return [d["device_id"] for d in resp.json()["items"]]


def main() -> None:
    print(f"Simulator → {API_BASE_URL}")
    token = login()
    device_ids = fetch_device_ids(token)
    if not device_ids:
        print("No devices found. Run: py seed.py")
        return

    print(f"Sending readings for {len(device_ids)} devices. Ctrl+C to stop.")
    headers = {"Authorization": f"Bearer {token}"}

    while True:
        device_id = random.choice(device_ids)
        # Bias toward threshold-exceeding values so alerts fire reliably
        pm25 = round(random.uniform(36, 72), 1)   # always > 35 threshold
        co2 = round(random.uniform(1010, 1500), 0)  # always > 1000 threshold
        payload = {
            "device_id": device_id,
            "pm25": pm25,
            "co2": co2,
            "temperature": round(random.uniform(19, 25), 1),
            "humidity": round(random.uniform(35, 55), 1),
        }
        try:
            resp = requests.post(
                f"{API_BASE_URL}/readings",
                json=payload,
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 201:
                print(f"POST {device_id} pm25={pm25} co2={co2}")
            else:
                print(f"Error {resp.status_code}: {resp.text}")
        except requests.RequestException as ex:
            print(f"Request failed: {ex}")

        time.sleep(random.uniform(INTERVAL_MIN, INTERVAL_MAX))


if __name__ == "__main__":
    main()
