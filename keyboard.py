# keyboard.py
import os
import select
import logging
import time
import json
from evdev import InputDevice, ecodes

import config

class Keyboard:
    def __init__(self):
        self.device = self._find_and_init_keyboard()
        self.shift_pressed = False
        self.key_map = self._load_key_map()

    def _load_key_map(self):
        """Loads the keyboard layout from a JSON file specified in config."""
        layout_path = os.path.join(config.BASE_DIR, config.KEYBOARD_LAYOUT_FILE)
        try:
            with open(layout_path, 'r') as f:
                json_map = json.load(f)
            # Convert string keys from JSON back to integer ecodes
            return {int(k): v for k, v in json_map.items()}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.critical(f"Failed to load keyboard layout '{layout_path}': {e}")
            raise RuntimeError(f"Could not load keyboard layout: {e}")

    def _find_and_init_keyboard(self):
        path = None
        # First, check if a manual path is provided in the config
        if config.KEYBOARD_DEVICE_PATH and config.KEYBOARD_DEVICE_PATH.strip():
            if os.path.exists(config.KEYBOARD_DEVICE_PATH):
                path = config.KEYBOARD_DEVICE_PATH
            else:
                logging.warning(f"Manual keyboard path '{config.KEYBOARD_DEVICE_PATH}' not found. Falling back to auto-detection.")
        if not path:
            path = self._find_keyboard_device_path()
        if not path:
            raise RuntimeError("Keyboard not found.")
        
        logging.info(f"Found keyboard at {path}")
        device = InputDevice(path)
        device.grab()
        logging.info(f"Keyboard grabbed: {device.name}")
        return device

    def _find_keyboard_device_path(self):
        by_id_dir = '/dev/input/by-id/'
        potential_keyboards = []
        if os.path.exists(by_id_dir):
            for item_name in os.listdir(by_id_dir):
                if 'keyboard' in item_name.lower() or item_name.lower().endswith('-kbd'):
                    full_path = os.path.join(by_id_dir, item_name)
                    if os.path.exists(full_path) and not os.path.isdir(full_path):
                        if item_name.lower().endswith('-event-kbd'):
                            potential_keyboards.insert(0, full_path)
                        else:
                            potential_keyboards.append(full_path)
        return potential_keyboards[0] if potential_keyboards else None

    def read_events(self):
        """Yields keyboard events."""
        try:
            for event in self.device.read():
                yield event
        except (OSError, BlockingIOError) as e:
            logging.warning(f"Keyboard read error: {e}")
            time.sleep(0.1)

    def has_input(self, timeout=0.1):
        """Check if there is keyboard input waiting."""
        ready, _, _ = select.select([self.device.fd], [], [], timeout)
        return bool(ready)

    def close(self):
        """Ungrab and close the keyboard device."""
        if self.device:
            try:
                self.device.ungrab()
                self.device.close()
                logging.info("Keyboard ungrabbed and closed.")
            except Exception as e:
                logging.error(f"Error closing keyboard: {e}")