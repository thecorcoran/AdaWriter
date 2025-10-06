# ada_writer.py (Version 3.6 - Editor Refactoring)
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import sys
import pygame
import threading
import signal
import time
import subprocess
import traceback
from evdev import ecodes
from datetime import date, datetime
import netifaces

# --- E-Paper Driver Import ---
# Attempt to import the hardware driver. If it fails, set a flag.
try:
    import waveshare_epd
    EINK_DRIVER_AVAILABLE = True
except ImportError:
    EINK_DRIVER_AVAILABLE = False

# Local imports
import config
from keyboard import Keyboard
from logger import setup_logger
from web_server import create_web_app
from display_manager import DisplayManager
from editor_renderer import EditorRenderer # New import
import wifi_manager

pygame.init()
logger = setup_logger()

# --- Graceful Shutdown Handler ---
SHUTDOWN_REQUESTED = False
def handle_shutdown_signal(signum, frame):
    """Handle termination signals from systemd."""
    global SHUTDOWN_REQUESTED
    if not SHUTDOWN_REQUESTED:
        logger.info(f"Received signal {signum}. Initiating graceful shutdown.")
        SHUTDOWN_REQUESTED = True

class AdaWriter:
    def __init__(self, keyboard_device, display_manager):
        self.keyboard = keyboard_device
        self.display = display_manager
        logger.info("Initializing AdaWriter application...")
        self.last_activity = time.time()
        
        self.projects_dir = os.path.join(config.BASE_DIR, config.PROJECTS_ROOT_FOLDER)
        self.archive_dir = os.path.join(self.projects_dir, "archive")
        self.trash_dir = os.path.join(self.projects_dir, ".trash")
        os.makedirs(self.projects_dir, exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)
        os.makedirs(self.trash_dir, exist_ok=True)
        self._ensure_project_files_exist()
        self.last_wifi_creds = self._load_last_wifi_credentials()
        
        self.web_server_thread = None
        self.flask_app = None

        # Status indicators
        self.save_indicator_active = False; self.save_indicator_timer = 0
        self.word_count_active = False; self.word_count_timer = 0; self.current_word_count_text = ""
        self.time_display_active = False; self.time_display_timer = 0; self.current_time_text = ""
        self.editor_view_top_line = 0

    def _update_monthly_journal(self, changed_daily_file_path):
        """
        Aggregates all daily journals for a given month into a single monthly file.
        This is triggered when a daily journal is saved.
        """
        try:
            file_basename = os.path.basename(changed_daily_file_path)
            # From '2024-09-15.txt', get '2024-09'
            monthly_filename = f"{file_basename[:7]}.txt"
            monthly_path = os.path.join(self.projects_dir, monthly_filename)

            # Find all daily files for that month and sort them
            daily_files_for_month = sorted([
                f for f in os.listdir(self.projects_dir) 
                # Ensure we only get daily files (e.g., YYYY-MM-DD.txt) and not the monthly file (YYYY-MM.txt)
                if f.startswith(file_basename[:7]) and f.count('-') == 2 and f.endswith('.txt') 
            ])

            full_daily_content = ""
            for daily_file in daily_files_for_month:
                daily_path = os.path.join(self.projects_dir, daily_file)
                with open(daily_path, 'r', encoding='utf-8') as f_daily:
                    full_daily_content += f_daily.read() + "\n\n"

            with open(monthly_path, 'w', encoding='utf-8') as f_monthly:
                f_monthly.write(full_daily_content.strip())
            logger.info(f"Updated monthly journal {monthly_filename} with new content.")
        except (IOError, OSError) as e:
            logger.error(f"Could not update monthly journal: {e}")

    def _ensure_project_files_exist(self):
        """Creates a daily journal file if it doesn't exist."""
        init_flag_path = os.path.join(self.projects_dir, '.initialized')
        if not os.path.exists(init_flag_path):
            logger.info("First run detected. Creating default files.")
            
            today = date.today()
            journal_filename = f"{today.strftime('%Y-%m-%d')}.txt"
            journal_path = os.path.join(self.projects_dir, journal_filename)
            journal_content = f"{today.strftime('%B %d, %Y')}\n\n"
            with open(journal_path, 'w', encoding='utf-8') as f: f.write(journal_content)
            
            default_project_path = os.path.join(self.projects_dir, "Project One.txt")
            with open(default_project_path, 'w', encoding='utf-8') as f: f.write("")

            with open(init_flag_path, 'w') as f: f.write('1')
            logger.info("Default files and initialization flag created.")

    def _load_last_wifi_credentials(self):
        """Loads the last used Wi-Fi credentials from a file."""
        try:
            path = os.path.join(config.BASE_DIR, "last_wifi.conf")
            with open(path, 'r') as f:
                lines = f.read().splitlines()
                if len(lines) >= 2:
                    return {'ssid': lines[0], 'password': lines[1]}
        except FileNotFoundError:
            logger.info("last_wifi.conf not found. Will prompt for new connection.")
        except (IOError, OSError) as e:
            logger.error(f"Error loading last Wi-Fi credentials: {e}")
        return None

    def _save_last_wifi_credentials(self, ssid, password):
        """Saves Wi-Fi credentials to a file."""
        path = os.path.join(config.BASE_DIR, "last_wifi.conf")
        with open(path, 'w') as f: f.write(f"{ssid}\n{password}")

    def run(self):
        """Main application loop."""
        try:
            should_shutdown = False; is_first_loop = True
            while not should_shutdown and not SHUTDOWN_REQUESTED:
                self.keyboard.shift_pressed = False # Reset shift state on main menu
                if time.time() - self.last_activity > config.INACTIVITY_TIMEOUT_SECONDS:
                    logger.info("Inactivity timeout reached. Requesting shutdown.")
                    should_shutdown = True
                    continue
                
                self.show_main_menu(is_first_run=is_first_loop)
                if is_first_loop: is_first_loop = False
                choice = self.wait_for_direct_choice([ecodes.KEY_1, ecodes.KEY_2, ecodes.KEY_W, ecodes.KEY_Q])
                
                if choice == ecodes.KEY_1: self.show_journal()
                elif choice == ecodes.KEY_2: self.show_projects_list()
                elif choice == ecodes.KEY_W: self.show_wifi_menu()
                elif choice == ecodes.KEY_Q:
                    if self.confirm_action("Really shut down?"):
                        should_shutdown = True
            
            if should_shutdown or SHUTDOWN_REQUESTED:
                self.initiate_shutdown()

        except Exception as e:
            logger.critical(f"--- UNHANDLED EXCEPTION IN APP RUNTIME ---", exc_info=True)
            self.show_message(f"Runtime Error:\n{e}", fatal_error=True)
            self.initiate_shutdown()

    def confirm_action(self, prompt):
        """Displays a confirmation dialog and waits for 1 (Yes) or 2 (No)."""
        self.display.draw_confirmation_dialog(prompt)
        self.display.display_image(is_full_refresh=True)
        choice = self.wait_for_direct_choice([ecodes.KEY_1, ecodes.KEY_2])
        return choice == ecodes.KEY_1

    def wait_for_direct_choice(self, valid_key_codes):
        """Waits for a specific key press from a list of valid keys."""
        while not SHUTDOWN_REQUESTED:
            if time.time() - self.last_activity > config.INACTIVITY_TIMEOUT_SECONDS:
                logger.info("Inactivity timeout in wait_for_direct_choice.")
                return ecodes.KEY_Q

            if not self.keyboard.has_input(config.KEYBOARD_POLL_TIMEOUT):
                continue

            for event in self.keyboard.read_events():
                if event.type == ecodes.EV_KEY and event.value == 1: # Key press event
                    self.last_activity = time.time()
                    if event.code in valid_key_codes:
                        return event.code

    def show_main_menu(self, is_first_run=False):
        draw = self.display.draw # Use persistent draw object
        draw.rectangle((0, 0, self.display.width, self.display.height), fill=255) # Clear the buffer
        
        title_y = self.display.height // 3
        y = self.display._draw_text_centered(draw, title_y, "AdaWriter", self.display.fonts['title'])
        y += 40 

        menu_items = ["1. Daily Journal", "2. Projects"]
        for item in menu_items:
            y = self.display._draw_text_centered(draw, y, item, self.display.fonts['menu']) + 10
        
        indicator_text = self._get_active_indicator_text()
        if indicator_text:
            bbox = self.display.fonts['status'].getbbox(indicator_text)
            text_w = bbox[2] - bbox[0]
            draw.text((self.display.width - config.TEXT_MARGIN - text_w, 10), indicator_text, font=self.display.fonts['status'], fill=0)

        self.display._draw_text_centered(draw, self.display.height - 20, "W for Wi-Fi, Q to Quit", self.display.fonts['footer'])
        
        # On the very first run, we don't need to refresh here because the DisplayManager will do it.
        # For all subsequent calls (e.g., returning from another screen), we do a full refresh.
        if not is_first_run:
            self.display.display_image(is_full_refresh=True)

    def show_message(self, message, duration_sec=3, fatal_error=False, full_refresh=True):
        """Displays a message on the screen for a certain duration."""
        self.display.draw.rectangle((0, 0, self.display.width, self.display.height), fill=255)
        # Use _draw_wrapped_text to handle multi-line and long messages correctly.
        # We need to calculate the starting y-position to center it vertically.
        y_start = self.display.height // 3 # A reasonable starting point
        self.display._draw_wrapped_text(y_start, message, self.display.fonts['menu'], margin=config.TEXT_MARGIN, centered=True)
        self.display.display_image(is_full_refresh=full_refresh)
        
        if fatal_error:
            time.sleep(10)
        else:
            pygame.time.wait(int(duration_sec * 1000))

    def show_journal(self):
        """Finds and opens today's journal file."""
        today = date.today()
        journal_filename = f"{today.strftime('%Y-%m-%d')}.txt"
        journal_path = os.path.join(self.projects_dir, journal_filename)
        
        # Ensure the daily file exists before opening it.
        if not os.path.exists(journal_path):
            journal_content = f"{today.strftime('%B %d, %Y')}\n\n"
            with open(journal_path, 'w', encoding='utf-8') as f: f.write(journal_content)
            logger.info(f"Created new daily journal: {journal_filename}")
        self.edit_project(file_path=journal_path, editor_title="Daily Journal", is_journal=True) # Always edit the daily file.

    def show_projects_list(self):
        """Displays a scrollable list of project files."""
        files = sorted([f for f in os.listdir(self.projects_dir) if f.endswith('.txt')])
        files = [f for f in files if not (f.count('-') >= 1 and f[:4].isdigit())]
        if not files:
            self.show_message("No projects found.", duration_sec=2)
            return

        selected_index = 0; scroll_offset = 0
        needs_redraw = True
        
        while True:
            if needs_redraw:
                draw = self.display.draw
                draw.rectangle((0, 0, self.display.width, self.display.height), fill=255)
                self.display._draw_text_centered(draw, 30, "Projects", self.display.fonts['heading'])
                draw.line([(20, 50), (self.display.width - 20, 50)], fill=0, width=1)
                list_font = self.display.fonts['list']
                max_items_on_screen = (self.display.height - 100) // (list_font.getbbox("Tg")[3] + 10)
                
                if selected_index < scroll_offset: scroll_offset = selected_index
                if selected_index >= scroll_offset + max_items_on_screen:
                    scroll_offset = selected_index - max_items_on_screen + 1

                y = 70
                for i, filename in enumerate(files[scroll_offset : scroll_offset + max_items_on_screen]):
                    display_index = i + scroll_offset
                    base_name = os.path.splitext(filename)[0]
                    display_name = (base_name[:35] + '...') if len(base_name) > 38 else base_name
                    prefix = "> " if display_index == selected_index else "  "
                    draw.text((20, y), f"{prefix}{display_name}", font=list_font, fill=0)
                    y += list_font.getbbox(filename)[3] + 15

                footer_text = "Enter=Open, R=Rename, N=New, Del=Delete\nESC=Return"
                self.display._draw_text_centered(draw, self.display.height - 25, footer_text, self.display.fonts['footer'])
                self.display.display_image(is_full_refresh=False)
                needs_redraw = False

            choice = self.wait_for_direct_choice([ecodes.KEY_UP, ecodes.KEY_DOWN, ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT, ecodes.KEY_PAGEUP, ecodes.KEY_PAGEDOWN, ecodes.KEY_ENTER, ecodes.KEY_ESC, ecodes.KEY_R, ecodes.KEY_N, ecodes.KEY_DELETE])

            if choice in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                continue
            elif choice == ecodes.KEY_DOWN:
                if self.keyboard.shift_pressed:
                    selected_index = min(len(files) - 1, selected_index + max_items_on_screen)
                else:
                    selected_index = (selected_index + 1) % len(files)
                needs_redraw = True
            elif choice == ecodes.KEY_UP:
                if self.keyboard.shift_pressed:
                    selected_index = max(0, selected_index - max_items_on_screen)
                else:
                    selected_index = (selected_index - 1 + len(files)) % len(files)
                needs_redraw = True
            elif choice == ecodes.KEY_ESC: return
            elif choice == ecodes.KEY_N:
                self.create_new_project()
                return self.show_projects_list()
            elif choice == ecodes.KEY_R:
                if files:
                    self.rename_project_ui(os.path.join(self.projects_dir, files[selected_index]))
                    # After renaming, reload files and redraw the list with a full refresh
                    self.show_message("Reloading list...", duration_sec=0.5, full_refresh=True)
                    return self.show_projects_list()
            elif choice == ecodes.KEY_DELETE:
                if files:
                    if self.confirm_action(f"Delete '{os.path.splitext(files[selected_index])[0]}'?"):
                        os.remove(os.path.join(self.projects_dir, files[selected_index]))
                        self.show_message("Deleted.", duration_sec=2)
                        # After deleting, reload files and redraw the list with a full refresh
                        self.show_message("Reloading list...", duration_sec=0.5, full_refresh=True)
                        return self.show_projects_list()
                    else:
                        needs_redraw = True # Just redraw if deletion is cancelled.
            elif choice == ecodes.KEY_ENTER:
                if files:
                    filepath = os.path.join(self.projects_dir, files[selected_index])
                    self.edit_project(file_path=filepath, editor_title=os.path.splitext(os.path.basename(filepath))[0]) # This was already fixed, but keeping for context
                    needs_redraw = True # Redraw after returning from editor

    def create_new_project(self):
        """Handles the UI for creating a new project file."""
        new_filename_base = self._get_text_from_user("New Project Name")
        if not new_filename_base or not new_filename_base.strip():
            self.show_message("Creation cancelled.", duration_sec=2)
            return
        new_filepath = os.path.join(self.projects_dir, f"{new_filename_base.strip()}.txt")
        with open(new_filepath, 'w', encoding='utf-8') as f: f.write("")
        self.show_message(f"Created\n{os.path.basename(new_filepath)}", duration_sec=2)

    def rename_project_ui(self, old_filepath):
        """Handles the UI for renaming a project file."""
        old_filename = os.path.basename(old_filepath)
        new_filename_base = self._get_text_from_user(f"Rename: {os.path.splitext(old_filename)[0]}", initial_text="")

        if not new_filename_base or not new_filename_base.strip():
            self.show_message("Rename cancelled.", duration_sec=2)
            return
        new_filename = f"{new_filename_base.strip()}.txt"
        new_filepath = os.path.join(self.projects_dir, new_filename)
        if os.path.exists(new_filepath):
            self.show_message("Filename already exists!", duration_sec=2)
            return
        os.rename(old_filepath, new_filepath)
        self.show_message(f"Renamed to\n{new_filename}", duration_sec=2)

    def show_wifi_menu(self):
        """Shows Wi-Fi options: start web server or connect to a new network."""
        draw = self.display.draw
        needs_redraw = True
        while True:
            if needs_redraw:
                draw.rectangle((0, 0, self.display.width, self.display.height), fill=255)
                self.display._draw_text_centered(draw, 30, "Wi-Fi & Network", self.display.fonts['heading'])
                menu_items = ["1. Start Web Server", "2. Connect to New Wi-Fi"]
                y = 100
                for item in menu_items:
                    draw.text((40, y), item, font=self.display.fonts['menu'], fill=0)
                    y += 40
                self.display._draw_text_centered(draw, self.display.height - 25, "ESC to Return", self.display.fonts['footer'])
                self.display.display_image(is_full_refresh=True)
                needs_redraw = False

            choice = self.wait_for_direct_choice([ecodes.KEY_1, ecodes.KEY_2, ecodes.KEY_ESC])
            if choice == ecodes.KEY_1:
                self.show_network_screen()
                needs_redraw = True
            elif choice == ecodes.KEY_2:
                self.show_wifi_setup_screen()
                needs_redraw = True
            elif choice == ecodes.KEY_ESC: break

    def get_ip_address(self):
        """Gets the primary IP address of the device."""
        try:
            for interface in netifaces.interfaces():
                if interface in ['lo']: continue
                ifaddresses = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in ifaddresses:
                    return ifaddresses[netifaces.AF_INET][0]['addr']
        except Exception as e:
            logger.error(f"Could not get IP address: {e}")
        return None

    def start_web_server(self):
        """Starts the Flask web server in a separate thread if not already running."""
        if self.web_server_thread is None or not self.web_server_thread.is_alive():
            self.flask_app = create_web_app(self.projects_dir, self.archive_dir, self.trash_dir)
            self.web_server_thread = threading.Thread(
                target=lambda: self.flask_app.run(host='0.0.0.0', port=8000),
                daemon=True
            )
            self.web_server_thread.start()
            logger.info("Web server started.")

    def show_network_screen(self):
        """Displays the screen for Wi-Fi file transfer."""
        if wifi_manager.get_connection_status() == "Disconnected":
            if self.last_wifi_creds:
                self.show_message(f"Connecting to\n{self.last_wifi_creds['ssid']}...", duration_sec=2, full_refresh=True)
                success, msg = wifi_manager.connect_to_network(
                    self.last_wifi_creds['ssid'], self.last_wifi_creds['password']
                )
                self.show_message(msg, duration_sec=2, full_refresh=True)
                if not success: return
            else:
                self.show_message("No Wi-Fi Connection.", duration_sec=3, full_refresh=True)
                return
        
        self.show_message("Starting server...", duration_sec=1, full_refresh=True)
        self.start_web_server()
        time.sleep(1)
        ip_address = self.get_ip_address()

        draw = self.display.draw
        draw.rectangle((0, 0, self.display.width, self.display.height), fill=255)
        self.display._draw_text_centered(draw, 30, "Wi-Fi Transfer", self.display.fonts['heading'])
        intro_text = "Connect to the AdaWriter from another device on the same Wi-Fi network using this address in a web browser:"
        if ip_address:
            y = self.display._draw_wrapped_text(80, intro_text, self.display.fonts['body'], config.TEXT_MARGIN, centered=True)
            self.display._draw_text_centered(draw, y + 20, f"http://{ip_address}:8000", self.display.fonts['list'])
        else:
            self.display._draw_wrapped_text(130, "Could not get IP address. Check Wi-Fi connection.", self.display.fonts['body'], config.TEXT_MARGIN, centered=True)
        self.display._draw_text_centered(draw, self.display.height - 25, "ESC to Return", self.display.fonts['footer'])
        self.display.display_image(is_full_refresh=True)
        self.wait_for_direct_choice([ecodes.KEY_ESC])

    def _text_input_loop(self, prompt, initial_text="", is_password=False):
        """A robust UI loop for getting a line of text from the user."""
        text = initial_text
        self.keyboard.shift_pressed = False
        cursor_blink_on = True
        last_blink_time = pygame.time.get_ticks()
        
        # Initial full draw of the static elements
        draw = self.display.draw
        draw.rectangle((0, 0, self.display.width, self.display.height), fill=255)
        self.display._draw_wrapped_text(30, prompt, self.display.fonts['heading'], config.TEXT_MARGIN)
        self.display._draw_text_centered(draw, self.display.height - 40, "Enter=Done, ESC=Cancel", self.display.fonts['footer'])
        self.display.display_image(is_full_refresh=True)

        text_area_rect = (0, 80, self.display.width, 150)

        while True:
            current_time_ms = pygame.time.get_ticks()
            if current_time_ms - last_blink_time > 800: # Blink interval
                cursor_blink_on = not cursor_blink_on
                last_blink_time = current_time_ms

            # Redraw the dynamic text area for each frame
            draw.rectangle(text_area_rect, fill=255) # Clear the text area
            display_text = "*" * len(text) if is_password else text
            prompt_prefix = "> "
            draw.text((config.TEXT_MARGIN, 100), f"{prompt_prefix}{display_text}", font=self.display.fonts['editor'], fill=0)
            
            if cursor_blink_on:
                prefix_width = self.display.fonts['editor'].getbbox(prompt_prefix)[2]
                cursor_x_start = config.TEXT_MARGIN + prefix_width + self.display.fonts['editor'].getbbox(display_text)[2]
                cursor_y_start = 100
                draw.rectangle([cursor_x_start, cursor_y_start, cursor_x_start + 10, cursor_y_start + 20], fill=0)
            
            self.display.display_image(is_full_refresh=False)

            # Non-blocking event check
            if self.keyboard.has_input(0.05):
                for event in self.keyboard.read_events():
                    if event.type != ecodes.EV_KEY: continue
                    
                    self.last_activity = time.time()
                    code = event.code

                    if code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                        self.keyboard.shift_pressed = (event.value != 0)
                        continue
                    
                    if event.value != 1: continue # Only handle key presses

                    if code == ecodes.KEY_ENTER: return text
                    elif code == ecodes.KEY_ESC: return None
                    elif code == ecodes.KEY_BACKSPACE:
                        if len(text) > 0: text = text[:-1]
                    else:
                        char_to_add = self._get_char_from_event(code)
                        if char_to_add: text += char_to_add

    def _wait_for_key_press(self, timeout=0.1):
        """Waits for and returns a single key press event."""
        # This loop is problematic for text input as it can miss events.
        # The text input loop should read events directly.
        if self.keyboard.has_input(timeout):
            for event in self.keyboard.read_events():
                if event.type == ecodes.EV_KEY:
                    return event
        return None # Timeout or no event

    def _get_char_from_event(self, code):
        """Helper to get a character from a keyboard event code, respecting shift state."""
        if code in self.keyboard.key_map:
            char_data = self.keyboard.key_map[code]
            if isinstance(char_data, dict):
                return char_data['shifted'] if self.keyboard.shift_pressed else char_data['unshifted']
            elif isinstance(char_data, str) and len(char_data) == 1:
                return char_data
        return None

    def _get_password_from_user(self, ssid):
        return self._text_input_loop(f"Password for {ssid}", is_password=True)

    def _get_text_from_user(self, prompt, initial_text=""):
        return self._text_input_loop(prompt, initial_text=initial_text)

    def show_wifi_setup_screen(self):
        """Displays a list of scanned Wi-Fi networks and allows connection."""
        self.show_message("Scanning for Wi-Fi...", duration_sec=1)
        networks = wifi_manager.scan_for_networks()
        if not networks:
            self.show_message("No Wi-Fi networks found.", duration_sec=3)
            return

        page, items_per_page = 0, 4
        needs_redraw = True
        while True:
            if needs_redraw:
                draw = self.display.draw
                draw.rectangle((0, 0, self.display.width, self.display.height), fill=255)
                self.display._draw_text_centered(draw, 30, "Select Wi-Fi Network", self.display.fonts['heading'])
                page_networks = networks[page * items_per_page : (page + 1) * items_per_page]
                
                y = 60
                for i, net in enumerate(page_networks):
                    ssid = (net['ssid'][:20] + '..') if len(net['ssid']) > 22 else net['ssid']
                    signal_bars = min(int(net['signal']) // 25, 3) + 1
                    signal_str = '▂▄▆█'[:signal_bars]
                    draw.text((config.TEXT_MARGIN, y), f"{i+1}. {ssid}", font=self.display.fonts['list'], fill=0)
                    bbox = self.display.fonts['list'].getbbox(signal_str)
                    signal_w = bbox[2] - bbox[0]
                    draw.text((self.display.width - config.TEXT_MARGIN - signal_w, y), signal_str, font=self.display.fonts['list'], fill=0)
                    y += 35

                footer_parts = ["1-4 to Select", "ESC to Return"]
                if len(networks) > (page + 1) * items_per_page: footer_parts.insert(1, "PgDn")
                self.display._draw_text_centered(draw, self.display.height - 25, ", ".join(footer_parts), self.display.fonts['footer'])
                self.display.display_image(is_full_refresh=True)
                needs_redraw = False

            valid_keys = [ecodes.KEY_ESC]
            if len(networks) > (page + 1) * items_per_page: valid_keys.append(ecodes.KEY_PAGEDOWN)
            if page > 0: valid_keys.append(ecodes.KEY_PAGEUP)
            choice_map = {ecodes.KEY_1: 0, ecodes.KEY_2: 1, ecodes.KEY_3: 2, ecodes.KEY_4: 3}
            valid_keys.extend([k for k,v in choice_map.items() if v < len(page_networks)])
            choice = self.wait_for_direct_choice(valid_keys)

            if choice == ecodes.KEY_ESC: break
            elif choice == ecodes.KEY_PAGEDOWN:
                page += 1
                needs_redraw = True
            elif choice == ecodes.KEY_PAGEUP:
                page -= 1
                needs_redraw = True
            elif choice in choice_map:
                selected_net = page_networks[choice_map[choice]]
                password = ""
                if selected_net['security'] and selected_net['security'] != '--':
                    password = self._get_password_from_user(selected_net['ssid'])
                if password is not None:
                    self.show_message(f"Connecting to\n{selected_net['ssid']}...", duration_sec=1, full_refresh=True)
                    success, message = wifi_manager.connect_to_network(selected_net['ssid'], password)
                    self.show_message(message, duration_sec=3, full_refresh=True)
                    if success:
                        self._save_last_wifi_credentials(selected_net['ssid'], password)
                        self.last_wifi_creds = {'ssid': selected_net['ssid'], 'password': password}
                        break
                else:
                    needs_redraw = True

    def _get_active_indicator_text(self):
        """Returns the text for any active status indicator (word count, time, saved)."""
        current_time_ms = pygame.time.get_ticks()
        if self.word_count_active and (current_time_ms - self.word_count_timer <= config.WORD_COUNT_DISPLAY_DURATION):
            return self.current_word_count_text
        if self.time_display_active and (current_time_ms - self.time_display_timer <= config.WORD_COUNT_DISPLAY_DURATION):
            return self.current_time_text
        if self.save_indicator_active and (current_time_ms - self.save_indicator_timer <= config.AUTO_SAVE_INDICATOR_DURATION):
            return "Saved"
        return ""

    def _update_editor_indicators(self):
        """Manages the state and timers for editor status indicators. Returns True if state changed."""
        changed = False
        current_time_ms = pygame.time.get_ticks()
        
        if self.word_count_active and (current_time_ms - self.word_count_timer > config.WORD_COUNT_DISPLAY_DURATION):
            self.word_count_active = False
            changed = True
        if self.time_display_active and (current_time_ms - self.time_display_timer > config.WORD_COUNT_DISPLAY_DURATION):
            self.time_display_active = False
            changed = True
        if self.save_indicator_active and (current_time_ms - self.save_indicator_timer > config.AUTO_SAVE_INDICATOR_DURATION):
            self.save_indicator_active = False
            changed = True
            
        return changed

    def initiate_shutdown(self):
        logger.info("Shutdown initiated by user or timeout.")
        draw = self.display.draw

        if self.display.shutdown_image:
            self.display.draw.rectangle((0, 0, self.display.width, self.display.height), fill=255)
            
            margin = 20
            brand_font = self.display.fonts['menu']
            brand_text = "AdaWriter"
            brand_y = margin + 10
            self.display._draw_text_centered(draw, brand_y, brand_text, brand_font)

            img_x = (self.display.width - self.display.shutdown_image.width) // 2
            img_y = brand_y + 30
            self.display.image.paste(self.display.shutdown_image, (img_x, img_y))

            quote = "Everything I know, I know because of love."
            quote_font = self.display.fonts['body']
            quote_y = img_y + self.display.shutdown_image.height + 20
            self.display._draw_wrapped_text(quote_y, quote, quote_font, margin, centered=True)
            
            self.display.display_image(is_full_refresh=True)
        
        self.display.sleep()
        pygame.quit()
        logger.info("Initiating system shutdown command.")
        os.system("sudo shutdown -h now")
        sys.exit(0)
    
    def edit_project(self, file_path, editor_title="Editor", is_journal=False):
        """Creates and runs a TextEditor instance for a given file."""
        editor = TextEditor(self.display, self.keyboard, self)
        editor.run(file_path, editor_title, is_journal)

class TextEditor:
    """Encapsulates all logic for the text editing experience."""
    def __init__(self, display_manager, keyboard, app_controller):
        self.display = display_manager
        self.keyboard = keyboard
        self.app = app_controller
        self.renderer = EditorRenderer(display_manager, app_controller) # New
        
        self.last_activity_time = 0
        self.cursor_inactivity_timeout = 5 # seconds
        self.cursor_blink_on = True
        self.last_blink_time = 0
        self.BLINK_INTERVAL_MS = 800
        self.partial_refresh_count = 0
        self.FULL_REFRESH_INTERVAL = 100 # Force a full refresh after this many partials

    def _get_wrapped_lines(self, source_lines):
        """
        Performs soft-wrapping on the source text to fit the display width.
        Returns the display lines and the source line index for each display line.
        """
        display_lines = []
        source_line_map = []
        font = self.display.fonts['editor']
        max_width = self.display.width - (2 * config.TEXT_MARGIN)

        for i, line in enumerate(source_lines):
            if not line:
                display_lines.append("")
                source_line_map.append(i)
                continue

            words = line.split(' ')
            current_line_text = ""
            for word in words:
                word_with_space = word + " "
                if font.getbbox(current_line_text + word)[2] > max_width:
                    display_lines.append(current_line_text.rstrip())
                    source_line_map.append(i)
                    current_line_text = word_with_space
                else:
                    current_line_text += word_with_space
            display_lines.append(current_line_text.rstrip())
            source_line_map.append(i)
        return display_lines, source_line_map

    def _handle_editor_input(self, event, editor_state):
        """Processes keyboard input and modifies editor state. Returns True if the layout might have changed."""
        lines, cursor_x, cursor_y = editor_state['lines'], editor_state['cursor_x'], editor_state['cursor_y']
        code = event.code
        
        if code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
            self.keyboard.shift_pressed = (event.value != 0)
            return

        if event.value != 1: return

        editor_state['cursor_visible'] = True
        editor_state['content_changed'] = True
        
        if code in (ecodes.KEY_UP, ecodes.KEY_DOWN, ecodes.KEY_LEFT, ecodes.KEY_RIGHT):
            if code == ecodes.KEY_UP:
                if cursor_y > 0:
                    editor_state['cursor_y'] -= 1
                    editor_state['cursor_x'] = min(cursor_x, len(lines[editor_state['cursor_y']]))
            elif code == ecodes.KEY_DOWN:
                if cursor_y < len(lines) - 1:
                    editor_state['cursor_y'] += 1
                    editor_state['cursor_x'] = min(cursor_x, len(lines[editor_state['cursor_y']]))
            elif code == ecodes.KEY_LEFT:
                if cursor_x > 0:
                    editor_state['cursor_x'] -= 1
                elif cursor_y > 0:
                    editor_state['cursor_y'] -= 1
                    editor_state['cursor_x'] = len(lines[editor_state['cursor_y']])
            elif code == ecodes.KEY_RIGHT:
                if cursor_x < len(lines[cursor_y]):
                    editor_state['cursor_x'] += 1
                elif cursor_y < len(lines) - 1:
                    editor_state['cursor_y'] += 1
                    editor_state['cursor_x'] = 0
        elif code == ecodes.KEY_ENTER:
            editor_state['layout_changed'] = True
            current_line = lines[cursor_y]
            lines[cursor_y] = current_line[:cursor_x]
            lines.insert(cursor_y + 1, current_line[cursor_x:])
            editor_state['cursor_y'] += 1
            editor_state['cursor_x'] = 0
        elif code == ecodes.KEY_BACKSPACE:
            if cursor_x > 0:
                lines[cursor_y] = lines[cursor_y][:cursor_x - 1] + lines[cursor_y][cursor_x:]
                editor_state['cursor_x'] -= 1
            elif cursor_y > 0:
                original_line_content = lines.pop(cursor_y)
                prev_line_len = len(lines[cursor_y - 1])
                lines[cursor_y - 1] += original_line_content
                editor_state['cursor_y'] -= 1
                editor_state['cursor_x'] = prev_line_len
                editor_state['layout_changed'] = True
        elif code in (ecodes.KEY_F1, ecodes.KEY_F2): # This was the previous fix, now we adjust the main loop
            editor_state['timers_changed'] = True # Force header/footer redraw for status indicators
            if code == ecodes.KEY_F1:
                word_count = len("\n".join(lines).split())
                self.app.current_word_count_text = f"Words: {word_count}"
                self.app.word_count_active, self.app.word_count_timer = True, pygame.time.get_ticks()
            else:
                self.app.current_time_text = datetime.now().strftime("%I:%M %p")
                self.app.time_display_active, self.app.time_display_timer = True, pygame.time.get_ticks()
        else:
            char_to_add = self.app._get_char_from_event(code)
            if char_to_add:
                lines[cursor_y] = lines[cursor_y][:cursor_x] + char_to_add + lines[cursor_y][cursor_x:]
                editor_state['cursor_x'] += len(char_to_add)

    def _calculate_cursor_on_display(self, display_lines, source_line_map, source_cursor_y, source_cursor_x):
        """Calculates the cursor's (y, x) position on the wrapped display lines."""
        if not display_lines or not (0 <= source_cursor_y < len(source_line_map)):
            return 0, 0

        try:
            first_display_line_index = source_line_map.index(source_cursor_y)
        except ValueError:
            return 0, 0

        char_offset = 0
        for display_y in range(first_display_line_index, len(display_lines)):
            if source_line_map[display_y] != source_cursor_y:
                prev_line_y = display_y - 1
                prev_line_x = len(display_lines[prev_line_y])
                return prev_line_y, prev_line_x

            current_display_line = display_lines[display_y]
            line_len_with_space = len(current_display_line) + 1

            if source_cursor_x <= char_offset + len(current_display_line):
                display_x = source_cursor_x - char_offset
                return display_y, display_x
            
            char_offset += line_len_with_space
        
        last_line_y = len(display_lines) - 1
        last_line_x = len(display_lines[last_line_y])
        return last_line_y, last_line_x

    def run(self, file_path, editor_title="Editor", is_journal=False):
        """Prepares and launches the main text editor loop with improved refresh logic."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                initial_content = f.read()
            lines = initial_content.splitlines() if initial_content else [""]
            if is_journal:
                current_time = datetime.now().strftime("%I:%M%p").lower()
                if not lines or not lines[-1].startswith("---"):
                    lines.append("")
                    lines.append(f"--- {current_time} ---")
                    lines.append("")
            cursor_y = len(lines) - 1
            cursor_x = len(lines[cursor_y])
        except (IOError, FileNotFoundError):
            logger.warning(f"File {file_path} not found, will create on save.")
            lines = [""]
            cursor_y = 0
            cursor_x = 0

        self._main_loop(file_path, lines, cursor_x, cursor_y, editor_title, is_journal)

    def _main_loop(self, file_path, lines, cursor_x, cursor_y, editor_title, is_journal):
        """Main loop for the text editor with optimized partial refresh."""
        editor_font = self.display.fonts['editor']
        line_height = (editor_font.getbbox("Tg")[3] - editor_font.getbbox("Tg")[1]) + 4
        max_lines_on_screen = (self.display.height - config.EDITOR_HEADER_HEIGHT - config.EDITOR_FOOTER_HEIGHT) // line_height

        display_lines, source_line_map = self._get_wrapped_lines(lines)
        initial_cursor_display_y, _ = self._calculate_cursor_on_display(display_lines, source_line_map, cursor_y, cursor_x)
        scroll_offset = max(0, initial_cursor_display_y - (max_lines_on_screen // 2))

        editor_state = {
            'lines': lines, 'cursor_x': cursor_x, 'cursor_y': cursor_y, 'scroll_offset': scroll_offset,
            'title': editor_title, 'is_journal': is_journal, 'cursor_visible': True,
            'layout_changed': False, 'content_changed': False, 'timers_changed': False
        }

        self.keyboard.shift_pressed = False
        self.last_activity_time = time.time()
        self.last_blink_time = pygame.time.get_ticks()
        self.cursor_blink_on = True
        self.partial_refresh_count = 0

        # Initial full draw
        self.display.draw.rectangle((0, 0, self.display.width, self.display.height), fill=255)
        cursor_display_pos = self._calculate_cursor_on_display(display_lines, source_line_map, editor_state['cursor_y'], editor_state['cursor_x'])
        self.renderer.draw_ui(self.display.draw, editor_state, display_lines, cursor_display_pos, self.cursor_blink_on)
        self.display.display_image(is_full_refresh=True)
        self.partial_refresh_count = 0
        content_changed_since_last_save = False

        while True:
            # --- Event Handling ---
            if self.keyboard.has_input(0.05):
                for event in self.keyboard.read_events():
                    if event.type != ecodes.EV_KEY: continue

                    self.app.last_activity = time.time()
                    self.last_activity_time = time.time()
                    self.cursor_blink_on = True
                    self.last_blink_time = pygame.time.get_ticks()

                    if event.code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                        self.keyboard.shift_pressed = (event.value != 0) # Handle both press (1) and release (0)
                        continue # Continue to next event

                    if event.value != 1: continue # Only process key-down for other keys

                    content_changed_since_last_save = True

                    if event.code == ecodes.KEY_ESC:
                        if content_changed_since_last_save:
                            with open(file_path, 'w', encoding='utf-8') as f: f.write('\n'.join(editor_state['lines']) + '\n')
                            self.app.save_indicator_active, self.app.save_indicator_timer = True, pygame.time.get_ticks()
                        if is_journal: self.app._update_monthly_journal(file_path)
                        return # Exit editor
                    self._handle_editor_input(event, editor_state)
            
            # --- State Updates from Timers ---
            current_time_ms = pygame.time.get_ticks()
            if time.time() - self.last_activity_time > self.cursor_inactivity_timeout:
                if editor_state['cursor_visible']:
                    editor_state['cursor_visible'] = False
                    editor_state['content_changed'] = True

            if editor_state['cursor_visible'] and (current_time_ms - self.last_blink_time > self.BLINK_INTERVAL_MS):
                self.cursor_blink_on = not self.cursor_blink_on
                self.last_blink_time = current_time_ms
                editor_state['content_changed'] = True

            if self.app._update_editor_indicators():
                editor_state['timers_changed'] = True

            if content_changed_since_last_save and (time.time() - self.last_activity_time > (config.INACTIVITY_SAVE_TIMEOUT / 1000)):
                with open(file_path, 'w', encoding='utf-8') as f: f.write("\n".join(editor_state['lines']) + '\n')
                self.app.save_indicator_active, self.app.save_indicator_timer = True, pygame.time.get_ticks()
                content_changed_since_last_save = False
                editor_state['timers_changed'] = True
            
            # --- Rendering Logic ---
            # A timer change (like F1/F2) should not force a full refresh on its own.
            # --- Rendering Logic: Determine what needs to be redrawn ---
            is_full_refresh_needed = editor_state['layout_changed'] or self.partial_refresh_count >= self.FULL_REFRESH_INTERVAL
            is_content_refresh_needed = editor_state['content_changed']
            is_header_footer_refresh_needed = editor_state['timers_changed']

            if is_full_refresh_needed or is_content_refresh_needed or is_header_footer_refresh_needed:
                display_lines, source_line_map = self._get_wrapped_lines(editor_state['lines'])
                cursor_display_pos = self._calculate_cursor_on_display(display_lines, source_line_map, editor_state['cursor_y'], editor_state['cursor_x'])

                # Adjust scroll offset if cursor moves out of view
                if cursor_display_pos[0] < editor_state['scroll_offset']:
                    editor_state['scroll_offset'] = cursor_display_pos[0]
                if cursor_display_pos[0] >= editor_state['scroll_offset'] + max_lines_on_screen:
                    editor_state['scroll_offset'] = cursor_display_pos[0] - max_lines_on_screen + 1

                if is_full_refresh_needed:
                    logger.debug("Performing full refresh (layout change or interval).")
                    self.display.draw.rectangle((0, 0, self.display.width, self.display.height), fill=255)
                    self.renderer.draw_ui(self.display.draw, editor_state, display_lines, cursor_display_pos, self.cursor_blink_on)
                    self.display.display_image(is_full_refresh=True)
                    self.partial_refresh_count = 0
                else:
                    # For partial updates, only redraw the necessary sections
                    if is_content_refresh_needed:
                        logger.debug("Partial refresh: content changed.")
                        editor_area = (0, config.EDITOR_HEADER_HEIGHT, self.display.width, self.display.height - config.EDITOR_FOOTER_HEIGHT)
                        self.display.draw.rectangle(editor_area, fill=255)
                        self.renderer.draw_text_area(self.display.draw, editor_state, display_lines, cursor_display_pos, self.cursor_blink_on)
                    
                    if is_header_footer_refresh_needed:
                        logger.debug("Partial refresh: header/footer changed.")
                        self.renderer.draw_header_and_footer(self.display.draw, editor_state)

                    self.display.display_image(is_full_refresh=False)
                    self.partial_refresh_count += 1
                
                # Reset dirty flags
                editor_state['layout_changed'] = False
                editor_state['content_changed'] = False
                editor_state['timers_changed'] = False


# --- MAIN EXECUTION ---
if __name__ == '__main__':
    if EINK_DRIVER_AVAILABLE:
        logger.info(f"waveshare_epd library version: {getattr(waveshare_epd, '__version__', 'N/A')}")
        logger.info(f"waveshare_epd library path: {waveshare_epd.__file__}")
    else:
        logger.warning("waveshare_epd library not found. Running in simulation mode.")

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    signal.signal(signal.SIGINT, handle_shutdown_signal)

    original_stderr = sys.stderr
    # Pass the driver availability status to the DisplayManager
    display_manager = DisplayManager(eink_driver_available=EINK_DRIVER_AVAILABLE)
    try:
        logger.info("AdaWriter starting up.")
        keyboard_device = Keyboard()
        app = AdaWriter(keyboard_device, display_manager)
        app.show_main_menu(is_first_run=True) # Draw the initial UI before the first refresh
        display_manager.start() # This will now display the pre-drawn menu
        app.run()
    except Exception as e:
        logger.error(f"--- CRITICAL STARTUP FAILURE: {e} ---", exc_info=True)
        traceback.print_exc(file=original_stderr)
        try:
            display_manager.show_message(f"FATAL STARTUP ERROR:\n{e}", fatal_error=True)
            time.sleep(20)
        except Exception as display_e:
            logger.error(f"Could not even show error on display: {display_e}")
            traceback.print_exc(file=original_stderr)
    finally:
        logger.info("AdaWriter shutting down.")
        pygame.quit()
        sys.exit(0)