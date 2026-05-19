import os

# Absolute path to the SQLite database file (kept next to this file)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "air_quality.db")

# Base URL the Flet desktop app uses to reach the FastAPI server
API_BASE_URL = "http://127.0.0.1:8000"

# Default number of records fetched per page from GET /devices
PAGE_SIZE = 50
