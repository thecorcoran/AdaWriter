# ada_writer_v1.4.3.py
# Changes:
# - Changed web server font to a serif font for a more classic look.
# - Restored the "View" button on the HTTP server page. (v1.4.2)
# - Changed directory names on the server page to be more user-friendly. (v1.4.2)
# - Changed the "Parent Directory" link on the server to "Home". (v1.4.2)
# - Added option to download files as .doc (RTF format) from the HTTP server. (v1.4.1)
# - Journal entries now automatically get a timestamp when a new session begins. (v1.4.0)

import os
# Attempt to disable ALSA/sound for Pygame if running headless and sound is not needed
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import sys
import pygame
import socket
import threading
import http.server
import socketserver
import netifaces
import time
from evdev import InputDevice, categorize, ecodes, KeyEvent # KeyEvent is used for constants
import select
from datetime import date, datetime
import html
from urllib.parse import unquote, urlparse, parse_qs
import re
import subprocess
import shutil

# Waveshare E-ink Display imports
from PIL import Image, ImageDraw, ImageFont

from waveshare_epd import epd4in2_V2

# --- Configuration ---
TEXT_MARGIN = 10
PROJECTS_ROOT_FOLDER = "projects"
ASSETS_FOLDER = "assets"
WIFI_SERVER_PORT = 8000
AUTO_SAVE_INDICATOR_DURATION = 1500 # milliseconds
AUTO_SAVE_INTERVAL = 30000 # milliseconds
WORD_COUNT_DISPLAY_DURATION = 2000 # milliseconds (also used for time display)
KEYBOARD_POLL_TIMEOUT = 0.01 # seconds for select timeout
DISPLAY_PARTIAL_SLEEP = 0.015 # seconds
FULL_REFRESH_SLEEP = 1.8 # seconds

# --- Inactivity Shutdown Configuration ---
LAST_KEYBOARD_ACTIVITY_TIME = time.time()
INACTIVITY_TIMEOUT_SECONDS = 10 * 60  # 10 minutes

def find_keyboard_device_path():
    """
    Scans /dev/input/by-id/ for a suitable keyboard device.
    Prefers devices with '-event-kbd' in their name.
    Falls back to checking /dev/input/eventX if by-id fails.
    """
    by_id_dir = '/dev/input/by-id/'
    potential_keyboards = []

    if os.path.exists(by_id_dir):
        print(f"DEBUG: Scanning {by_id_dir} for keyboards..."); sys.stdout.flush()
        for item_name in os.listdir(by_id_dir):
            if 'keyboard' in item_name.lower() or item_name.lower().endswith('-kbd'):
                full_path = os.path.join(by_id_dir, item_name)
                if os.path.exists(full_path) and not os.path.isdir(full_path):
                    if item_name.lower().endswith('-event-kbd'):
                        print(f"DEBUG: Found specific keyboard candidate by-id: {full_path}"); sys.stdout.flush()
                        potential_keyboards.insert(0, full_path) # Prioritize specific event kbd
                    else:
                        print(f"DEBUG: Found general keyboard candidate by-id: {full_path}"); sys.stdout.flush()
                        potential_keyboards.append(full_path)
    else:
        print(f"DEBUG: Directory {by_id_dir} not found. Will try fallback /dev/input/eventX paths."); sys.stdout.flush()

    if potential_keyboards:
        print(f"DEBUG: Selected keyboard from /dev/input/by-id/: {potential_keyboards[0]}"); sys.stdout.flush()
        return potential_keyboards[0]

    print("DEBUG: No suitable keyboard in /dev/input/by-id/. Trying /dev/input/eventX..."); sys.stdout.flush()
    for i in range(10): # Check event0 through event9
        event_path = f"/dev/input/event{i}"
        if os.path.exists(event_path):
            try:
                dev = InputDevice(event_path)
                # Check if it has key event capabilities and some common keys
                if ecodes.EV_KEY in dev.capabilities(verbose=False):
                    keys = dev.capabilities(verbose=False).get(ecodes.EV_KEY, [])
                    # A simple check for Q, A, Z keys to guess if it's a keyboard
                    if ecodes.KEY_Q in keys and ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
                        print(f"DEBUG: Found potential keyboard at fallback path: {event_path}"); sys.stdout.flush()
                        dev.close()
                        return event_path
                dev.close()
            except Exception: # Permissions error, or not a device evdev can handle
                pass

    print("DEBUG: No keyboard devices found in /dev/input/by-id/ or common /dev/input/eventX paths."); sys.stdout.flush()
    return None


# --- Pygame Initialization ---
try:
    print("DEBUG: Initializing Pygame..."); sys.stdout.flush()
    pygame.init()
    if not pygame.font.get_init():
        print("DEBUG: Pygame font not initialized by pygame.init(), trying pygame.font.init()..."); sys.stdout.flush()
        pygame.font.init()
    if not pygame.font.get_init():
        print("CRITICAL: Pygame font module could not be initialized."); sys.stdout.flush()
        sys.exit("Pygame font init failed")
    print("DEBUG: Pygame initialized successfully."); sys.stdout.flush()
except pygame.error as e:
    print(f"DEBUG: Pygame init error: {e}"); sys.stdout.flush()
    # Attempt to initialize font module separately if main init failed (common in headless)
    if not pygame.font.get_init():
        try:
            pygame.font.init()
            if not pygame.font.get_init(): raise RuntimeError("Fallback font init failed")
            print("DEBUG: Pygame font module initialized via fallback."); sys.stdout.flush()
        except Exception as font_e:
            print(f"CRITICAL: Pygame font module could not be initialized even with fallback: {font_e}"); sys.stdout.flush()
            sys.exit("Pygame font init failed")
    else:
        print("DEBUG: Pygame font was already initialized despite main init error (normal for headless)."); sys.stdout.flush()

# --- Global Server Variables ---
httpd_server = None
server_thread = None

# --- Evdev Keyboard Setup ---
KEYBOARD_DEVICE_PATH = find_keyboard_device_path()
keyboard = None

if not KEYBOARD_DEVICE_PATH:
    print(f"DEBUG: ERROR: No suitable keyboard device path was automatically detected."); sys.stdout.flush()
    sys.exit("Keyboard auto-detection failed")
try:
    print(f"DEBUG: Attempting to use keyboard device: {KEYBOARD_DEVICE_PATH}"); sys.stdout.flush()
    keyboard = InputDevice(KEYBOARD_DEVICE_PATH)
    print(f"DEBUG: Keyboard InputDevice created for {KEYBOARD_DEVICE_PATH}"); sys.stdout.flush()
    keyboard.grab() # Exclusive access to the keyboard
    print(f"DEBUG: Keyboard grabbed: {keyboard.name} at {KEYBOARD_DEVICE_PATH}"); sys.stdout.flush()
except FileNotFoundError:
    print(f"DEBUG: ERROR: Keyboard device not found at {KEYBOARD_DEVICE_PATH} (even after auto-detection)."); sys.stdout.flush()
    sys.exit("Keyboard not found")
except Exception as e:
    print(f"DEBUG: ERROR: Could not open keyboard device {KEYBOARD_DEVICE_PATH}: {e}"); sys.stdout.flush()
    sys.exit("Keyboard error")

# --- Keycode to Character Mapping (with Shift) ---
KEY_MAP = {
    ecodes.KEY_A: {'unshifted': 'a', 'shifted': 'A'}, ecodes.KEY_B: {'unshifted': 'b', 'shifted': 'B'},
    ecodes.KEY_C: {'unshifted': 'c', 'shifted': 'C'}, ecodes.KEY_D: {'unshifted': 'd', 'shifted': 'D'},
    ecodes.KEY_E: {'unshifted': 'e', 'shifted': 'E'}, ecodes.KEY_F: {'unshifted': 'f', 'shifted': 'F'},
    ecodes.KEY_G: {'unshifted': 'g', 'shifted': 'G'}, ecodes.KEY_H: {'unshifted': 'h', 'shifted': 'H'},
    ecodes.KEY_I: {'unshifted': 'i', 'shifted': 'I'}, ecodes.KEY_J: {'unshifted': 'j', 'shifted': 'J'},
    ecodes.KEY_K: {'unshifted': 'k', 'shifted': 'K'}, ecodes.KEY_L: {'unshifted': 'l', 'shifted': 'L'},
    ecodes.KEY_M: {'unshifted': 'm', 'shifted': 'M'}, ecodes.KEY_N: {'unshifted': 'n', 'shifted': 'N'},
    ecodes.KEY_O: {'unshifted': 'o', 'shifted': 'O'}, ecodes.KEY_P: {'unshifted': 'p', 'shifted': 'P'},
    ecodes.KEY_Q: {'unshifted': 'q', 'shifted': 'Q'},
    ecodes.KEY_R: {'unshifted': 'r', 'shifted': 'R'},
    ecodes.KEY_S: {'unshifted': 's', 'shifted': 'S'}, ecodes.KEY_T: {'unshifted': 't', 'shifted': 'T'},
    ecodes.KEY_U: {'unshifted': 'u', 'shifted': 'U'}, ecodes.KEY_V: {'unshifted': 'v', 'shifted': 'V'},
    ecodes.KEY_W: {'unshifted': 'w', 'shifted': 'W'},
    ecodes.KEY_X: {'unshifted': 'x', 'shifted': 'X'},
    ecodes.KEY_Y: {'unshifted': 'y', 'shifted': 'Y'}, ecodes.KEY_Z: {'unshifted': 'z', 'shifted': 'Z'},
    ecodes.KEY_1: {'unshifted': '1', 'shifted': '!'}, ecodes.KEY_2: {'unshifted': '2', 'shifted': '@'},
    ecodes.KEY_3: {'unshifted': '3', 'shifted': '#'}, ecodes.KEY_4: {'unshifted': '4', 'shifted': '$'},
    ecodes.KEY_5: {'unshifted': '5', 'shifted': '%'}, ecodes.KEY_6: {'unshifted': '6', 'shifted': '^'},
    ecodes.KEY_7: {'unshifted': '7', 'shifted': '&'}, ecodes.KEY_8: {'unshifted': '8', 'shifted': '*'},
    ecodes.KEY_9: {'unshifted': '9', 'shifted': '('}, ecodes.KEY_0: {'unshifted': '0', 'shifted': ')'},
    ecodes.KEY_MINUS: {'unshifted': '-', 'shifted': '_'},
    ecodes.KEY_EQUAL: {'unshifted': '=', 'shifted': '+'},
    ecodes.KEY_LEFTBRACE: {'unshifted': '[', 'shifted': '{'},
    ecodes.KEY_RIGHTBRACE: {'unshifted': ']', 'shifted': '}'},
    ecodes.KEY_BACKSLASH: {'unshifted': '\', 'shifted': '|'},
    ecodes.KEY_SEMICOLON: {'unshifted': ';', 'shifted': ':'},
    ecodes.KEY_APOSTROPHE: {'unshifted': "'", 'shifted': '"'},
    ecodes.KEY_GRAVE: {'unshifted': '`', 'shifted': '~'},
    ecodes.KEY_COMMA: {'unshifted': ',', 'shifted': '<'},
    ecodes.KEY_DOT: {'unshifted': '.', 'shifted': '>'},
    ecodes.KEY_SLASH: {'unshifted': '/', 'shifted': '?'},
    ecodes.KEY_SPACE: ' ',
    ecodes.KEY_ENTER: 'ENTER', ecodes.KEY_BACKSPACE: 'BACKSPACE', ecodes.KEY_ESC: 'ESCAPE_KEY',
    ecodes.KEY_LEFTSHIFT: 'LSHIFT', ecodes.KEY_RIGHTSHIFT: 'RSHIFT',
    ecodes.KEY_F1: 'WORD_COUNT_HOTKEY',
    ecodes.KEY_F2: 'TIME_DISPLAY_HOTKEY',
    ecodes.KEY_PAGEUP: 'PAGE_UP',
    ecodes.KEY_PAGEDOWN: 'PAGE_DOWN',
}

# --- Text Wrapping Function ---
def wrap_text(text, font, max_width):
    lines = []
    if not text: return [""]
    words = text.split(' ')
    current_line = ''
    for word_idx, word in enumerate(words):
        if not word and not current_line and word_idx < len(words) -1:
            current_line += ' '
            continue

        test_line = current_line + (' ' if current_line and current_line[-1] != ' ' else '') + word

        if font.size(test_line)[0] <= max_width:
            current_line = test_line
        else:
            if current_line: lines.append(current_line)
            current_line = word
            if font.size(current_line)[0] > max_width:
                temp_long_word_line = ""
                for char_val in current_line:
                    if font.size(temp_long_word_line + char_val)[0] <= max_width:
                        temp_long_word_line += char_val
                    else:
                        if temp_long_word_line: lines.append(temp_long_word_line)
                        temp_long_word_line = char_val
                if temp_long_word_line: lines.append(temp_long_word_line)
                current_line = ""
    if current_line or (not lines and text.strip() == "" and text != ""):
        lines.append(current_line)

    return lines if lines else [""]

# --- EPD Display Class ---
class EPDDisplay:
    JOURNAL_ARCHIVE_SUBFOLDER = "JournalArchive"
    PROJECT_ARCHIVE_SUBFOLDER = "ProjectArchive"
    MONTHLY_LOGS_SUBFOLDER = "MonthlyLogs"
    instance = None

    def __init__(self):
        EPDDisplay.instance = self
        print("DEBUG: EPDDisplay __init__ started"); sys.stdout.flush()
        time.sleep(0.5)
        self.epd = None; self.simulated_display = False
        try:
            print("DEBUG: Attempting EPD hardware object creation..."); sys.stdout.flush()
            self.epd = epd4in2_V2.EPD()
            print("DEBUG: EPD object created. Initializing EPD hardware..."); sys.stdout.flush()
            self.epd.init()
            print("DEBUG: EPD hardware initialized. Clearing display once."); sys.stdout.flush()
            self.epd.Clear()
            self.width = self.epd.width; self.height = self.epd.height
            print(f"DEBUG: E-ink display HAL found: {self.width}x{self.height}"); sys.stdout.flush()
        except Exception as e:
            print(f"DEBUG: Error initializing e-ink hardware object: {e}
Running in simulation mode."); sys.stdout.flush()
            self.width = 400; self.height = 300; self.simulated_display = True
        self.screen = pygame.Surface((self.width, self.height))
        print(f"DEBUG: Pygame surface created for EPD: {self.width}x{self.height}"); sys.stdout.flush()

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"DEBUG: Script base directory: {self.base_dir}"); sys.stdout.flush()

        font_path_primary_custom = '/usr/local/share/fonts/custom/CyrillicOld.otf'
        font_path_serif_system = '/usr/share/fonts/truetype/pt-serif/PT_Serif-Regular.ttf'
        font_path_dejavu_serif = '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf'

        primary_font_file = font_path_primary_custom if os.path.exists(font_path_primary_custom) else \
                            font_path_serif_system if os.path.exists(font_path_serif_system) else \
                            font_path_dejavu_serif if os.path.exists(font_path_dejavu_serif) else None

        body_serif_font_file = font_path_serif_system if os.path.exists(font_path_serif_system) else \
                                    font_path_dejavu_serif if os.path.exists(font_path_dejavu_serif) else None

        default_font_name = pygame.font.get_default_font() if pygame.font.get_init() else "sans"
        print(f"DEBUG: Fonts: Primary='{primary_font_file}', BodySerif='{body_serif_font_file}', PygameDefault='{default_font_name}'"); sys.stdout.flush()

        try:
            self.font_display_title = pygame.font.Font(primary_font_file, 70)
            self.font_shutdown_brand_accent = pygame.font.Font(primary_font_file, 14)
            self.font_main_heading = pygame.font.Font(primary_font_file, 36)
            self.font_main_menu_serif_item = pygame.font.Font(body_serif_font_file, 26)
            self.font_list_item = pygame.font.Font(primary_font_file, 25)
            self.font_editor_text = pygame.font.Font(body_serif_font_file, 20)
            self.font_date_text = pygame.font.Font(body_serif_font_file, 18)
            self.font_quote_serif = pygame.font.Font(body_serif_font_file, 16)
            self.font_attribution_serif = pygame.font.Font(body_serif_font_file, 14)
            self.font_url_display = pygame.font.Font(body_serif_font_file, 22)
            self.font_body_standard = pygame.font.Font(body_serif_font_file, 16)
            self.font_word_count_legacy = pygame.font.Font(body_serif_font_file, 14) # Kept if needed elsewhere, but indicators use new font
            self.font_status_indicator = pygame.font.Font(body_serif_font_file, 12) # New font for indicators
            self.font_bottom_directive_unified = pygame.font.Font(body_serif_font_file, 12)
            print("DEBUG: Custom fonts loaded with new sizes."); sys.stdout.flush()
        except pygame.error as e:
            print(f"DEBUG: Warning: Font loading error. Using SysFont. Error: {e}"); sys.stdout.flush()
            self.font_display_title = pygame.font.SysFont(default_font_name, 70)
            self.font_shutdown_brand_accent = pygame.font.SysFont(default_font_name, 14)
            self.font_main_heading = pygame.font.SysFont(default_font_name, 36)
            self.font_main_menu_serif_item = pygame.font.SysFont(default_font_name, 26)
            self.font_list_item = pygame.font.SysFont(default_font_name, 25)
            self.font_quote_serif = pygame.font.SysFont(default_font_name, 16)
            self.font_attribution_serif = pygame.font.SysFont(default_font_name, 14)
            self.font_editor_text = pygame.font.SysFont(default_font_name, 20)
            self.font_date_text = pygame.font.SysFont(default_font_name, 18)
            self.font_url_display = pygame.font.SysFont(default_font_name, 22)
            self.font_body_standard = pygame.font.SysFont(default_font_name, 16)
            self.font_word_count_legacy = pygame.font.SysFont(default_font_name, 14)
            self.font_status_indicator = pygame.font.SysFont(default_font_name, 12) # Fallback for new font
            self.font_bottom_directive_unified = pygame.font.SysFont(default_font_name, 12)
            print("DEBUG: Default SysFonts loaded with new sizes."); sys.stdout.flush()

        self.save_indicator_active = False; self.save_indicator_timer = 0
        self.word_count_active = False; self.word_count_timer = 0; self.current_word_count_text = ""
        self.time_display_active = False
        self.time_display_timer = 0
        self.current_time_text = ""
        self.shift_pressed = False
        self.editor_view_top_doc_line = 0
        self.num_displayable_screen_lines = 10

        self.projects_dir = os.path.join(self.base_dir, PROJECTS_ROOT_FOLDER)
        self.assets_dir = os.path.join(self.base_dir, ASSETS_FOLDER)
        self.monthly_logs_dir = os.path.join(self.projects_dir, self.MONTHLY_LOGS_SUBFOLDER)

        os.makedirs(self.projects_dir, exist_ok=True)
        os.makedirs(os.path.join(self.projects_dir, self.JOURNAL_ARCHIVE_SUBFOLDER), exist_ok=True)
        os.makedirs(os.path.join(self.projects_dir, self.PROJECT_ARCHIVE_SUBFOLDER), exist_ok=True)
        os.makedirs(self.assets_dir, exist_ok=True)
        os.makedirs(self.monthly_logs_dir, exist_ok=True)

        self._ensure_project_files_exist()
        print("DEBUG: EPDDisplay __init__ finished"); sys.stdout.flush()

    def _ensure_project_files_exist(self):
        print("DEBUG: Ensuring project files exist..."); sys.stdout.flush()
        project_files_found = 0
        for f_name in os.listdir(self.projects_dir):
            full_path = os.path.join(self.projects_dir, f_name)
            if os.path.isfile(full_path) and f_name.endswith(".txt"):
                if self.JOURNAL_ARCHIVE_SUBFOLDER in os.path.normpath(full_path) or \
                   self.PROJECT_ARCHIVE_SUBFOLDER in os.path.normpath(full_path) or \
                   self.MONTHLY_LOGS_SUBFOLDER in os.path.normpath(full_path) or \
                   (len(f_name) == 14 and f_name[4] == '-' and f_name[7] == '-' and f_name[:4].isdigit()):
                    continue

                if f_name.lower() != "daily journal.txt":
                    project_files_found +=1

        for i in range(1, 4):
            if project_files_found < 3:
                project_file_path = os.path.join(self.projects_dir, f"Project {i}.txt")
                if not os.path.exists(project_file_path):
                    with open(project_file_path, 'w', encoding='utf-8') as f: f.write("")
                    print(f"DEBUG: Created default file: {project_file_path}"); sys.stdout.flush()
                    project_files_found +=1
            else:
                break
        print("DEBUG: Project file check complete."); sys.stdout.flush()

    def clear(self): self.screen.fill((255, 255, 255))

    def display_full(self):
        if self.epd and not self.simulated_display:
            try:
                print("DEBUG: display_full - Calling epd.init() for full refresh"); sys.stdout.flush()
                self.epd.init()
                print("DEBUG: display_full - Clearing EPD with epd.Clear()"); sys.stdout.flush()
                self.epd.Clear()

                pil_image_str = pygame.image.tostring(self.screen, "RGB", False)
                pil_image = Image.frombytes("RGB", (self.width, self.height), pil_image_str)
                pil_image_1bit = pil_image.convert('1')
                eink_buffer = self.epd.getbuffer(pil_image_1bit)

                print("DEBUG: display_full - Calling epd.display()"); sys.stdout.flush()
                self.epd.display(eink_buffer)
                time.sleep(FULL_REFRESH_SLEEP)
            except Exception as e: print(f"DEBUG: Error in display_full: {e}"); import traceback; traceback.print_exc()
        else: print("SIM DEBUG: display_full (simulated or no epd)")

    def display_partial(self):
        if self.epd and not self.simulated_display:
            try:
                pil_image_str = pygame.image.tostring(self.screen, "RGB", False)
                pil_image = Image.frombytes("RGB", (self.width, self.height), pil_image_str)
                pil_image_1bit = pil_image.convert('1')
                eink_buffer = self.epd.getbuffer(pil_image_1bit)
                self.epd.display_Partial(eink_buffer)
                time.sleep(DISPLAY_PARTIAL_SLEEP)
            except Exception as e: print(f"DEBUG: Error in display_partial: {e}"); import traceback; traceback.print_exc()
        else: print("SIM DEBUG: display_partial (simulated or no epd)")

    def draw_text(self, x, y, text, font, color=(0, 0, 0), max_w_override=None):
        wrap_w = max_w_override if max_w_override is not None else self.width - x - TEXT_MARGIN
        wrapped_lines = wrap_text(text, font, wrap_w)
        current_y = y
        for i,line in enumerate(wrapped_lines):
            if current_y + font.get_linesize() > self.height: break
            text_surface = font.render(line, True, color)
            self.screen.blit(text_surface, (x, current_y))
            current_y += font.get_linesize()
        return current_y

    def draw_text_centered(self, start_y, text, font, color=(0, 0, 0)):
        wrapped_lines = wrap_text(text, font, self.width - 2 * TEXT_MARGIN)
        current_y = start_y
        if not wrapped_lines: return start_y
        for i,line in enumerate(wrapped_lines):
            if current_y + font.get_linesize() > self.height - TEXT_MARGIN: break
            text_surface = font.render(line, True, color)
            text_rect = text_surface.get_rect(centerx=self.width // 2, top=current_y)
            self.screen.blit(text_surface, text_rect)
            current_y += font.get_linesize()
        return current_y

    def show_main_menu(self):
        self.clear()
        title_text = "Hello, Ada."
        title_font = self.font_display_title
        title_wrapped = wrap_text(title_text, title_font, self.width - 2 * TEXT_MARGIN)
        title_block_height = len(title_wrapped) * title_font.get_linesize()
        hello_ada_y_start = (self.height // 3) - title_block_height // 2
        if hello_ada_y_start < 20: hello_ada_y_start = 20
        y_after_title = self.draw_text_centered(hello_ada_y_start, title_text, title_font)

        menu_items_main = [ ("1. Daily Journal", self.font_main_menu_serif_item),
                            ("2. Projects", self.font_main_menu_serif_item),
                            ("3. Wi-Fi Settings", self.font_main_menu_serif_item) ] # New item
        menu_y_pos = y_after_title + 40 + self.font_main_menu_serif_item.get_linesize()
        item_spacing = 30
        rendered_items = []
        total_width_of_items = 0
        for text, font in menu_items_main:
            surf = font.render(text, True, (0,0,0))
            rendered_items.append(surf)
            total_width_of_items += surf.get_width()

        if rendered_items:
            total_width_needed = total_width_of_items + item_spacing * (len(rendered_items) - 1 if len(rendered_items)>0 else 0)
            current_x = (self.width - total_width_needed) // 2
            for surf in rendered_items:
                self.screen.blit(surf, (current_x, menu_y_pos))
                current_x += surf.get_width() + item_spacing

        bottom_item1_text = "W to Wi-Fi Transfer"
        bottom_item2_text = "Q to Quit"
        font_for_bottom = self.font_bottom_directive_unified

        surf_b1 = font_for_bottom.render(bottom_item1_text, True, (0,0,0))
        surf_b2 = font_for_bottom.render(bottom_item2_text, True, (0,0,0))
        bottom_gap_width = 20
        bottom_block_total_width = surf_b1.get_width() + surf_b2.get_width() + bottom_gap_width
        bottom_start_x = (self.width - bottom_block_total_width) // 2
        bottom_y_pos = self.height - font_for_bottom.get_linesize() - 10

        if bottom_start_x < TEXT_MARGIN or (surf_b1.get_width() + surf_b2.get_width() + bottom_gap_width > self.width - 2*TEXT_MARGIN):
                      self.draw_text_centered(self.height - (font_for_bottom.get_linesize() * 2) - 10 - 2, bottom_item1_text, font_for_bottom)
                      self.draw_text_centered(self.height - font_for_bottom.get_linesize() - 10, bottom_item2_text, font_for_bottom)
        else:
            self.screen.blit(surf_b1, (bottom_start_x, bottom_y_pos))
            self.screen.blit(surf_b2, (bottom_start_x + surf_b1.get_width() + bottom_gap_width, bottom_y_pos))

        self.display_full()

    def show_journal(self):
        today_dt = date.today(); today_filename_str = today_dt.strftime("%Y-%m-%d")
        archive_path = os.path.join(self.projects_dir, self.JOURNAL_ARCHIVE_SUBFOLDER)
        os.makedirs(archive_path, exist_ok=True)
        todays_journal_path = os.path.join(archive_path, f"{today_filename_str}.txt")
        editor_main_title = "Daily Journal"
        date_for_display = today_dt.strftime('%B %d, %Y')
        self.edit_project(todays_journal_path, editor_title=editor_main_title, date_str_for_display=date_for_display, is_journal=True)

    def _get_project_files(self):
        project_files = []
        for f_name in os.listdir(self.projects_dir):
            full_path = os.path.join(self.projects_dir, f_name)
            if os.path.isfile(full_path) and f_name.endswith(".txt"):
                if self.JOURNAL_ARCHIVE_SUBFOLDER in os.path.normpath(full_path) or \
                   self.PROJECT_ARCHIVE_SUBFOLDER in os.path.normpath(full_path) or \
                   self.MONTHLY_LOGS_SUBFOLDER in os.path.normpath(full_path) :
                    continue
                try:
                    date.fromisoformat(f_name[:10])
                    if len(f_name) == 14 and f_name[4] == '-' and f_name[7] == '-':
                        continue
                except ValueError: pass

                if f_name.lower() != "daily journal.txt":
                    project_files.append(f_name)
        project_files.sort()
        return project_files

    def show_projects_list(self):
        while True:
            self.clear();
            y_after_title = self.draw_text_centered(15, "Projects", self.font_main_heading)

            displayed_projects_files = self._get_project_files()[:3]
            project_display_names = [f"{i+1}. {os.path.splitext(f)[0]}" for i, f in enumerate(displayed_projects_files)]

            font_for_directives = self.font_bottom_directive_unified
            num_items = len(project_display_names); item_font = self.font_list_item
            item_height_est = item_font.get_linesize() + 5
            total_block_height = num_items * (item_height_est + 25)

            header_total_height = y_after_title + 15
            footer_total_height = font_for_directives.get_linesize() * 2 + 30
            available_height_for_list = self.height - header_total_height - footer_total_height
            start_y_projects = header_total_height + max(0, (available_height_for_list - total_block_height) // 2)

            if not displayed_projects_files:
                self.draw_text_centered(self.height // 2, "No projects found.", self.font_body_standard)
                self.draw_text_centered(self.height - font_for_directives.get_linesize() - 10, "ESC to return", font_for_directives)
                self.display_full(); self.wait_for_back(); return

            current_y = start_y_projects
            for name in project_display_names:
                y_after_item = self.draw_text_centered(current_y, name, item_font)
                current_y = y_after_item + 25

            directive_line1 = "1-3 to Open, R to Rename"
            directive_line2 = "A to Archive, D to Delete, ESC to Return"

            bottom_y_instr = self.height - (font_for_directives.get_linesize() * 2) - 10 - 2
            self.draw_text_centered(bottom_y_instr, directive_line1, font_for_directives)
            self.draw_text_centered(bottom_y_instr + font_for_directives.get_linesize() + 2, directive_line2, font_for_directives)

            self.display_full()

            valid_keys_map = { ecodes.KEY_1: 0, ecodes.KEY_2: 1, ecodes.KEY_3: 2,
                                 ecodes.KEY_R: 'RENAME', ecodes.KEY_A: 'ARCHIVE', ecodes.KEY_D: 'DELETE' }
            choice_key_code = self.wait_for_direct_choice(list(valid_keys_map.keys()) + [ecodes.KEY_ESC])

            if choice_key_code == ecodes.KEY_ESC: return
            elif choice_key_code == ecodes.KEY_R: self.rename_project_menu(displayed_projects_files); continue
            elif choice_key_code == ecodes.KEY_A: self.archive_project_menu(displayed_projects_files); continue
            elif choice_key_code == ecodes.KEY_D: self.delete_project_menu(displayed_projects_files); continue
            else:
                try:
                    choice_idx = valid_keys_map.get(choice_key_code)
                    if choice_idx is not None and 0 <= choice_idx < len(displayed_projects_files):
                        chosen_file_name = displayed_projects_files[choice_idx]
                        editor_title = os.path.splitext(os.path.basename(chosen_file_name))[0]
                        self.edit_project(os.path.join(self.projects_dir, chosen_file_name), editor_title=editor_title)
                        return # Return to main menu after editing a project
                    else: self.show_message("Invalid choice.", 2, do_full_refresh=False)
                except Exception as e: self.show_message(f"Project Error: {e}", 3, do_full_refresh=False)

    def _handle_project_action(self, action_name_display, action_verb_present, action_verb_past, current_project_files):
        self.clear()
        y_after_title = self.draw_text_centered(15, f"{action_name_display} Project", self.font_main_heading)

        if not current_project_files:
            self.show_message(f"No projects to {action_name_display.lower()}.", 2, do_full_refresh=False); return

        project_display_names = [f"{i+1}. {os.path.splitext(f)[0]}" for i, f in enumerate(current_project_files)]
        font_for_directive = self.font_bottom_directive_unified

        num_items = len(project_display_names); item_font = self.font_list_item
        item_height_est = item_font.get_linesize() + 5
        total_block_height = num_items * (item_height_est + 20)
        header_total_height = y_after_title + 15
        footer_total_height = font_for_directive.get_linesize() + 20
        available_height_for_list = self.height - header_total_height - footer_total_height
        start_y_projects = header_total_height + max(0, (available_height_for_list - total_block_height) // 2)

        current_y = start_y_projects
        for name in project_display_names: current_y = self.draw_text_centered(current_y, name, item_font) + 20

        directive_text = f"1-{len(current_project_files)} to Select, ESC to Cancel"
        self.draw_text_centered(self.height - font_for_directive.get_linesize() - 10,
                                directive_text, font_for_directive)
        self.display_full()

        valid_choice_keys = [getattr(ecodes, f"KEY_{i+1}") for i in range(len(current_project_files))] + [ecodes.KEY_ESC]
        key_map_idx = {getattr(ecodes, f"KEY_{i+1}"):i for i in range(len(current_project_files))}

        choice_key = self.wait_for_direct_choice(valid_choice_keys)
        if choice_key == ecodes.KEY_ESC: return

        selected_idx = key_map_idx.get(choice_key)
        if selected_idx is None or not (0 <= selected_idx < len(current_project_files)):
            self.show_message("Invalid selection.", 1, do_full_refresh=False); return

        chosen_filename = current_project_files[selected_idx]
        chosen_filepath = os.path.join(self.projects_dir, chosen_filename)

        confirm_prompt_text = f"{action_verb_present} '{os.path.splitext(chosen_filename)[0]}'? (Y/N)"
        if action_name_display == "Delete": confirm_prompt_text = f"DELETE '{os.path.splitext(chosen_filename)[0]}' PERMANENTLY? (Y/N)"

        self.show_message(confirm_prompt_text, duration_sec=0, do_full_refresh=False)
        confirm_key = self.wait_for_direct_choice([ecodes.KEY_Y, ecodes.KEY_N, ecodes.KEY_ESC])

        if confirm_key == ecodes.KEY_Y:
            if action_name_display == "Delete":
                self.show_message("ARE YOU SURE? (Y/N)", duration_sec=0, do_full_refresh=False)
                final_confirm_key = self.wait_for_direct_choice([ecodes.KEY_Y, ecodes.KEY_N, ecodes.KEY_ESC])
                if final_confirm_key != ecodes.KEY_Y:
                    self.show_message(f"{action_name_display} cancelled.", 1, do_full_refresh=False); return
            try:
                if action_name_display == "Archive":
                    archive_dir = os.path.join(self.projects_dir, self.PROJECT_ARCHIVE_SUBFOLDER)
                    os.makedirs(archive_dir, exist_ok=True)
                    base, ext = os.path.splitext(chosen_filename)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    archive_filename_candidate = f"{base} (archived {timestamp}){ext}"
                    archive_filepath = os.path.join(archive_dir, archive_filename_candidate)
                    count = 0
                    while os.path.exists(archive_filepath):
                        count += 1
                        archive_filename_candidate = f"{base} (archived {timestamp}_{count}){ext}"
                        archive_filepath = os.path.join(archive_dir, archive_filename_candidate)
                    os.rename(chosen_filepath, archive_filepath)
                    self.show_message(f"'{base}' {action_verb_past.lower()}.", 2, do_full_refresh=False)
                elif action_name_display == "Delete":
                    os.remove(chosen_filepath)
                    self.show_message(f"'{os.path.splitext(chosen_filename)[0]}' deleted.", 2, do_full_refresh=False)
                self._ensure_project_files_exist(); # Refresh available project slots if needed
            except Exception as e: self.show_message(f"Error: {e}", 3, do_full_refresh=False)
        else: self.show_message(f"{action_name_display} cancelled.", 1, do_full_refresh=False)

    def archive_project_menu(self, project_file_list): self._handle_project_action("Archive", "Archiving", "archived", project_file_list)
    def delete_project_menu(self, project_file_list): self._handle_project_action("Delete", "Deleting", "deleted", project_file_list)

    def rename_project_menu(self, current_project_files):
        while True:
            self.clear(); y_after_title = self.draw_text_centered(15, "Rename Project", self.font_main_heading)

            renamable_projects_to_display = current_project_files[:3] # Only allow renaming first 3 displayed
            project_display_names = [f"{i+1}. {os.path.splitext(f)[0]}" for i, f in enumerate(renamable_projects_to_display)]

            start_y_projects = y_after_title + 20
            if not renamable_projects_to_display:
                self.draw_text_centered(self.height // 2, "No projects to rename.", self.font_body_standard)
            else:
                current_y = start_y_projects
                for name in project_display_names: current_y = self.draw_text_centered(current_y, name, self.font_list_item) + 20

            font_for_directive = self.font_bottom_directive_unified
            self.draw_text_centered(self.height - font_for_directive.get_linesize() - 10, "ESC to return", font_for_directive)
            self.display_full()

            if not renamable_projects_to_display: self.wait_for_back(); return

            valid_keys_map = {ecodes.KEY_1: 0, ecodes.KEY_2: 1, ecodes.KEY_3: 2}
            choice_key_code = self.wait_for_direct_choice(list(valid_keys_map.keys()) + [ecodes.KEY_ESC])

            if choice_key_code == ecodes.KEY_ESC: return

            try:
                choice_idx = valid_keys_map.get(choice_key_code)
                if choice_idx is not None and 0 <= choice_idx < len(renamable_projects_to_display):
                    old_file_name = renamable_projects_to_display[choice_idx]
                    old_file_path = os.path.join(self.projects_dir, old_file_name)
                    prompt_text = f"New name for '{os.path.splitext(old_file_name)[0]}':"

                    new_name_input = self.get_text_input_overlay(prompt_text)

                    if new_name_input == "ESCAPE_KEY":
                        self.show_message("Rename cancelled.", 1, do_full_refresh=False); continue
                    if not new_name_input.strip():
                        self.show_message("Name cannot be empty.", 2, do_full_refresh=False); continue

                    new_file_base = new_name_input.strip(); new_file_name_only = new_file_base + ".txt"
                    new_file_path = os.path.join(self.projects_dir, new_file_name_only)

                    if os.path.exists(new_file_path) and old_file_path.lower() != new_file_path.lower() :
                        self.show_message(f"'{new_file_base}' already exists.", 2, do_full_refresh=False)
                    else:
                        os.rename(old_file_path, new_file_path)
                        self.show_message(f"Renamed to '{new_file_base}'.", 2, do_full_refresh=False)
                        return # Return to project list after successful rename
                else: self.show_message("Invalid number.", 2, do_full_refresh=False)
            except Exception as e: self.show_message(f"Rename Error: {e}", 3, do_full_refresh=False)

    def edit_project(self, file_path, editor_title=None, date_str_for_display=None, is_journal=False):
        lines_from_file = []
        new_file_created = False
        try:
            file_dir = os.path.dirname(file_path)
            if file_dir and not os.path.exists(file_dir): os.makedirs(file_dir, exist_ok=True)
            with open(file_path, 'r', encoding='utf-8') as f: lines_from_file = f.read().splitlines()
        except FileNotFoundError:
            lines_from_file = [""] # Start with a single empty line for new files
            new_file_created = True
        except IOError as e: self.show_message(f"Error reading file: {e}", 3, do_full_refresh=False); return

        lines = list(lines_from_file) # Make a mutable copy

        if is_journal:
            # If it's a new file, add the date header
            if new_file_created and date_str_for_display:
                lines = [date_str_for_display, ""] # Overwrite initial empty line

            # For any journal session, add a timestamp for the new session
            # Add a separator if there's already content and the last line isn't empty.
            if lines and lines[-1].strip() != "":
                    lines.append("") # Add a blank line for separation

            current_time_str = datetime.now().strftime("%I:%M %p")
            lines.append(f"--- {current_time_str} ---")
            lines.append("") # Add a blank line for the user to start typing.

        if not lines: lines.append("") # Ensure lines is never empty

        self.shift_pressed = False
        last_save_time = pygame.time.get_ticks()
        current_editor_title = editor_title if editor_title else os.path.splitext(os.path.basename(file_path))[0]

        # Initialize to scroll to the bottom (cursor position)
        self.editor_view_top_doc_line = len(lines) # Ensures bottom is visible

        self._draw_edit_screen(current_editor_title, lines, date_str_for_display, is_journal)
        self.display_full() # Initial full refresh

        last_displayed_lines_content = lines[:] # For partial update check
        running_editor = True
        while running_editor:
            global LAST_KEYBOARD_ACTIVITY_TIME, INACTIVITY_TIMEOUT_SECONDS
            if time.time() - LAST_KEYBOARD_ACTIVITY_TIME > INACTIVITY_TIMEOUT_SECONDS:
                print("DEBUG: Editor loop detected inactivity. Initiating shutdown.")
                sys.stdout.flush()
                self.initiate_shutdown() # This will exit
                return # Fallback return

            needs_display_update = False; text_was_modified = False # Reset flags each loop
            ready_to_read, _, _ = select.select([keyboard.fd], [], [], KEYBOARD_POLL_TIMEOUT)

            if keyboard.fd in ready_to_read:
                try:
                    for event in keyboard.read():
                        if event.type == ecodes.EV_KEY:
                            global LAST_KEYBOARD_ACTIVITY_TIME
                            LAST_KEYBOARD_ACTIVITY_TIME = time.time()
                            key_code = event.code
                            key_value = event.value # 0 for release, 1 for press, 2 for repeat

                            if key_code == ecodes.KEY_LEFTSHIFT or key_code == ecodes.KEY_RIGHTSHIFT:
                                self.shift_pressed = (key_value != 0) # True if pressed/repeated, False if released
                                continue # Don't process shift as a character

                            if key_value == 1 or key_value == 2: # Key down or repeat
                                needs_display_update = True # Assume any key press might change display
                                mapped_key_action = KEY_MAP.get(key_code)

                                if mapped_key_action == 'WORD_COUNT_HOTKEY':
                                    full_text = "
".join(lines)
                                    word_count = len(full_text.split()) if full_text.strip() else 0
                                    self.current_word_count_text = f"Word Count: {word_count}"
                                    self.word_count_active = True
                                    self.time_display_active = False # Mutually exclusive
                                    self.word_count_timer = pygame.time.get_ticks()
                                elif mapped_key_action == 'TIME_DISPLAY_HOTKEY':
                                    current_time_obj = datetime.now()
                                    # Use %I for 12-hour clock, %p for AM/PM
                                    self.current_time_text = current_time_obj.strftime("%I:%M:%S %p")
                                    self.time_display_active = True
                                    self.word_count_active = False # Mutually exclusive
                                    self.time_display_timer = pygame.time.get_ticks()
                                elif mapped_key_action == 'PAGE_UP':
                                    if self.editor_view_top_doc_line >= len(lines): # If already at bottom (or scrolled past)
                                        # Jump to a page above the current end
                                        self.editor_view_top_doc_line = max(0, len(lines) - self.num_displayable_screen_lines)
                                    # Regular scroll up
                                    scroll_amount = self.num_displayable_screen_lines // 2 or 1
                                    self.editor_view_top_doc_line = max(0, self.editor_view_top_doc_line - scroll_amount)
                                    text_was_modified = False # Scrolling isn't text modification
                                elif mapped_key_action == 'PAGE_DOWN':
                                    if self.editor_view_top_doc_line >= len(lines): continue # Already at/past bottom
                                    max_possible_top_idx = max(0, len(lines) -1) # Max index that can be the top line
                                    scroll_amount = self.num_displayable_screen_lines // 2 or 1
                                    new_top_line = min(max_possible_top_idx, self.editor_view_top_doc_line + scroll_amount)
                                    # If scrolling would take us to where the last few lines are visible, just go to end view
                                    if new_top_line >= max(0, len(lines) - self.num_displayable_screen_lines):
                                        self.editor_view_top_doc_line = len(lines) # Signal "view from bottom"
                                    else:
                                        self.editor_view_top_doc_line = new_top_line
                                    text_was_modified = False # Scrolling isn't text modification
                                elif key_code == ecodes.KEY_ENTER:
                                    lines.append(""); text_was_modified = True
                                elif key_code == ecodes.KEY_BACKSPACE:
                                    if lines and lines[-1]: lines[-1] = lines[-1][:-1]
                                    elif len(lines) > 1: lines.pop()
                                    # Ensure lines isn't empty, important for cursor logic
                                    if not lines: lines.append("")
                                    text_was_modified = True
                                elif key_code == ecodes.KEY_ESC:
                                    try:
                                        with open(file_path, 'w', encoding='utf-8') as f: f.write('
'.join(lines))
                                        if is_journal: # Only update monthly log for journals
                                            self._update_monthly_log(file_path, lines)
                                        self.show_message("Saved & Exiting", 1, do_full_refresh=False)
                                    except IOError as e: self.show_message(f"Error saving: {e}", 3, do_full_refresh=False)
                                    running_editor = False; break # Exit the for event loop
                                else: # Character input
                                    key_entry = KEY_MAP.get(key_code)
                                    char_to_add = None
                                    if key_entry:
                                        if isinstance(key_entry, dict): # Shiftable character
                                            char_to_add = key_entry['shifted'] if self.shift_pressed else key_entry['unshifted']
                                        elif isinstance(key_entry, str) and key_entry not in ['LSHIFT', 'RSHIFT', 'ENTER', 'BACKSPACE', 'ESCAPE_KEY', 'WORD_COUNT_HOTKEY', 'TIME_DISPLAY_HOTKEY', 'PAGE_UP', 'PAGE_DOWN']:
                                            char_to_add = key_entry # Non-shiftable, like space

                                    if char_to_add:
                                        lines[-1] += char_to_add; text_was_modified = True
                except BlockingIOError: # No events available, normal for non-blocking read
                    pass
                except Exception as e:
                    print(f"Editor input error: {e}") # Log other errors

            if text_was_modified: # If text changed, ensure view follows cursor (bottom of text)
                self.editor_view_top_doc_line = len(lines)

            if not running_editor: # This correctly breaks 'while running_editor' if ESC was pressed
                break

            # --- Auto-save and status indicator logic ---
            current_time = pygame.time.get_ticks()
            if current_time - last_save_time > AUTO_SAVE_INTERVAL:
                try:
                    with open(file_path, 'w', encoding='utf-8') as f: f.write('
'.join(lines))
                    last_save_time = current_time; self.save_indicator_active = True; self.save_indicator_timer = current_time
                    needs_display_update = True; print("DEBUG: Auto-saved.")
                except IOError as e: print(f"ERROR: Auto-save: {e}")

            # Manage timed indicators (save, word count, time)
            if self.save_indicator_active and (current_time - self.save_indicator_timer > AUTO_SAVE_INDICATOR_DURATION):
                self.save_indicator_active = False; needs_display_update = True
            if self.word_count_active and (current_time - self.word_count_timer > WORD_COUNT_DISPLAY_DURATION):
                self.word_count_active = False; needs_display_update = True
            if self.time_display_active and (current_time - self.time_display_timer > WORD_COUNT_DISPLAY_DURATION): # Uses same duration as word count
                self.time_display_active = False; needs_display_update = True

            if needs_display_update or lines != last_displayed_lines_content:
                self._draw_edit_screen(current_editor_title, lines, date_str_for_display, is_journal)
                self.display_partial(); last_displayed_lines_content = lines[:] # Update cache
            else: # No input and no display update needed, sleep briefly
                if not ready_to_read: # Only sleep if there was no input to process
                    time.sleep(0.005) # Short sleep to yield CPU

    def _update_monthly_log(self, daily_file_path, daily_lines):
        """
        Updates the monthly log file. It finds the entry for the given day and replaces it.
        If no entry for the day exists, it appends a new one.
        """
        try:
            daily_filename = os.path.basename(daily_file_path)
            entry_date_str = os.path.splitext(daily_filename)[0] # Should be YYYY-MM-DD
            year_month_str = entry_date_str[:7] # YYYY-MM
            monthly_log_filename = f"{year_month_str}.txt"
            monthly_log_filepath = os.path.join(self.monthly_logs_dir, monthly_log_filename)

            entry_header = f"--- {entry_date_str} ---"
            # Join the daily lines, ensuring no excessive newlines if daily_lines is empty/minimal
            new_content_for_day = "
".join(l for l in daily_lines if l.strip() or l == "") # Preserve intentional blank lines but filter out purely whitespace lines if desired
            full_new_entry = f"{entry_header}

{new_content_for_day}"

            all_log_content = ""
            if os.path.exists(monthly_log_filepath):
                with open(monthly_log_filepath, 'r', encoding='utf-8') as f:
                    all_log_content = f.read()

            # Split the log by entry headers
            # The separator is a regex looking for --- dddd-dd-dd ---
            # Make sure the regex captures the newline before the header for cleaner splitting
            entries = re.split(r'(
*--- \d{4}-\d{2}-\d{2} ---)', all_log_content)

            entry_found = False
            new_log_parts = []

            # The first part is anything before the first header or if the file is empty/no headers
            if entries[0]:
                new_log_parts.append(entries[0].strip("
")) # Avoid leading newlines if it's the start

            # Iterate through header/content pairs
            for i in range(1, len(entries), 2):
                header = entries[i].strip() # The captured header itself
                content = entries[i+1] # The content after this header

                if header == entry_header:
                    # This is the entry we want to replace. Don't add it here.
                    entry_found = True
                else:
                    # Keep this existing entry
                    new_log_parts.append(entries[i]) # The header (with its preceding newline)
                    new_log_parts.append(content) # The content

            # Add the new/updated entry. Ensure it's separated by a newline if there's existing content.
            if new_log_parts and "".join(new_log_parts).strip():
                 new_log_parts.append("

" + full_new_entry) # Add two newlines for separation before new entry
            else:
                 new_log_parts.append(full_new_entry) # This is the first entry

            # Reconstruct the log file content
            final_log_content = "".join(new_log_parts).strip("
") # Remove leading/trailing newlines from the whole doc

            with open(monthly_log_filepath, 'w', encoding='utf-8') as mf:
                mf.write(final_log_content + '
') # Ensure a final newline

            if entry_found:
                print(f"DEBUG: Updated entry in monthly log: {monthly_log_filepath}"); sys.stdout.flush()
            else:
                print(f"DEBUG: Appended new entry to monthly log: {monthly_log_filepath}"); sys.stdout.flush()

        except Exception as e:
            print(f"ERROR: Could not update monthly log: {e}"); sys.stdout.flush()
            import traceback
            traceback.print_exc()

    def _draw_edit_screen(self, title_text_to_display, lines, date_str_for_display=None, is_journal=False):
        self.clear()
        current_y_offset = 15 # Top margin
        current_y_offset = self.draw_text_centered(current_y_offset, title_text_to_display, self.font_main_heading)
        # No date display below title anymore, it's part of the journal content if applicable.

        content_start_y = current_y_offset + 20 # Space after title
        line_h = self.font_editor_text.get_linesize()
        directive_font = self.font_bottom_directive_unified
        directive_area_height = directive_font.get_linesize() + 15 + 5 # Height for bottom directive text

        available_text_height = self.height - content_start_y - directive_area_height
        self.num_displayable_screen_lines = max(1, int(available_text_height / line_h) if line_h > 0 else 1)

        screen_lines_to_display = []

        # Determine if rendering from bottom (cursor is at the end of document)
        # or from a specific top line (scrolled view)
        render_from_bottom = (self.editor_view_top_doc_line >= len(lines)) and lines

        if render_from_bottom:
            current_buffer_height = 0
            # Iterate document lines from last to first to fill screen from bottom up
            for doc_line_idx in range(len(lines) - 1, -1, -1):
                is_cursor_line = (doc_line_idx == len(lines) - 1) # Is this the line with the cursor?
                line_with_cursor = lines[doc_line_idx] + ("_" if is_cursor_line else "")
                wrapped_sub_lines = wrap_text(line_with_cursor, self.font_editor_text, self.width - 2 * TEXT_MARGIN)

                # Add wrapped lines from this document line, also from bottom up
                for sub_line_idx in range(len(wrapped_sub_lines) - 1, -1, -1):
                    sub_line = wrapped_sub_lines[sub_line_idx]
                    if current_buffer_height + line_h <= available_text_height:
                        screen_lines_to_display.insert(0, sub_line) # Add to beginning of screen lines
                        current_buffer_height += line_h
                    else: break # Screen buffer full
                if current_buffer_height >= available_text_height: break # Screen buffer full
        elif lines: # Rendering from a specific top_doc_line (scrolled view)
            current_buffer_height = 0
            start_idx = max(0, min(self.editor_view_top_doc_line, len(lines) -1 if lines else 0))
            for doc_line_idx in range(start_idx, len(lines)):
                line_content = lines[doc_line_idx]
                is_true_last_line_of_doc = (doc_line_idx == len(lines) - 1) # Is this the actual last line of the document?
                # Cursor only on the true last line of the document if we are not in a scrolled-up view
                # This needs to be smarter: cursor should be on the last line *being edited*, which is always lines[-1]
                # The self.editor_view_top_doc_line only affects *which part* of lines is visible.
                # For simplicity now, cursor is only shown if the view includes the very last line of the document.
                show_cursor_on_this_line = is_true_last_line_of_doc and (self.editor_view_top_doc_line + self.num_displayable_screen_lines >= len(lines))


                line_to_render = line_content + ("_" if show_cursor_on_this_line else "")
                wrapped_sub_lines = wrap_text(line_to_render, self.font_editor_text, self.width - 2 * TEXT_MARGIN)

                for sub_line in wrapped_sub_lines:
                    if current_buffer_height + line_h <= available_text_height:
                        screen_lines_to_display.append(sub_line)
                        current_buffer_height += line_h
                    else: break # Screen buffer full
                if current_buffer_height >= available_text_height: break # Screen buffer full
        else: # No lines in document
            screen_lines_to_display.append("_") # Just show cursor

        # Draw the collected screen lines
        current_draw_y = content_start_y
        for text_line_to_render in screen_lines_to_display:
            self.draw_text(TEXT_MARGIN, current_draw_y, text_line_to_render, self.font_editor_text)
            current_draw_y += line_h

        # Draw status indicators (Saved, Word Count, Time)
        indicator_text = None
        indicator_font = self.font_status_indicator # Using the new smaller font
        if self.word_count_active:
            indicator_text = self.current_word_count_text
        elif self.time_display_active:
            indicator_text = self.current_time_text
        elif self.save_indicator_active: # Save indicator has lowest priority
            indicator_text = "Saved"

        if indicator_text:
            indicator_surface = indicator_font.render(indicator_text, True, (0,0,0)) # Black text
            indicator_rect = indicator_surface.get_rect(topright=(self.width - TEXT_MARGIN - 5, TEXT_MARGIN + 3))
            self.screen.blit(indicator_surface, indicator_rect)

        # Draw bottom directive text
        directive_text = "ESC to Return, PgUp/Dn to Scroll, F1 for Word Count"
        self.draw_text_centered(self.height - directive_font.get_linesize() - 10, directive_text, directive_font)

    def get_local_ip(self):
        try:
            interfaces = netifaces.interfaces()
            for iface_name in interfaces:
                if iface_name == 'lo' or not iface_name.startswith(('eth', 'wlan')): continue
                addrs = netifaces.ifaddresses(iface_name)
                if netifaces.AF_INET in addrs:
                    for link in addrs[netifaces.AF_INET]:
                        ip = link['addr']
                        if not ip.startswith("127.") and not ip.startswith("169.254"): return ip
            # Fallback if no suitable interface found above
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(0.1)
            s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
            if not ip.startswith("127."): return ip # Check if it's a real IP
            return "No IP Found (Fallback)"
        except Exception as e: print(f"Error getting IP: {e}"); return "No IP (Error)"

    def start_wifi_transfer_server(self):
        global httpd_server, server_thread
        if httpd_server and server_thread and server_thread.is_alive():
            self._draw_wifi_screen_and_wait(); return # Server already running

        ip_address = self.get_local_ip()
        if "No IP" in ip_address : self.show_message(f"IP Error: {ip_address}. Check Wi-Fi.", 3, do_full_refresh=False); return

        class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
            DIRECTORY_FRIENDLY_NAMES = {
                "JournalArchive": "Journal Archive",
                "MonthlyLogs": "Monthly Journals",
                "ProjectArchive": "Project Archives"
            }

            def __init__(self, *args, **kwargs):
                # Ensure EPDDisplay.instance is valid and points to the correct projects_dir
                serve_directory = EPDDisplay.instance.projects_dir if hasattr(EPDDisplay, 'instance') and EPDDisplay.instance else os.path.join(os.path.dirname(os.path.abspath(__file__)), PROJECTS_ROOT_FOLDER)
                super().__init__(*args, directory=serve_directory, **kwargs)

            def do_GET(self):
                """Handle GET requests, serving a custom HTML page or converting to DOC."""
                parsed_url = urlparse(self.path)
                query_params = parse_qs(parsed_url.query)
                fs_path = self.translate_path(parsed_url.path)

                if 'format' in query_params and query_params['format'][0] == 'doc':
                    self.send_as_doc(fs_path)
                    return

                if os.path.isdir(fs_path):
                    self.list_directory(fs_path) # Custom listing for directories
                    return

                # Fallback to default behavior for files (e.g., viewing .txt directly)
                super().do_GET()

            def send_as_doc(self, filepath):
                """Reads a text file and serves it as an RTF file with a .doc extension."""
                if not os.path.isfile(filepath):
                    self.send_error(404, "File not found")
                    return

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        plain_text = f.read()

                    # Simple conversion to RTF format
                    # Escape RTF control characters
                    rtf_text = plain_text.replace('\', r'\\').replace('{', r'\{').replace('}', r'\}')
                    # Convert newlines to RTF paragraph marks
                    rtf_text = rtf_text.replace('
', r'\par' + '
') # Keep newlines for readability in RTF source

                    # Basic RTF structure
                    rtf_content = f"{{\\rtf1\\ansi\\deff0 {{\\fonttbl{{\\f0 Arial;}}}}\\fs24 {rtf_text}}}"
                    encoded_content = rtf_content.encode('ascii', 'ignore') # RTF is typically ASCII

                    self.send_response(200)
                    self.send_header("Content-Type", "application/msword") # Standard for .doc
                    doc_filename = os.path.basename(filepath)
                    base_name, _ = os.path.splitext(doc_filename)
                    self.send_header("Content-Disposition", f'attachment; filename="{html.escape(base_name)}.doc"')
                    self.send_header("Content-Length", str(len(encoded_content)))
                    self.end_headers()
                    self.wfile.write(encoded_content)

                except Exception as e:
                    self.send_error(500, f"Error converting file: {e}")

            def list_directory(self, path):
                """Generates a custom HTML page for directory listing with download links."""
                try:
                    list_of_files = os.listdir(path)
                    list_of_files.sort(key=lambda a: a.lower())

                    # Determine the heading text
                    heading_text = "AdaWriter"
                    # Get the current directory name relative to the server root
                    current_folder_rel_path = os.path.relpath(path, self.directory)
                    if current_folder_rel_path != '.':
                        current_folder_display_name = os.path.basename(current_folder_rel_path)
                        heading_text += f" - {self.DIRECTORY_FRIENDLY_NAMES.get(current_folder_display_name, current_folder_display_name)}"


                    body = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>AdaWriter Files</title>
                        <meta name="viewport" content="width=device-width, initial-scale=1">
                        <style>
                            body {{ font-family: Georgia, "Times New Roman", Times, serif; margin: 2em; background-color: #fdfdfd; color: #333; }}
                            h1 {{
                                font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; /* Modern font for title */
                                color: #343a40;
                                border-bottom: 2px solid #eaeaea;
                                padding-bottom: 0.5em;
                                font-weight: 300; /* Lighter font weight for title */
                            }}
                            ul {{ list-style-type: none; padding: 0; }}
                            li {{
                                background-color: #fff;
                                margin-bottom: 10px;
                                padding: 15px;
                                border-radius: 5px;
                                border: 1px solid #eee;
                                display: flex;
                                justify-content: space-between;
                                align-items: center;
                                flex-wrap: wrap; /* Allow actions to wrap on small screens */
                                gap: 10px; /* Space between name and actions if they wrap */
                            }}
                            a {{ text-decoration: none; }}
                            .file-name {{ font-weight: normal; word-break: break-all; color: #495057; }} /* Allow long names to break */
                            .dir-link {{ color: #0056b3; font-weight: bold; }}
                            .actions {{ display: flex; flex-wrap: nowrap; align-items: center; }} /* Keep actions on one line if possible */
                            .actions a {{
                                margin-left: 10px; /* Space between action buttons */
                                padding: 8px 14px;
                                border-radius: 5px;
                                text-align: center;
                                font-size: 0.9em;
                                border: 1px solid transparent;
                                white-space: nowrap; /* Prevent button text from wrapping */
                                font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; /* Consistent font for buttons */
                            }}
                            .view-link {{ background-color: #f8f9fa; color: #343a40; border-color: #ddd; }}
                            .download-txt-link {{ background-color: #e7f3ff; color: #004085; border-color: #b8daff; }}
                            .download-doc-link {{ background-color: #d1ecf1; color: #0c5460; border-color: #bee5eb; }}
                        </style>
                    </head>
                    <body>
                    <h1>{heading_text}</h1>
                    <ul>
                    """

                    # Link to parent directory if not at the root
                    if os.path.normpath(path) != os.path.normpath(self.directory):
                        body += '<li><a href=".." class="file-name dir-link">Home</a></li>' # Changed from "Parent Directory"

                    for name in list_of_files:
                        fullname = os.path.join(path, name)
                        linkname = name # Relative link

                        if os.path.isdir(fullname):
                            displayname = self.DIRECTORY_FRIENDLY_NAMES.get(name, name) # Use friendly name if available
                            body += f'<li><a href="{linkname}/" class="file-name dir-link">{html.escape(displayname)}</a></li>'
                        elif os.path.isfile(fullname):
                            displayname = name
                            base, ext = os.path.splitext(name)
                            body += f"""
                            <li>
                                <span class="file-name">{html.escape(displayname)}</span>
                                <span class="actions">
                                    <a href="{linkname}" class="view-link" target="_blank">View</a>
                                    <a href="{linkname}" class="download-txt-link" download>Download .txt</a>
                                    <a href="{linkname}?format=doc" class="download-doc-link" download="{html.escape(base)}.doc">Download .doc</a>
                                </span>
                            </li>
                            """

                    body += "</ul></body></html>"
                    encoded = body.encode('utf-8')

                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)

                except OSError:
                    self.send_error(404, "No permission to list directory")

            def log_message(self, format, *args): pass # Suppress log messages to console

        try:
            socketserver.TCPServer.allow_reuse_address = True # Allow quick restart
            httpd_server = socketserver.TCPServer(("", WIFI_SERVER_PORT), CustomHTTPRequestHandler)
            server_thread = threading.Thread(target=httpd_server.serve_forever, daemon=True); server_thread.start()
            print(f"Wi-Fi server started: http://{ip_address}:{WIFI_SERVER_PORT}")
            self._draw_wifi_screen_and_wait() # Show screen and wait for ESC
        except Exception as e:
            self.show_message(f"Server Start Error: {e}", 4, do_full_refresh=False)
            if httpd_server: httpd_server.server_close() # Ensure server is closed on error
            httpd_server = None; server_thread = None

    def _draw_wifi_screen_and_wait(self):
        global httpd_server, server_thread # Ensure access to globals
        ip_address = self.get_local_ip()
        url_to_type = f"http://{ip_address}:{WIFI_SERVER_PORT}" if "No IP" not in ip_address else ip_address

        self.clear();
        y_after_title = self.draw_text_centered(20, "Wi-Fi File Transfer", self.font_main_heading)
        prompt_text_y = y_after_title + 35
        y_after_prompt = self.draw_text_centered(prompt_text_y, "Type this into the browser on your phone:", self.font_body_standard)
        url_display_y = y_after_prompt + 25
        self.draw_text_centered(url_display_y, url_to_type, self.font_url_display)

        font_for_directive = self.font_bottom_directive_unified
        self.draw_text_centered(self.height - font_for_directive.get_linesize() - 10, "ESC to Stop Server", font_for_directive)
        self.display_full(); self.wait_for_back() # wait_for_back handles ESC key press

        # After ESC is pressed and wait_for_back returns:
        if httpd_server:
            print("DEBUG: Attempting to shut down Wi-Fi server...")
            shutdown_thread = threading.Thread(target=httpd_server.shutdown, daemon=True); shutdown_thread.start()
            shutdown_thread.join(timeout=1.0) # Wait for shutdown to complete
            httpd_server.server_close() # Close the server socket itself
            if server_thread: server_thread.join(timeout=0.5) # Wait for the server thread to exit
            print("DEBUG: Wi-Fi server shutdown process completed.")
            httpd_server = None; server_thread = None; self.show_message("Wi-Fi server off.", 1, do_full_refresh=False)

    def show_message(self, message, duration_sec=2, do_full_refresh=True):
        self.clear(); font_for_message = self.font_body_standard
        wrapped_lines = wrap_text(message, font_for_message, self.width - 2 * TEXT_MARGIN)
        block_height = len(wrapped_lines) * font_for_message.get_linesize()
        center_y_start = (self.height - block_height) // 2
        self.draw_text_centered(max(10, center_y_start), message, font_for_message)

        if do_full_refresh:
            self.display_full()
        else:
            self.display_partial() # Use partial refresh for quick messages
        if duration_sec > 0: time.sleep(duration_sec) # Only sleep if duration is positive

    def wait_for_direct_choice(self, valid_key_codes):
        consecutive_keyboard_errors = 0; max_keyboard_errors = 20 # Threshold for error exit
        while True: # Loop indefinitely until a valid key is pressed
            global LAST_KEYBOARD_ACTIVITY_TIME, INACTIVITY_TIMEOUT_SECONDS
            if time.time() - LAST_KEYBOARD_ACTIVITY_TIME > INACTIVITY_TIMEOUT_SECONDS:
                print("DEBUG: wait_for_direct_choice detected inactivity. Initiating shutdown.")
                sys.stdout.flush()
                self.initiate_shutdown() # This will exit
                return ecodes.KEY_ESC # Fallback return, assuming KEY_ESC is a valid ecode

            ready_to_read, _, _ = select.select([keyboard.fd], [], [], KEYBOARD_POLL_TIMEOUT) # Non-blocking poll
            if keyboard.fd in ready_to_read:
                try:
                    for event in keyboard.read():
                        # Process only key down events (value=1)
                        if event.type == ecodes.EV_KEY and event.value == KeyEvent.key_down:
                            global LAST_KEYBOARD_ACTIVITY_TIME
                            LAST_KEYBOARD_ACTIVITY_TIME = time.time() # Update on any key down event processed here
                            consecutive_keyboard_errors = 0 # Reset error count on successful read
                            if event.code in valid_key_codes:
                                # LAST_KEYBOARD_ACTIVITY_TIME is already updated above
                                return event.code # Return the valid key code
                except OSError as e: # Handle specific OS errors like device not found
                    if e.errno == 19: # ENODEV (No such device) - keyboard likely disconnected
                        print(f"KBD ERR (NoDev): {consecutive_keyboard_errors + 1}/{max_keyboard_errors}")
                        consecutive_keyboard_errors += 1
                        if consecutive_keyboard_errors >= max_keyboard_errors:
                            print("CRITICAL: Persistent keyboard Errno 19. Exiting script.")
                            if keyboard: # Attempt to release if possible
                                try: keyboard.ungrab(); keyboard.close(); print("Keyboard ungrabbed/closed on error exit.")
                                except Exception as ke: print(f"Error releasing keyboard on exit: {ke}")
                            sys.exit("Persistent keyboard failure (Errno 19)")
                        time.sleep(0.05) # Brief pause before retrying
                    else: print(f"OSError reading keyboard: {e}"); time.sleep(0.1) # Other OSErrors
                except BlockingIOError: pass # Normal for non-blocking, ignore
                except Exception as e: # Catch any other unexpected errors during keyboard read
                    print(f"General error reading keyboard: {e}")
                    consecutive_keyboard_errors += 1
                    if consecutive_keyboard_errors >= max_keyboard_errors: sys.exit("Persistent general keyboard read failure")
                    time.sleep(0.1) # Brief pause

    def get_text_input_overlay(self, prompt):
        input_buffer = ""
        self.shift_pressed = False # Reset shift state for each input session
        # Define overlay dimensions and position
        overlay_height = self.height // 2 + 40 # Slightly taller for better spacing
        overlay_y = self.height - overlay_height - 5 # Positioned near the bottom, with small margin
        overlay_rect_to_save = pygame.Rect(0, overlay_y, self.width, overlay_height + 5)
        overlay_rect_to_save.clamp_ip(self.screen.get_rect()) # Ensure it's within screen bounds

        try: # Save the screen area that will be covered by the overlay
            saved_screen_area = self.screen.subsurface(overlay_rect_to_save).copy()
        except ValueError as e: # Fallback if subsurface is invalid (e.g., rect too large)
            print(f"Warning: Subsurface for overlay invalid ({e}). Using full screen copy.")
            saved_screen_area = self.screen.copy()

        running_input = True
        while running_input:
            global LAST_KEYBOARD_ACTIVITY_TIME, INACTIVITY_TIMEOUT_SECONDS
            if time.time() - LAST_KEYBOARD_ACTIVITY_TIME > INACTIVITY_TIMEOUT_SECONDS:
                print("DEBUG: Text input overlay detected inactivity. Initiating shutdown.")
                sys.stdout.flush()
                # Attempt to restore screen before shutdown message if possible,
                # but initiate_shutdown will take over quickly.
                # self.screen.blit(saved_screen_area, overlay_rect_to_save.topleft)
                # self.display_partial() # This might not be visible
                self.initiate_shutdown() # This will exit
                return "ESCAPE_KEY" # Fallback return

            # Draw overlay background and border
            pygame.draw.rect(self.screen, (255, 255, 255), overlay_rect_to_save) # White background
            pygame.draw.rect(self.screen, (0,0,0), overlay_rect_to_save, 2) # Black border

            # Draw the prompt text
            prompt_render_y = overlay_y + 15 # Padding from top of overlay
            y_after_prompt = self.draw_text_centered(prompt_render_y, prompt, self.font_body_standard)

            # Draw the current input buffer with a cursor
            input_line_y = y_after_prompt + 10 # Space after prompt
            display_input_text = f"> {input_buffer}_" # Add cursor

            # Truncate displayed text if too long for the overlay width
            max_input_display_width = overlay_rect_to_save.width - 2 * (TEXT_MARGIN)
            temp_display_input_text = display_input_text
            # Iteratively shorten if too wide, preferring to show end of text
            while self.font_editor_text.size(temp_display_input_text)[0] > max_input_display_width and len(temp_display_input_text) > 3: # Min "> _"
                if len(input_buffer) > 20 : # If buffer is long, show ellipsis at start
                    temp_display_input_text = f"> ..{input_buffer[-18:]}_" # Show last 18 chars
                else: # Shorter buffer, try to just shorten from start
                    # This part might need more sophisticated logic for very narrow displays
                    # or very long single characters if that's possible with the font.
                    # For now, a simple approach:
                    if self.font_editor_text.size("> _")[0] > max_input_display_width: # Cannot even fit "> _"
                            temp_display_input_text = ">_" # Show minimal
                            break
                    # Fallback if still too long (should rarely happen with above)
                    half_len = len(temp_display_input_text) // 2
                    temp_display_input_text = temp_display_input_text[:half_len + 1] + "_" # Simple truncate
                # Ensure it still has the prompt/cursor visual cues
                if not temp_display_input_text.startswith("> ") or not temp_display_input_text.endswith("_"):
                    temp_display_input_text = ">" + ("..." if len(input_buffer) > 3 else input_buffer[:3]) + "_"


            self.draw_text(overlay_rect_to_save.left + TEXT_MARGIN, input_line_y, temp_display_input_text, self.font_editor_text)

            # Draw bottom directive for input confirmation/cancellation
            font_for_directive = self.font_bottom_directive_unified
            directive_text = "ENTER to Confirm, ESC to Cancel"
            directive_y = overlay_y + overlay_height - font_for_directive.get_linesize() - 10 # Position at bottom of overlay
            self.draw_text_centered(directive_y, directive_text, font_for_directive)

            self.display_partial() # Update the e-ink display with the overlay

            # Keyboard input handling
            ready_to_read, _, _ = select.select([keyboard.fd], [], [], KEYBOARD_POLL_TIMEOUT)

            if keyboard.fd in ready_to_read:
                try:
                    for event in keyboard.read():
                        if event.type == ecodes.EV_KEY: # Process key events
                            global LAST_KEYBOARD_ACTIVITY_TIME
                            LAST_KEYBOARD_ACTIVITY_TIME = time.time()
                            key_code = event.code
                            key_value = event.value # Press, release, or repeat

                            # Handle Shift key state
                            if key_code == ecodes.KEY_LEFTSHIFT or key_code == ecodes.KEY_RIGHTSHIFT:
                                self.shift_pressed = (key_value != 0) # True if pressed/repeated
                                continue # Don't process shift as a character

                            if key_value == 1 or key_value == 2: # Key down or repeat
                                if key_code == ecodes.KEY_ENTER:
                                    self.screen.blit(saved_screen_area, overlay_rect_to_save.topleft) # Restore screen
                                    self.display_partial() # Update display to remove overlay
                                    return input_buffer.strip() # Return the entered text

                                elif key_code == ecodes.KEY_ESC:
                                    self.screen.blit(saved_screen_area, overlay_rect_to_save.topleft) # Restore
                                    self.display_partial()
                                    return "ESCAPE_KEY" # Special value for cancellation

                                elif key_code == ecodes.KEY_BACKSPACE:
                                    if input_buffer: # If buffer is not empty
                                        input_buffer = input_buffer[:-1] # Remove last character
                                else: # Character input
                                    key_entry = KEY_MAP.get(key_code)
                                    char_to_add = None
                                    if key_entry:
                                        if isinstance(key_entry, dict): # Shiftable character
                                            char_to_add = key_entry['shifted'] if self.shift_pressed else key_entry['unshifted']
                                        # Non-shiftable, non-action key (like space)
                                        elif isinstance(key_entry, str) and key_entry not in ['LSHIFT', 'RSHIFT', 'ENTER', 'BACKSPACE', 'ESCAPE_KEY', 'WORD_COUNT_HOTKEY', 'TIME_DISPLAY_HOTKEY', 'PAGE_UP', 'PAGE_DOWN']:
                                            char_to_add = key_entry

                                    if char_to_add and len(input_buffer) < 100: # Limit input length
                                        input_buffer += char_to_add
                except BlockingIOError: # Normal for non-blocking read
                    pass
                except Exception as e: # Log other errors
                    print(f"Error reading keyboard in get_text_input_overlay: {e}")
            # No input, small sleep to prevent busy loop if select timeout is very low or zero
            # else: time.sleep(0.001)

        # Fallback: should be unreachable if loop exits via return statements
        self.screen.blit(saved_screen_area, overlay_rect_to_save.topleft)
        self.display_partial()
        return input_buffer.strip() # Or "ESCAPE_KEY" if loop broken differently

    def wait_for_back(self): self.wait_for_direct_choice([ecodes.KEY_ESC])

    def initiate_shutdown(self): # Removed from_main_loop, it's not essential for epd internal call
        print("DEBUG: Shutdown initiated (inactivity or explicit call).")
        sys.stdout.flush()

        global httpd_server, server_thread, keyboard # Access globals

        if httpd_server and server_thread and server_thread.is_alive():
            print("DEBUG: Shutting down Wi-Fi server...")
            sys.stdout.flush()
            # Initiate shutdown in a thread to avoid blocking if server is stuck
            shutdown_thread = threading.Thread(target=httpd_server.shutdown, daemon=True)
            shutdown_thread.start()
            shutdown_thread.join(timeout=2.0) # Wait for shutdown with timeout
            if shutdown_thread.is_alive():
                print("DEBUG: HTTPD shutdown timed out, closing server socket directly.")
            httpd_server.server_close() # Ensure socket is closed
            if server_thread.is_alive():
                server_thread.join(timeout=1.0)
            httpd_server = None
            server_thread = None
            print("DEBUG: Wi-Fi server shutdown sequence completed.")
            sys.stdout.flush()

        # show_message might try to use keyboard if not careful, but keyboard will be closed.
        # For shutdown, a simple print might be more robust if EPD is also going down.
        # However, the plan is to use show_message.
        self.show_message("Shutting down...", duration_sec=2, do_full_refresh=True)

        if self.epd and not self.simulated_display:
            try:
                print("DEBUG: Putting e-ink display to sleep.")
                sys.stdout.flush()
                self.epd.sleep()
            except Exception as e:
                print(f"DEBUG: Error putting display to sleep: {e}"); sys.stdout.flush()

        if keyboard:
            try:
                print("DEBUG: Ungrabbing and closing keyboard.")
                sys.stdout.flush()
                keyboard.ungrab()
                keyboard.close()
                keyboard = None # Clear the global
            except Exception as e_kbd:
                print(f"DEBUG: Error releasing keyboard: {e_kbd}"); sys.stdout.flush()

        print("DEBUG: Quitting Pygame modules.")
        sys.stdout.flush()
        if pygame.font.get_init(): pygame.font.quit()
        pygame.display.quit() # Safe to call even if not fully initialized or display not active
        pygame.quit()

        print("DEBUG: Flushing stdout/stderr before final OS shutdown command.")
        sys.stdout.flush()
        sys.stderr.flush()
        time.sleep(0.3)

        print("DEBUG: Issuing OS shutdown command: sudo shutdown -h now")
        sys.stdout.flush()
        os.system("sudo shutdown -h now")
        sys.exit(0) # Ensure script terminates

    def show_shutdown_screen(self):
        if not self.epd or self.simulated_display: # Don't try to use EPD if simulated or not present
            print("SIM DEBUG: show_shutdown_screen ('AdaWriter')"); sys.stdout.flush()
            if self.epd and hasattr(self.epd, 'sleep'): # If EPD object exists but is simulated, it might have a dummy sleep
                try: self.epd.sleep()
                except: pass # Ignore errors on dummy sleep
            return

        print("DEBUG: Displaying AdaWriter shutdown screen..."); sys.stdout.flush()
        self.clear() # Clear screen to white
        tolstoy_image_surface_scaled = None
        try:
            # Try to load PNG first, then BMP as fallback
            image_path = os.path.join(self.assets_dir, "tolstoy.png")
            if not os.path.exists(image_path):
                image_path = os.path.join(self.assets_dir, "tolstoy.bmp") # Fallback to BMP

            if os.path.exists(image_path):
                print(f"DEBUG: Attempting to load Tolstoy image from: {image_path}"); sys.stdout.flush()
                loaded_image = pygame.image.load(image_path) # Load the image
                print(f"DEBUG: Image loaded (pre-convert), type: {type(loaded_image)}, size: {loaded_image.get_size()}"); sys.stdout.flush()

                # Ensure the loaded image is in a format that supports alpha if it's PNG, or just convert for consistency
                # Using convert_alpha() is safer for images with transparency. For BMPs, convert() is fine.
                if image_path.endswith(".png"):
                    tolstoy_image_prepared = loaded_image.convert_alpha()
                else:
                    tolstoy_image_prepared = loaded_image.convert()

                print("DEBUG: Image converted for Pygame processing."); sys.stdout.flush()

                desired_img_height = 170 # Desired height for the image on display
                img_w, img_h = tolstoy_image_prepared.get_size()
                if img_h > 0 : # Ensure height is positive to avoid division by zero
                    aspect_ratio = img_w / img_h
                    new_img_h = desired_img_height
                    new_img_w = int(new_img_h * aspect_ratio)
                    # Ensure width is also within bounds
                    if new_img_w > self.width - 40 : # Max width with some margin
                        new_img_w = self.width - 40
                        new_img_h = int(new_img_w / aspect_ratio) if aspect_ratio > 0 else desired_img_height # Recalc height
                    print(f"DEBUG: Prepared image size: {img_w}x{img_h}, Scaling to: {new_img_w}x{new_img_h}"); sys.stdout.flush()
                    tolstoy_image_surface_scaled = pygame.transform.smoothscale(tolstoy_image_prepared, (new_img_w, new_img_h))
                    print("DEBUG: Tolstoy image successfully scaled."); sys.stdout.flush()
                else:
                    print("DEBUG: Tolstoy image has zero height after preparation."); sys.stdout.flush()
                    tolstoy_image_surface_scaled = None # Cannot use
            else:
                print(f"DEBUG: Tolstoy image not found in assets at path: {image_path}"); sys.stdout.flush()
                tolstoy_image_surface_scaled = None
        except Exception as e:
            print(f"DEBUG: Error loading/scaling Tolstoy image: {e}"); sys.stdout.flush()
            import traceback; traceback.print_exc(file=sys.stdout); sys.stdout.flush()
            tolstoy_image_surface_scaled = None # Ensure it's None on error

        # Text content for the shutdown screen
        quote_text = "Everything I know, I know because of love."
        quote_font = self.font_quote_serif
        attribution_text = "- Leo Tolstoy"
        attribution_font = self.font_attribution_serif
        brand_text = "AdaWriter"
        brand_font = self.font_shutdown_brand_accent # Using the smaller primary font for accent
        current_y_pos = TEXT_MARGIN + 10 # Initial Y position

        # Display Tolstoy image if loaded and scaled successfully
        if tolstoy_image_surface_scaled:
            img_rect = tolstoy_image_surface_scaled.get_rect(centerx=self.width // 2, top=current_y_pos)
            self.screen.blit(tolstoy_image_surface_scaled, img_rect)
            current_y_pos = img_rect.bottom + 10 # Update Y position below image
            print(f"DEBUG: Tolstoy image blitted at {img_rect.topleft}"); sys.stdout.flush()
        else: # Fallback if no image: vertically center the quote block
            quote_block_height = len(wrap_text(quote_text, quote_font, self.width - 2*TEXT_MARGIN)) * quote_font.get_linesize()
            attribution_block_height = attribution_font.get_linesize()
            total_text_block_height = quote_block_height + attribution_block_height + 5 # 5 for spacing
            # Calculate Y to center this block, considering space for brand text at bottom
            current_y_pos = (self.height - total_text_block_height - brand_font.get_linesize() - 30) // 2 # 30 for bottom margin area
            if current_y_pos < TEXT_MARGIN + 10: current_y_pos = TEXT_MARGIN + 10 # Ensure it's not too high
            print("DEBUG: Tolstoy image surface was None, not blitting image."); sys.stdout.flush()


        # Draw quote and attribution
        # Check if text fits on one line, else use draw_text_centered for wrapping
        quote_surface = quote_font.render(quote_text, True, (0,0,0)) # Black text
        if quote_surface.get_width() <= self.width - 2 * TEXT_MARGIN: # Fits on one line
            quote_rect = quote_surface.get_rect(centerx=self.width // 2, top=current_y_pos)
            self.screen.blit(quote_surface, quote_rect)
            current_y_pos = quote_rect.bottom # Update Y below quote
        else: # Needs wrapping
            current_y_pos = self.draw_text_centered(current_y_pos, quote_text, quote_font)
        current_y_pos += 2 # Small space
        current_y_pos = self.draw_text_centered(current_y_pos, attribution_text, attribution_font)

        # Draw "AdaWriter" brand at the bottom
        brand_text_y = self.height - brand_font.get_linesize() - 15 # 15px from bottom
        self.draw_text_centered(brand_text_y, brand_text, brand_font)

        print("DEBUG: Calling display_full() for shutdown screen."); sys.stdout.flush()
        self.display_full(); # Update the EPD with the composed screen
        print("DEBUG: display_full() for shutdown screen returned. Sleeping for 2.5s."); sys.stdout.flush()
        time.sleep(2.5) # Display the screen for a moment
        try:
            print("DEBUG: Putting e-ink display to sleep..."); sys.stdout.flush()
            self.epd.sleep() # Put the display to sleep
            print("DEBUG: E-ink display put to sleep command sent."); sys.stdout.flush()
        except Exception as e: print(f"Error putting display to sleep: {e}"); sys.stdout.flush()

# --- Wi-Fi Management Methods ---
    def show_wifi_menu(self):
        print("DEBUG: show_wifi_menu called"); sys.stdout.flush()
        running_wifi_menu = True
        while running_wifi_menu:
            self.clear()
            title_y = self.draw_text_centered(15, "Wi-Fi Settings", self.font_main_heading)

            menu_items = [
                "1. Scan & Connect",
                "2. Current IP / Status",
                "ESC. Back to Main Menu"
            ]

            current_y = title_y + 30 # Start Y for menu items
            item_font = self.font_list_item # Or another suitable font

            for item_text in menu_items:
                current_y = self.draw_text(TEXT_MARGIN + 20, current_y + 5, item_text, item_font)
                current_y += item_font.get_linesize() * 0.5 # Spacing

            self.display_full()

            valid_keys = [ecodes.KEY_1, ecodes.KEY_2, ecodes.KEY_ESC]
            choice = self.wait_for_direct_choice(valid_keys)

            if choice == ecodes.KEY_1:
                self.scan_and_select_wifi() # This will show its own messages and return here
            elif choice == ecodes.KEY_2:
                ip_status = self._get_wifi_ip_status()
                self.show_message(ip_status, duration_sec=4, do_full_refresh=True) # Longer duration for status
            elif choice == ecodes.KEY_ESC:
                running_wifi_menu = False
        # Loop finishes, effectively returning to the main menu caller
        # Ensure the main menu is refreshed by returning to its loop

    def _get_wifi_ip_status(self):
        print("DEBUG: _get_wifi_ip_status called"); sys.stdout.flush()
        if not shutil.which("nmcli"):
            return "nmcli tool not found."

        current_ip = self.get_local_ip() # Assuming this method exists and works
        active_ssid = None

        try:
            cmd = ["nmcli", "-t", "-f", "NAME,DEVICE,TYPE", "connection", "show", "--active"]
            process = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=10)

            if process.returncode == 0:
                for line in process.stdout.strip().split('
'):
                    parts = line.split(':')
                    # Example line: MyWifi:wlan0:wifi
                    if len(parts) == 3 and parts[1].startswith('wlan') and parts[2] == 'wifi':
                        active_ssid = parts[0].replace("\\:", ":") # Handle escaped colons in SSID
                        break
            else:
                print(f"DEBUG: Error checking active Wi-Fi status with nmcli. Return code: {process.returncode}")
                print(f"DEBUG: nmcli stderr: {process.stderr}")

        except FileNotFoundError: # Should be caught by shutil.which, but as a fallback
            return "nmcli tool not found."
        except subprocess.TimeoutExpired:
            print("DEBUG: nmcli command timed out while checking active connection.")
            return f"IP: {current_ip}
(Wi-Fi status check timed out)"
        except Exception as e:
            print(f"DEBUG: Exception checking Wi-Fi status: {e}")
            return f"IP: {current_ip}
(Error checking Wi-Fi status)"

        if active_ssid:
            return f"Connected to: {active_ssid}
IP: {current_ip}"
        else:
            return f"IP: {current_ip}
(No active Wi-Fi or status unknown)"

    def scan_and_select_wifi(self):
        print("DEBUG: scan_and_select_wifi called"); sys.stdout.flush()
        self.show_message("Scanning for networks...", duration_sec=0, do_full_refresh=False) # Non-blocking message

        networks = self._scan_wifi_networks_nmcli()

        if not networks: # Handles None or empty list
            self.show_message("No networks found or scan failed.", 2, do_full_refresh=True) # Ensure full refresh after scan message
            return

        selected_network = self._display_wifi_networks_menu(networks)

        if selected_network is None: # User cancelled from the network list menu
            self.show_message("Selection cancelled.", 1, do_full_refresh=True) # Refresh to clear network list
            return

        ssid = selected_network['ssid']
        security = selected_network['security'] # e.g., "WPA2", "WEP", "Open", or empty
        password = "" # Default for open networks or if no password is required/entered

        # Check if security field is present and not effectively 'open'
        # nmcli might return an empty string for SECURITY or specific terms like "open"
        is_protected = security and security.lower() != "open" and security.strip() != ""

        if is_protected:
            prompt_message = f"Password for {ssid}:"
            # Ensure the prompt overlay is drawn on a clean base or the previous menu
            # self.show_main_menu() # Or self.show_wifi_menu() if that's the base
            # For now, get_text_input_overlay handles its own drawing over current screen

            password_input = self.get_text_input_overlay(prompt_message)

            if password_input == "ESCAPE_KEY" or password_input is None: # Check for None if get_text_input_overlay can return it
                self.show_message("Connection cancelled.", 1, do_full_refresh=True) # Refresh to clear overlay
                return
            password = password_input # Can be empty if user just hits Enter

        self.show_message(f"Connecting to {ssid}...", duration_sec=0, do_full_refresh=True) # Full refresh before connect attempt message

        # Pass None if password string is empty, otherwise pass the password.
        # Some systems might treat an empty string password differently than no password argument.
        actual_password_arg = password if password else None

        success = self._connect_to_wifi_nmcli(ssid, actual_password_arg)

        if success:
            self.show_message(f"Successfully connected to {ssid}!", 2, do_full_refresh=True)
        else:
            # _connect_to_wifi_nmcli already shows a detailed error,
            # but we might want a more generic one here or ensure it's refreshed.
            self.show_message(f"Failed to connect to {ssid}.", 3, do_full_refresh=True) # Longer duration for failure

    def _scan_wifi_networks_nmcli(self):
        print("DEBUG: _scan_wifi_networks_nmcli called"); sys.stdout.flush()
        if not shutil.which("nmcli"):
            self.show_message("nmcli not found.", 2)
            return []

        cmd = ["nmcli", "--terse", "--fields", "SSID,BARS,SECURITY", "dev", "wifi", "list", "--rescan", "yes"]
        parsed_networks = []
        try:
            # self.show_message("Scanning...", duration_sec=0, do_full_refresh=False) # Feedback moved to calling function
            process = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=15)

            if process.returncode != 0:
                error_message = process.stderr.strip()
                print(f"DEBUG: nmcli scan error - return code {process.returncode}. stderr: {error_message}")
                # self.show_message("Wi-Fi scan command failed.", 2) # Feedback moved to calling function
                return []

            output = process.stdout.strip()
            print(f"DEBUG: nmcli scan output:
{output}")

            if not output: # No networks found or empty output
                return []

            for line in output.split('
'):
                parts = line.split(':')
                # SSID can contain escaped colons, BARS and SECURITY might be missing

                ssid = parts[0].replace("\\:", ":") if len(parts) > 0 else ""
                if not ssid.strip(): # Skip lines with empty or whitespace-only SSIDs
                    continue

                strength_bars = ""
                security = "Open" # Default to Open if not specified

                if len(parts) > 1:
                    strength_bars = parts[1]
                if len(parts) > 2:
                    security_field = parts[2].replace("\\:", ":") # Handle escaped colons in security field too
                    if security_field.strip(): # Only override default if security field is not empty
                        security = security_field

                parsed_networks.append({'ssid': ssid, 'strength_bars': strength_bars, 'security': security})

        except subprocess.TimeoutExpired:
            print("DEBUG: nmcli scan command timed out.")
            # self.show_message("Wi-Fi scan timed out.", 2) # Feedback moved to calling function
            return []
        except Exception as e:
            print(f"DEBUG: Exception during Wi-Fi scan: {e}")
            # self.show_message("Error during scan.", 2) # Feedback moved to calling function
            return []

        return parsed_networks

    def _display_wifi_networks_menu(self, networks):
        print("DEBUG: _display_wifi_networks_menu called with networks:", networks); sys.stdout.flush()
        self.clear()
        title_y = self.draw_text_centered(15, "Select Network", self.font_main_heading)

        display_count = min(len(networks), 7) # Show max 7 networks
        if display_count == 0: # Should be caught by scan_and_select_wifi, but as a safeguard
            self.show_message("No networks to display.", 2)
            return None

        valid_keys = [ecodes.KEY_ESC]
        options_to_display = []

        item_y = title_y + 25 # Initial Y for the first network item

        for i in range(display_count):
            net = networks[i]
            # Simplified strength: just show BARS field directly for now
            text = f"{i+1}. {net['ssid']} ({net['strength_bars']}) {net['security']}"
            options_to_display.append(text) # Not strictly needed here but good for consistency
            item_y = self.draw_text(TEXT_MARGIN + 10, item_y + 5, text, self.font_list_item, max_w_override=self.width - 2*(TEXT_MARGIN+10))
            item_y += self.font_list_item.get_linesize() * 0.3 # Add some spacing
            valid_keys.append(getattr(ecodes, f"KEY_{i+1}"))

        directive_font = self.font_bottom_directive_unified
        directive_text = "ESC to Cancel"
        # Adjust directive_y if list is short, prevent overlap
        directive_y_candidate = item_y + 20
        min_directive_y = self.height - directive_font.get_linesize() - 10
        final_directive_y = max(directive_y_candidate, min_directive_y)
        if final_directive_y > min_directive_y and item_y > final_directive_y - 20 : # Avoid overlap if list is too long
             final_directive_y = item_y + 10 # push it down a bit
        if final_directive_y + directive_font.get_linesize() > self.height -5: # Absolute last resort
            final_directive_y = self.height - directive_font.get_linesize() -5


        self.draw_text_centered(final_directive_y, directive_text, directive_font)
        self.display_full()

        choice_key = self.wait_for_direct_choice(valid_keys)

        if choice_key == ecodes.KEY_ESC:
            return None

        # Convert KEY_1, KEY_2 etc. to index
        # KEY_1 (ecodes value 2) corresponds to index 0
        # KEY_2 (ecodes value 3) corresponds to index 1
        # ...
        # KEY_9 (ecodes value 10) corresponds to index 8
        # KEY_0 (ecodes value 11) corresponds to index 9 (if we were using it)

        # A more robust way to map these specific keys:
        key_to_index_map = {ecodes.KEY_1:0, ecodes.KEY_2:1, ecodes.KEY_3:2, ecodes.KEY_4:3, ecodes.KEY_5:4, ecodes.KEY_6:5, ecodes.KEY_7:6} # up to 7 items

        if choice_key in key_to_index_map:
            choice_index = key_to_index_map[choice_key]
            if 0 <= choice_index < display_count:
                return networks[choice_index]

        return None # Should not happen if wait_for_direct_choice works correctly

    def _connect_to_wifi_nmcli(self, ssid, password=None):
        print(f"DEBUG: _connect_to_wifi_nmcli called for SSID: {ssid}"); sys.stdout.flush()
        if not shutil.which("nmcli"):
            self.show_message("nmcli not found.", 2)
            return False

        cmd = ["nmcli", "dev", "wifi", "connect", ssid]
        if password: # Only add password argument if it's provided and not empty
            cmd.extend(["password", password])

        print(f"DEBUG: Wi-Fi Connect CMD: {' '.join(cmd)}")
        sys.stdout.flush()

        try:
            process = subprocess.run(cmd, capture_output=True, text=True, timeout=45) # Increased timeout

            print(f"DEBUG: nmcli connect stdout:
{process.stdout}")
            sys.stdout.flush()
            print(f"DEBUG: nmcli connect stderr:
{process.stderr}")
            sys.stdout.flush()

            if process.returncode == 0:
                # Even if nmcli returns 0, connection might still be acquiring IP.
                self.show_message("Verifying connection...", duration_sec=0, do_full_refresh=False)
                time.sleep(8) # Wait for connection to establish and IP to be assigned.

                current_ip = self.get_local_ip()
                if "No IP" not in current_ip and current_ip != "127.0.0.1": # Check for a valid IP
                    print(f"DEBUG: Connection successful, IP acquired: {current_ip}"); sys.stdout.flush()
                    return True

                # Fallback check if IP is not immediately available or get_local_ip is problematic
                # This checks if the SSID is listed as active for any wlan device
                verify_cmd = ["nmcli", "-t", "-f", "ACTIVE,SSID,DEVICE", "device", "wifi"]
                verify_process = subprocess.run(verify_cmd, capture_output=True, text=True, timeout=10)
                if verify_process.returncode == 0:
                    for line in verify_process.stdout.strip().split('
'):
                        if line.startswith("yes:") and ssid in line:
                            print(f"DEBUG: Verified active connection to {ssid} via nmcli device wifi list."); sys.stdout.flush()
                            return True

                self.show_message("IP address not confirmed.", 2)
                print("DEBUG: Connection succeeded by nmcli, but IP address not confirmed or SSID not active."); sys.stdout.flush()
                return False # Or True, depending on how strict we want to be. Let's be strict.
            else:
                error_msg = process.stderr.strip().split('
')[-1] if process.stderr.strip() else "Unknown nmcli error"
                # self.show_message(f"Connection failed: {error_msg}", 3) # Moved to calling function
                print(f"DEBUG: nmcli connect command failed. Last error line: {error_msg}"); sys.stdout.flush()
                return False
        except subprocess.TimeoutExpired:
            print("DEBUG: nmcli connect command timed out."); sys.stdout.flush()
            # self.show_message("Connection attempt timed out.", 3) # Moved to calling function
            return False
        except Exception as e:
            print(f"DEBUG: Exception during Wi-Fi connect: {e}"); sys.stdout.flush()
            # self.show_message("Error during connection.", 3) # Moved to calling function
            return False

# --- Main Application Logic ---
def main():
    global keyboard, httpd_server, server_thread, epd # epd needs to be global for the inactivity check in main
    choice_key_code = None # epd is initialized after this in original code
    try:
        # Change to script's directory to ensure relative paths for assets/projects work
        script_base_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_base_dir)
        print(f"--- Starting Adawriter Script (home.py) from {os.getcwd()} ---")
        sys.stdout.flush()

        # Attempt to turn off HDMI on Raspberry Pi to save power/prevent interference
        if os.path.exists("/usr/bin/tvservice") and os.access("/usr/bin/tvservice", os.X_OK):
            print("DEBUG: Attempting to turn off HDMI...")
            status = os.system("/usr/bin/tvservice -o > /dev/null 2>&1") # Redirect output
            if status == 0: print("DEBUG: HDMI off command executed.")
            else: print(f"DEBUG: tvservice -o command may have failed (status: {status}).")
        else: print("DEBUG: tvservice command not found or not executable.")

        print("DEBUG: Creating EPDDisplay object...")
        epd = EPDDisplay() # This now handles its own init and EPD object creation
        EPDDisplay.instance = epd # Make instance globally accessible via class
        print("DEBUG: EPDDisplay object created.")

        running = True
        while running:
            global LAST_KEYBOARD_ACTIVITY_TIME, INACTIVITY_TIMEOUT_SECONDS # epd is already global
            if time.time() - LAST_KEYBOARD_ACTIVITY_TIME > INACTIVITY_TIMEOUT_SECONDS:
                print("DEBUG: Main loop detected inactivity. Initiating shutdown.")
                sys.stdout.flush()
                if epd:
                    epd.initiate_shutdown() # This call will handle sys.exit()
                else: # Should not happen if epd is initialized correctly
                    print("CRITICAL: EPD object not found for shutdown. Exiting.")
                    sys.exit(1)
                # Code below might not be reached if initiate_shutdown exits, but good for clarity
                running = False
                break

            print("DEBUG: Top of main while loop, calling show_main_menu()")
            epd.show_main_menu() # Display the main menu options
            print("DEBUG: show_main_menu() returned, waiting for input...")
            # Define valid keys for the main menu
            valid_main_menu_keys = [ecodes.KEY_1, ecodes.KEY_2, ecodes.KEY_3, ecodes.KEY_W, ecodes.KEY_Q]
            choice_key_code = epd.wait_for_direct_choice(valid_main_menu_keys)

            # global LAST_KEYBOARD_ACTIVITY_TIME # Already global from loop start
            LAST_KEYBOARD_ACTIVITY_TIME = time.time()

            print(f"DEBUG: Main menu choice key: {choice_key_code} (Q is {ecodes.KEY_Q}, W is {ecodes.KEY_W})")

            if choice_key_code == ecodes.KEY_1: epd.show_journal()
            elif choice_key_code == ecodes.KEY_2: epd.show_projects_list()
            elif choice_key_code == ecodes.KEY_3: epd.show_wifi_menu()
            elif choice_key_code == ecodes.KEY_W: epd.start_wifi_transfer_server()
            elif choice_key_code == ecodes.KEY_Q:
                print("DEBUG: Q key pressed in main menu. Setting running = False.")
                sys.stdout.flush()
                running = False # This will cause the loop to terminate

    except SystemExit as e: # Catch sys.exit() calls, e.g. from keyboard errors
        print(f"DEBUG: Script explicitly exited with code: {e.code if hasattr(e, 'code') else 'Unknown'}")
        # If exit was due to Q key but error code is non-zero, treat as error for shutdown path
        if choice_key_code == ecodes.KEY_Q and (hasattr(e, 'code') and e.code !=0) : choice_key_code = None # Not a clean Q quit
        elif not hasattr(e, 'code') or e.code != 0: choice_key_code = None # Any other non-zero exit
    except Exception as e: # Catch all other unhandled exceptions
        print(f"CRITICAL UNHANDLED EXCEPTION in main execution: {e}")
        import traceback; traceback.print_exc(); choice_key_code = None # Treat as error, don't show pretty shutdown
    finally:
        print(f"DEBUG: Reached finally block. choice_key_code = {choice_key_code}, Q_KEY_CODE for comparison = {ecodes.KEY_Q}")
        sys.stdout.flush()

        # Ensure HTTP server is shut down if it was running
        if httpd_server: # Check if httpd_server object exists
            print("DEBUG: Shutting down Wi-Fi server from finally block."); sys.stdout.flush()
            try:
                shutdown_thread = threading.Thread(target=httpd_server.shutdown, daemon=True)
                shutdown_thread.start(); shutdown_thread.join(timeout=1.0) # Wait for shutdown
                httpd_server.server_close() # Close the server socket
                if server_thread and server_thread.is_alive(): server_thread.join(timeout=0.5) # Wait for thread
            except Exception as e_httpd: print(f"Error shutting down httpd_server: {e_httpd}"); sys.stdout.flush()
            finally: httpd_server = None; server_thread = None # Clear globals

        # Release keyboard
        if keyboard: # Check if keyboard object was initialized
            try:
                print("DEBUG: Attempting to ungrab and close keyboard."); sys.stdout.flush()
                keyboard.ungrab(); keyboard.close(); # Ungrab and close
                print("DEBUG: Keyboard ungrabbed and closed."); sys.stdout.flush()
            except Exception as e_kbd: print(f"DEBUG: Error closing keyboard: {e_kbd}"); sys.stdout.flush()

        # Check if shutdown was initiated by 'Q' key
        if choice_key_code == ecodes.KEY_Q: # Only show pretty shutdown if Q was the last command
            print("DEBUG: 'Q' key was pressed (checked in finally), proceeding to shutdown."); sys.stdout.flush()
            if epd is not None: # Ensure epd object exists
                print("DEBUG: Calling show_shutdown_screen() from finally."); sys.stdout.flush()
                epd.show_shutdown_screen() # Display the custom shutdown screen
            else: print("DEBUG: EPD object was None in finally, cannot show shutdown screen."); sys.stdout.flush()

            # Quit Pygame modules
            if pygame.font.get_init(): pygame.font.quit()
            if pygame.display.get_init(): pygame.display.quit()
            pygame.quit(); print("DEBUG: Pygame quit in Q-shutdown path."); sys.stdout.flush()

            # Perform system shutdown
            print("DEBUG: Flushing stdout/stderr before shutdown command..."); sys.stdout.flush(); sys.stderr.flush()
            time.sleep(0.2) # Brief pause for flush
            print("DEBUG: Initiating system shutdown command (sudo shutdown -h now)..."); sys.stdout.flush()
            status = 0 # Default status
            try:
                # status = os.system("sudo shutdown -h now") # Uncomment to enable actual shutdown
                print("INFO: System shutdown command would be: sudo shutdown -h now (commented out for safety)"); sys.stdout.flush() # For testing
                print(f"DEBUG: Shutdown command process finished with status {status} (script will likely terminate here if successful)"); sys.stdout.flush()
                if status != 0: # Should not happen if command is commented out
                    print(f"ERROR: Shutdown command failed with status {status}"); sys.stdout.flush()
                sys.exit(0 if status == 0 else 1) # Exit with success if shutdown cmd was (notionally) successful
            except Exception as e_shutdown: # Catch errors during the os.system call itself
                print(f"Error during os.system(shutdown) command: {e_shutdown}"); sys.stdout.flush()
                sys.exit(1) # Exit with error
        else: # Normal exit or error exit, not a Q-initiated shutdown
            print(f"DEBUG: Exiting script (finally block). choice_key_code ({choice_key_code}) was not Q ({ecodes.KEY_Q})."); sys.stdout.flush()
            if epd is not None and epd.epd and not epd.simulated_display: # If EPD hardware exists
                try: epd.epd.sleep(); print("DEBUG: EPD display put to sleep on normal exit."); sys.stdout.flush()
                except Exception as e_epd_sleep: print(f"Error sleeping display on normal exit: {e_epd_sleep}"); sys.stdout.flush()

            # Quit Pygame modules
            if pygame.font.get_init(): pygame.font.quit()
            if pygame.display.get_init(): pygame.display.quit()
            pygame.quit(); print("DEBUG: Pygame quit on normal exit."); sys.stdout.flush()

            # Determine exit code for non-Q exits
            exit_code = 0
            if 'e' in locals(): # Check if an exception 'e' was caught in the main try-except
                current_exception = locals()['e']
                if isinstance(current_exception, SystemExit) and hasattr(current_exception, 'code'):
                    # If it was a SystemExit, propagate its code unless it's 0 (which means clean exit already)
                    if current_exception.code is not None and current_exception.code != 0 : exit_code = 1 # Treat non-zero sys.exit as error
                elif isinstance(current_exception, Exception): exit_code = 1 # Any other exception means error
            sys.exit(exit_code) # Exit with 0 if no error, 1 if error

if __name__ == '__main__':
    # Ensure the script runs from its own directory context
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print(f"--- Starting Adawriter Script (home.py) from {os.getcwd()} ---")
    sys.stdout.flush()
    main()
    # This line should ideally not be reached if main() always calls sys.exit()
    print("--- Adawriter Script (home.py) main() returned (should not happen if sys.exit is called) ---")
    sys.stdout.flush()
