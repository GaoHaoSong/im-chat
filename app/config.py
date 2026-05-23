from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "im.db"
UPLOAD_DIR = DATA_DIR / "uploads"

MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_IMAGE_SIZE = 10 * 1024 * 1024
RECALL_WINDOW_SECONDS = 120

USERNAME_PATTERN = r"^[A-Za-z0-9_]{3,20}$"
PIN_PATTERN = r"^[0-9]{4,6}$"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
