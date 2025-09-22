# config.py (Version 2.0)
import os

# --- Project Structure ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_ROOT_FOLDER = "projects"
ASSETS_FOLDER = "assets"

# --- Display ---
FULL_REFRESH_SLEEP = 2.0
DISPLAY_PARTIAL_SLEEP = 0.5
TEXT_MARGIN = 10
EDITOR_HEADER_HEIGHT = 60
EDITOR_FOOTER_HEIGHT = 30

# --- Editor ---
AUTO_SAVE_INTERVAL = 30000  # 30 seconds in milliseconds
INACTIVITY_SAVE_TIMEOUT = 5000 # 5 seconds in milliseconds
AUTO_SAVE_INDICATOR_DURATION = 2000  # 2 seconds
WORD_COUNT_DISPLAY_DURATION = 3000  # 3 seconds

# --- System ---
INACTIVITY_TIMEOUT_SECONDS = 600 # 10 minutes
KEYBOARD_POLL_TIMEOUT = 1.0 # seconds