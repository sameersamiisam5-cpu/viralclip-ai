import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
OUTPUT_DIR = BASE_DIR / "output"

DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Default clip settings
DEFAULT_CLIP_DURATION = 45  # seconds
MIN_CLIP_DURATION = 20      # seconds
MAX_CLIP_DURATION = 60      # seconds

# Target 9:16 resolution (standard 1080x1920)
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
