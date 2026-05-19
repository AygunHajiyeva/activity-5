import os

# Absolute path to the SQLite database file (kept next to this file)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "air_quality.db")

# Base URL the Flet desktop app uses to reach the FastAPI server
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

PAGE_SIZE = 10
MAX_PAGE_SIZE = 100

DEFAULT_PM25_THRESHOLD = 35.0
DEFAULT_CO2_THRESHOLD = 1000.0

CORS_ORIGINS = [
    "http://127.0.0.1",
    "http://localhost",
]
