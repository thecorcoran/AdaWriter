# keyboard.py
import os
import select
import logging
import time
from evdev import InputDevice, ecodes

KEY_MAP = {
    ecodes.KEY_A: {'unshifted': 'a', 'shifted': 'A'}, ecodes.KEY_B: {'unshifted': 'b', 'shifted': 'B'},
    ecodes.KEY_C: {'unshifted': 'c', 'shifted': 'C'}, ecodes.KEY_D: {'unshifted': 'd', 'shifted': 'D'},
    ecodes.KEY_E: {'unshifted': 'e', 'shifted': 'E'}, ecodes.KEY_F: {'unshifted': 'f', 'shifted': 'F'},
    ecodes.KEY_G: {'unshifted': 'g', 'shifted': 'G'}, ecodes.KEY_H: {'unshifted': 'h', 'shifted': 'H'},
    ecodes.KEY_I: {'unshifted': 'i', 'shifted': 'I'}, ecodes.KEY_J: {'unshifted': 'j', 'shifted': 'J'},
    ecodes.KEY_K: {'unshifted': 'k', 'shifted': 'K'}, ecodes.KEY_L: {'unshifted': 'l', 'shifted': 'L'},
    ecodes.KEY_M: {'unshifted': 'm', 'shifted': 'M'}, ecodes.KEY_N: {'unshifted': 'n', 'shifted': 'N'},
    ecodes.KEY_O: {'unshifted': 'o', 'shifted': 'O'}, ecodes.KEY_P: {'unshifted': 'p', 'shifted': 'P'},
    ecodes.KEY_Q: {'unshifted': 'q', 'shifted': 'Q'}, ecodes.KEY_R: {'unshifted': 'r', 'shifted': 'R'}, # Q is also used for Quit
    ecodes.KEY_S: {'unshifted': 's', 'shifted': 'S'}, ecodes.KEY_T: {'unshifted': 't', 'shifted': 'T'},
    ecodes.KEY_U: {'unshifted': 'u', 'shifted': 'U'}, ecodes.KEY_V: {'unshifted': 'v', 'shifted': 'V'},
    ecodes.KEY_W: {'unshifted': 'w', 'shifted': 'W'}, ecodes.KEY_X: {'unshifted': 'x', 'shifted': 'X'},
    ecodes.KEY_Y: {'unshifted': 'y', 'shifted': 'Y'}, ecodes.KEY_Z: {'unshifted': 'z', 'shifted': 'Z'},
    ecodes.KEY_1: {'unshifted': '1', 'shifted': '!'}, ecodes.KEY_2: {'unshifted': '2', 'shifted': '@'},
    ecodes.KEY_3: {'unshifted': '3', 'shifted': '#'}, ecodes.KEY_4: {'unshifted': '4', 'shifted': '$'},
    ecodes.KEY_5: {'unshifted': '5', 'shifted': '%'}, ecodes.KEY_6: {'unshifted': '6', 'shifted': '^'},
    ecodes.KEY_7: {'unshifted': '7', 'shifted': '&'}, ecodes.KEY_8: {'unshifted': '8', 'shifted': '*'},
    ecodes.KEY_9: {'unshifted': '9', 'shifted': '('}, ecodes.KEY_0: {'unshifted': '0', 'shifted': ')'},
    ecodes.KEY_MINUS:       {'unshifted': '-', 'shifted': '_'},
    ecodes.KEY_EQUAL:       {'unshifted': '=', 'shifted': '+'},
    ecodes.KEY_LEFTBRACE:   {'unshifted': '[', 'shifted': '{'},
    ecodes.KEY_RIGHTBRACE:  {'unshifted': ']', 'shifted': '}'},
    ecodes.KEY_BACKSLASH:   {'unshifted': '\\', 'shifted': '|'},
    ecodes.KEY_SEMICOLON:   {'unshifted': ';', 'shifted': ':'},
    ecodes.KEY_APOSTROPHE:  {'unshifted': "'", 'shifted': '"'},
    ecodes.KEY_GRAVE:       {'unshifted': '`', 'shifted': '~'},
    ecodes.KEY_COMMA:       {'unshifted': ',', 'shifted': '<'},
    ecodes.KEY_DOT:         {'unshifted': '.', 'shifted': '>'},
    ecodes.KEY_SLASH:       {'unshifted': '/', 'shifted': '?'},
    ecodes.KEY_SPACE:       ' ', ecodes.KEY_ENTER: 'ENTER', ecodes.KEY_BACKSPACE:   'BACKSPACE',
    ecodes.KEY_ESC:         'ESCAPE_KEY', ecodes.KEY_LEFTSHIFT: 'LSHIFT', ecodes.KEY_RIGHTSHIFT:  'RSHIFT',
    ecodes.KEY_F1:          'WORD_COUNT_HOTKEY', ecodes.KEY_F2: 'TIME_DISPLAY_HOTKEY',
    ecodes.KEY_PAGEUP:      'PAGE_UP', ecodes.KEY_PAGEDOWN:    'PAGE_DOWN',
    ecodes.KEY_UP:          'SCROLL_UP', ecodes.KEY_DOWN: 'SCROLL_DOWN',
}

class Keyboard:
    def __init__(self):
        self.device = self._find_and_init_keyboard()
        self.shift_pressed = False

    def _find_and_init_keyboard(self):
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