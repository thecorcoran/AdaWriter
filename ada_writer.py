# ada_writer.py (Version 3.0 - Editor Performance Update)
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import sys
import pygame
import threading
import time
import subprocess
import traceback
from evdev import ecodes
from datetime import date, datetime
import netifaces

# Local imports
import config
from keyboard import Keyboard, KEY_MAP
from logger import setup_logger
from web_server import create_web_app
from display_manager import DisplayManager
import wifi_manager

pygame.init()
logger = setup_logger()

class AdaWriter:
    def __init__(self, keyboard_device):
        self.keyboard = keyboard_device
        logger.info("Initializing AdaWriter application...")
        self.display = DisplayManager()
        self.last_activity = time.time()
        self.projects_dir = os.path.join(config.BASE_DIR, config.PROJECTS_ROOT_FOLDER)
        os.makedirs(self.projects_dir, exist_ok=True)
        self._ensure_project_files_exist()
        self.last_wifi_creds = self._load_last_wifi_credentials()
        
        self.web_server_thread = None
        self.flask_app = None

        # Status indicators
        self.save_indicator_active = False; self.save_indicator_timer = 0
        self.word_count_active = False; self.word_count_timer = 0; self.current_word_count_text = ""
        self.time_display_active = False; self.time_display_timer = 0; self.current_time_text = ""
        self.editor_view_top_line = 0

    def _update_monthly_journal(self, daily_file_path):
        """Appends the content of a daily journal to its corresponding monthly journal."""
        try:
            with open(daily_file_path, 'r', encoding='utf-8') as f:
                daily_content = f.read()

            file_basename = os.path.basename(daily_file_path) # e.g., "2023-10-27.txt"
            monthly_filename = f"{file_basename[:7]}.txt" # e.g., "2023-10.txt"
            monthly_path = os.path.join(self.projects_dir, monthly_filename)

            with open(monthly_path, 'a', encoding='utf-8') as f:
                f.write(daily_content)
            logger.info(f"Updated monthly journal {monthly_filename}")
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
            should_shutdown = False
            while not should_shutdown:
                if time.time() - self.last_activity > config.INACTIVITY_TIMEOUT_SECONDS:
                    logger.info("Inactivity timeout reached. Shutting down.")
                    should_shutdown = True
                    continue
    
                self.show_main_menu()
                choice = self.wait_for_direct_choice([ecodes.KEY_1, ecodes.KEY_2, ecodes.KEY_W, ecodes.KEY_Q])
                
                if choice == ecodes.KEY_1: self.show_journal()
                elif choice == ecodes.KEY_2: self.show_projects_list()
                elif choice == ecodes.KEY_W: self.show_wifi_menu()
                elif choice == ecodes.KEY_Q: should_shutdown = True
            
            if should_shutdown:
                self.initiate_shutdown()

        except Exception as e:
            logger.critical(f"--- UNHANDLED EXCEPTION IN APP RUNTIME ---", exc_info=True)
            self.show_message(f"Runtime Error:\n{e}", fatal_error=True)
            self.initiate_shutdown()

    def wait_for_direct_choice(self, valid_key_codes):
        """Waits for a specific key press from a list of valid keys."""
        while True:
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

    def show_main_menu(self):
        draw = self.display.draw # Use persistent draw object
        draw.rectangle((0, 0, self.display.width, self.display.height), fill=255) # Clear the buffer
        
        # AdaWriter title centered in the top 1/3 of the screen
        title_y = self.display.height // 3
        y = self.display._draw_text_centered(draw, title_y, "AdaWriter", self.display.fonts['title'])
        y += 20

        menu_items = ["1. Daily Journal", "2. Projects"]
        item_width = self.display.width // len(menu_items)
        for i, item in enumerate(menu_items):
            x = (item_width * i) + (item_width - self.display.fonts['menu'].getbbox(item)[2]) // 2
            draw.text((x, y), item, font=self.display.fonts['menu'], fill=0)
        
        indicator_text = self._get_active_indicator_text()
        if indicator_text:
            bbox = self.display.fonts['status'].getbbox(indicator_text)
            text_w = bbox[2] - bbox[0]
            draw.text((self.display.width - config.TEXT_MARGIN - text_w, 10), indicator_text, font=self.display.fonts['status'], fill=0)

        self.display._draw_text_centered(draw, self.display.height - 20, "W for Wi-Fi, Q to Quit", self.display.fonts['footer'])
        self.display.display_image(is_full_refresh=True)

    def show_message(self, message, duration_sec=3, fatal_error=False, full_refresh=True):
        """Displays a message on the screen for a certain duration."""
        # Use persistent draw object and clear it for the message
        self.display.draw.rectangle((0, 0, self.display.width, self.display.height), fill=255)
        self.display._draw_text_centered(self.display.draw, self.display.height // 2, message, self.display.fonts['menu'])
        self.display.display_image(is_full_refresh=False)
        
        if fatal_error:
            time.sleep(10)
        else:
            pygame.time.wait(int(duration_sec * 1000))

    def show_journal(self):
        """Finds and opens today's journal file."""
        today = date.today()
        journal_filename = f"{today.strftime('%Y-%m-%d')}.txt"
        journal_path = os.path.join(self.projects_dir, journal_filename)
        self.edit_project(file_path=journal_path, editor_title="Daily Journal", is_journal=True)

    def show_projects_list(self):
        """Displays a scrollable list of project files."""
        files = sorted([f for f in os.listdir(self.projects_dir) if f.endswith('.txt')])
        files = [f for f in files if not (f.count('-') >= 1 and f[:4].isdigit())]
        if not files:
            self.show_message("No projects found.", duration_sec=2)
            return

        selected_index = 0; scroll_offset = 0
        needs_full_refresh = True # Start with a full refresh
        
        while True:
            draw = self.display.draw # Use persistent draw object
            draw.rectangle((0, 0, self.display.width, self.display.height), fill=255) # Clear buffer for redraw
            self.display._draw_text_centered(draw, 10, "Projects", self.display.fonts['heading'])
            draw.line([(20, 50), (self.display.width - 20, 50)], fill=0, width=1)
            list_font = self.display.fonts['list']
            max_items_on_screen = (self.display.height - 100) // (list_font.getbbox("Tg")[3] + 10)
            
            if selected_index < scroll_offset: scroll_offset = selected_index
            if selected_index >= scroll_offset + max_items_on_screen:
                scroll_offset = selected_index - max_items_on_screen + 1

            y = 60
            for i, filename in enumerate(files[scroll_offset : scroll_offset + max_items_on_screen]):
                display_index = i + scroll_offset
                display_name = (filename[:35] + '...') if len(filename) > 38 else filename
                prefix = "> " if display_index == selected_index else "  "
                draw.text((20, y), f"{prefix}{display_name}", font=list_font, fill=0)
                y += list_font.getbbox(filename)[3] + 10

            footer_text = "Enter=Open, R=Rename, N=New, Esc=Back"
            if len(files) > max_items_on_screen: # Use arrows for clarity
                footer_text = "Shift+↑/↓=PgUp/Dn, " + footer_text

            self.display._draw_text_centered(draw, self.display.height - 25, footer_text, self.display.fonts['footer'])
            self.display.display_image(is_full_refresh=needs_full_refresh)
            needs_full_refresh = False # Subsequent updates can be partial

            choice = self.wait_for_direct_choice([ecodes.KEY_UP, ecodes.KEY_DOWN, ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT, ecodes.KEY_PAGEUP, ecodes.KEY_PAGEDOWN, ecodes.KEY_ENTER, ecodes.KEY_ESC, ecodes.KEY_R, ecodes.KEY_N])

            if choice in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                # The wait function will handle the key up/down state, just continue
                continue
            elif choice == ecodes.KEY_DOWN:
                if self.keyboard.shift_pressed:
                    selected_index = min(len(files) - 1, selected_index + max_items_on_screen)
                else:
                    selected_index = (selected_index + 1) % len(files)
            elif choice == ecodes.KEY_UP:
                if self.keyboard.shift_pressed:
                    selected_index = max(0, selected_index - max_items_on_screen)
                else:
                    selected_index = (selected_index - 1 + len(files)) % len(files)
            elif choice == ecodes.KEY_ESC: return
            elif choice == ecodes.KEY_N:
                self.create_new_project()
                return self.show_projects_list()
            elif choice == ecodes.KEY_R:
                if files:
                    self.rename_project_ui(os.path.join(self.projects_dir, files[selected_index]))
                    return self.show_projects_list()
            elif choice == ecodes.KEY_ENTER:
                if files:
                    filepath = os.path.join(self.projects_dir, files[selected_index])
                    self.edit_project(file_path=filepath, editor_title=os.path.splitext(os.path.basename(filepath))[0])
                    return

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
        new_filename_base = self._get_text_from_user(f"Rename: {old_filename}", initial_text=os.path.splitext(old_filename)[0])

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
        draw = self.display.draw # Use persistent draw object
        while True:
            self.display.draw.rectangle((0, 0, self.display.width, self.display.height), fill=255) # Clear for menu
            self.display._draw_text_centered(draw, 30, "Wi-Fi & Network", self.display.fonts['heading'])
            menu_items = ["1. Start Web Server", "2. Connect to New Wi-Fi"]
            y = 100
            for item in menu_items:
                y = self.display._draw_text_centered(draw, y, item, self.display.fonts['menu']) + 10
            self.display._draw_text_centered(self.display.draw, self.display.height - 20, "ESC to Return", self.display.fonts['footer'])
            self.display.display_image(is_full_refresh=True)

            choice = self.wait_for_direct_choice([ecodes.KEY_1, ecodes.KEY_2, ecodes.KEY_ESC])
            if choice == ecodes.KEY_1: self.show_network_screen()
            elif choice == ecodes.KEY_2: self.show_wifi_setup_screen()
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
            self.flask_app = create_web_app(self.projects_dir)
            self.web_server_thread = threading.Thread(
                target=lambda: self.flask_app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False),
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

        draw = self.display.draw # Use persistent draw object
        self.display.draw.rectangle((0, 0, self.display.width, self.display.height), fill=255) # Clear for network screen
        self.display._draw_text_centered(draw, 30, "Wi-Fi Transfer", self.display.fonts['heading'])
        if ip_address:
            y = self.display._draw_wrapped_text(80, "Connect to the AdaWriter from another device on the same Wi-Fi network using this address in a web browser:", self.display.fonts['body'], config.TEXT_MARGIN)
            self.display._draw_text_centered(draw, y + 20, f"http://{ip_address}:8000", self.display.fonts['list'])
        else:
            self.display._draw_wrapped_text(130, "Could not get IP address. Check Wi-Fi connection.", self.display.fonts['body'], config.TEXT_MARGIN)
        self.display._draw_text_centered(self.display.draw, self.display.height - 30, "Press ESC to return to the main menu", self.display.fonts['footer'])
        self.display.display_image(is_full_refresh=True)
        self.wait_for_direct_choice([ecodes.KEY_ESC])

    def _text_input_loop(self, prompt, initial_text="", is_password=False):
        """A generic UI loop for getting a line of text from the user."""
        text = initial_text
        self.keyboard.shift_pressed = False
        content_changed = True

        while True:
            if content_changed: # This block now operates on the persistent image
                draw = self.display.draw
                self.display.draw.rectangle((0, 0, self.display.width, self.display.height), fill=255) # Clear for text input
                self.display._draw_wrapped_text(30, prompt, self.display.fonts['heading'], config.TEXT_MARGIN)
                display_text = "*" * len(text) if is_password else text
                draw.text((config.TEXT_MARGIN, 100), f"> {display_text}", font=self.display.fonts['editor'], fill=0)
                cursor_pos_x = config.TEXT_MARGIN + 12 + self.display.fonts['editor'].getbbox(display_text)[2]
                draw.line([(cursor_pos_x, 100), (cursor_pos_x, 100 + 20)], fill=0, width=1)
                self.display._draw_text_centered(self.display.draw, self.display.height - 40, "Enter=Done, ESC=Cancel", self.display.fonts['footer'])
                self.display.display_image(is_full_refresh=False)
                content_changed = False

            if not self.keyboard.has_input(0.1): continue

            for event in self.keyboard.read_events():
                if event.type != ecodes.EV_KEY: continue
                self.last_activity = time.time()
                code = event.code

                if code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                    self.keyboard.shift_pressed = (event.value != 0)
                    continue

                if event.value != 1: continue

                content_changed = True
                if code == ecodes.KEY_ENTER: return text
                elif code == ecodes.KEY_ESC: return None
                elif code == ecodes.KEY_BACKSPACE:
                    if len(text) > 0: text = text[:-1]
                else:
                    char_to_add = self._get_char_from_event(code)
                    if char_to_add: text += char_to_add
                    else: content_changed = False

    def _get_char_from_event(self, code):
        """Helper to get a character from a keyboard event code, respecting shift state."""
        if code in KEY_MAP:
            char_data = KEY_MAP[code]
            if isinstance(char_data, dict):
                return char_data['shifted'] if self.keyboard.shift_pressed else char_data['unshifted']
            # Handles non-dict entries like KEY_SPACE: ' '
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
        while True:
            draw = self.display.draw # Use persistent draw object
            self.display.draw.rectangle((0, 0, self.display.width, self.display.height), fill=255) # Clear for Wi-Fi list
            self.display._draw_text_centered(draw, 15, "Wi-Fi Networks", self.display.fonts['heading'])
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
            self.display._draw_text_centered(self.display.draw, self.display.height - 20, ", ".join(footer_parts), self.display.fonts['footer'])
            self.display.display_image()

            valid_keys = [ecodes.KEY_ESC]
            if len(networks) > (page + 1) * items_per_page: valid_keys.append(ecodes.KEY_PAGEDOWN)
            if page > 0: valid_keys.append(ecodes.KEY_PAGEUP)
            choice_map = {ecodes.KEY_1: 0, ecodes.KEY_2: 1, ecodes.KEY_3: 2, ecodes.KEY_4: 3}
            valid_keys.extend([k for k,v in choice_map.items() if v < len(page_networks)])
            choice = self.wait_for_direct_choice(valid_keys)

            if choice == ecodes.KEY_ESC: break
            elif choice == ecodes.KEY_PAGEDOWN: page += 1
            elif choice == ecodes.KEY_PAGEUP: page -= 1
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

    def initiate_shutdown(self):
        logger.info("Shutdown initiated by user or timeout.")
        draw = self.display.draw # Use persistent draw object
        
        # First, show "Shutting down..."
        self.display.draw.rectangle((0, 0, self.display.width, self.display.height), fill=255)
        self.display._draw_text_centered(draw, self.display.height // 2, "Shutting down...", self.display.fonts['footer'])
        self.display.display_image(is_full_refresh=True)
        time.sleep(2) # Keep the message on screen for a moment

        if self.display.shutdown_image:
            self.display.draw.rectangle((0, 0, self.display.width, self.display.height), fill=255) # Clear for shutdown screen
            
            quote = "Everything I know, I know because of love."
            
            # Center the image horizontally, and place it vertically centered in the top half
            img_x = (self.display.width - self.display.shutdown_image.width) // 2
            img_y = (self.display.height // 2 - self.display.shutdown_image.height) // 2
            self.display.image.paste(self.display.shutdown_image, (img_x, img_y))

            # Center the quote above the image.
            quote_y = img_y - 60 # Adjust this value as needed for spacing
            self.display._draw_text_centered(draw, quote_y, quote, self.display.fonts['body'])

            # Position AdaWriter halfway between the image and the bottom of the display, using the title font.
            brand_y = (img_y + self.display.shutdown_image.height + self.display.height) // 2
            self.display._draw_text_centered(draw, brand_y, "AdaWriter", self.display.fonts['title'])
            
            self.display.display_image(is_full_refresh=True)
        
        self.display.sleep()
        pygame.quit()
        logger.info("Initiating system shutdown command.")
        os.system("sudo shutdown -h now")
        
        self.display.sleep()
        pygame.quit()
        logger.info("Initiating system shutdown command.")
        os.system("sudo shutdown -h now")
        sys.exit(0)
    
    def edit_project(self, file_path, editor_title="Editor", is_journal=False):
        """Prepares and launches the main text editor loop."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                initial_content = f.read()
            lines = initial_content.splitlines() if initial_content else [""]
            if is_journal:
                # Add a timestamp for the new session
                # But only if the last line isn't already a timestamp (to prevent duplicates)
                current_time = datetime.now().strftime("%I:%M%p").lower()
                if not lines or not lines[-1].startswith("--- "):
                    lines.append("")
                    lines.append(f"--- {current_time} ---")
                    lines.append("")

            # For existing files, place cursor at the very end of the last line.
            cursor_y = max(0, len(lines) - 1)
            cursor_x = len(lines[cursor_y]) if lines else 0

        except (IOError, FileNotFoundError):
            logger.warning(f"File {file_path} not found, will create on save.")
            lines = [""]
            if is_journal:
                # New journal file, create date header and first timestamp.
                lines = [
                    f"{date.today().strftime('%B %d, %Y')}", 
                    "", 
                    f"--- {datetime.now().strftime('%I:%M%p').lower()} ---",
                    ""
                ]
                cursor_y = len(lines) - 1
                cursor_x = 0
            else:
                # For other new files, cursor starts at the beginning.
                cursor_y = 0
                cursor_x = 0

        # Pre-calculate scroll offset to start with the cursor in view.
        # This requires a one-time pre-wrap to be accurate.
        display_lines, source_line_map = self._get_wrapped_lines(lines, cursor_y, cursor_x)
        line_height = self.display.fonts['editor'].getbbox("Tg")[3] + 2
        max_display_lines = (self.display.height - config.EDITOR_HEADER_HEIGHT - config.EDITOR_FOOTER_HEIGHT) // line_height
        
        cursor_display_y, _ = self._calculate_cursor_on_display(display_lines, source_line_map, cursor_y, cursor_x)
        initial_scroll_offset = max(0, cursor_display_y - (max_display_lines // 2))
        
        self._edit_project_loop(file_path, lines, cursor_x, cursor_y, editor_title, is_journal, initial_scroll_offset)

    def _get_wrapped_lines(self, source_lines, cursor_y, cursor_x):
        """
        Performs soft-wrapping on the source text to fit the display width.
        Returns the display lines and the source line index for each display line.
        """
        display_lines = []
        source_line_map = [] # Maps display line index to source line index
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
                word_with_space = word + " " # Add space back for width calculation
                if font.getbbox(current_line_text + word)[2] > max_width:
                    display_lines.append(current_line_text.rstrip())
                    source_line_map.append(i)
                    current_line_text = word_with_space
                else:
                    current_line_text += word_with_space
            display_lines.append(current_line_text.rstrip())
            source_line_map.append(i)
        return display_lines, source_line_map

    def _draw_editor_ui(self, draw, editor_state, display_lines, cursor_display_y, cursor_display_x):
        """A single, consolidated function to draw the editor's UI onto the persistent buffer."""
        editor_font = self.display.fonts['editor']
        line_height = editor_font.getbbox("Tg")[3] + 2

        self.display.draw.rectangle((0, 0, self.display.width, self.display.height), fill=255)
        
        # Header
        self.display._draw_text_centered(draw, 10, editor_state['title'], self.display.fonts['heading'])
        
        # Text content and cursor
        y_pos = config.EDITOR_HEADER_HEIGHT
        max_lines_on_screen = (self.display.height - config.EDITOR_HEADER_HEIGHT - config.EDITOR_FOOTER_HEIGHT) // line_height
        visible_lines = display_lines[editor_state['scroll_offset'] : editor_state['scroll_offset'] + max_lines_on_screen]
        
        for i, line in enumerate(visible_lines):
            current_display_y = i + editor_state['scroll_offset']
            draw.text((config.TEXT_MARGIN, y_pos), line, font=editor_font, fill=0)

            if current_display_y == cursor_display_y:
                if line: # If line has content, calculate position from text
                    line_prefix = line[:cursor_display_x]
                    cursor_pixel_x = config.TEXT_MARGIN + editor_font.getbbox(line_prefix)[2]
                else: # If line is empty, cursor is at the margin
                    cursor_pixel_x = config.TEXT_MARGIN
                draw.line([(cursor_pixel_x, y_pos), (cursor_pixel_x, y_pos + line_height - 2)], fill=0, width=1)
            y_pos += line_height

        # Status indicators (top right)
        indicator_text = self._get_active_indicator_text()
        if indicator_text:
            bbox = self.display.fonts['status'].getbbox(indicator_text)
            text_w = bbox[2] - bbox[0]
            draw.text((self.display.width - config.TEXT_MARGIN - text_w, 10), indicator_text, font=self.display.fonts['status'], fill=0)
        # Footer
        self.display._draw_text_centered(self.display.draw, self.display.height - 25, "Arrows=Move, ESC=Save & Exit, F1=Words, F2=Time", self.display.fonts['footer'])
        
    def _handle_editor_input(self, event, editor_state):
        """Processes keyboard input, modifies editor state, and returns the type of change."""
        lines, cursor_x, cursor_y = editor_state['lines'], editor_state['cursor_x'], editor_state['cursor_y']
        code = event.code
        change_type = None

        if code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
            self.keyboard.shift_pressed = (event.value != 0)
            return change_type

        if event.value != 1: return change_type

        # Default change is a simple content update, requiring a partial refresh
        change_type = "content_update"

        if code in (ecodes.KEY_UP, ecodes.KEY_DOWN, ecodes.KEY_LEFT, ecodes.KEY_RIGHT):
            # --- New WYSIWYG Cursor Movement ---
            # This logic moves the cursor based on what's visible on the display,
            # which is more intuitive with soft-wrapped text.
            
            # 1. Get current display geometry
            display_lines, source_line_map = self._get_wrapped_lines(lines, cursor_y, cursor_x)
            current_display_y, current_display_x = self._calculate_cursor_on_display(display_lines, source_line_map, cursor_y, cursor_x)

            # 2. Calculate target display line
            target_display_y = -1
            if code == ecodes.KEY_UP:
                target_display_y = max(0, current_display_y - 1)
            elif code == ecodes.KEY_DOWN:
                target_display_y = min(len(display_lines) - 1, current_display_y + 1)

            if target_display_y != -1 and target_display_y != current_display_y:
                # 3. Find the new source coordinates from the target display line
                # We try to maintain the horizontal position (current_display_x).
                new_source_y, new_source_x = self._get_source_coords_from_display_coords(
                    display_lines, source_line_map, target_display_y, current_display_x
                )
                
                # 4. Update the editor state
                editor_state['cursor_y'] = new_source_y
                editor_state['cursor_x'] = new_source_x
            
            change_type = "content_update"

        elif code == ecodes.KEY_LEFT:
            original_x, original_y = cursor_x, cursor_y
            if cursor_x > 0:
                editor_state['cursor_x'] -= 1
            elif cursor_y > 0:
                # Move to the end of the previous source line
                prev_line_index = cursor_y - 1
                if prev_line_index in range(len(lines)):
                    editor_state['cursor_y'] = prev_line_index
                    editor_state['cursor_x'] = len(lines[prev_line_index])
            # Only trigger a full refresh if the line actually changes
            change_type = "content_update" if editor_state['cursor_y'] != original_y else "content_update"
        elif code == ecodes.KEY_RIGHT:
            original_x, original_y = cursor_x, cursor_y
            if cursor_x < len(lines[cursor_y]):
                editor_state['cursor_x'] += 1
            elif cursor_y < len(lines) - 1:
                editor_state['cursor_y'] += 1
                editor_state['cursor_x'] = 0
            change_type = "content_update" if editor_state['cursor_y'] != original_y else "content_update"
        elif code == ecodes.KEY_ENTER:
            current_line = lines[cursor_y]
            lines[cursor_y] = current_line[:cursor_x]
            lines.insert(cursor_y + 1, current_line[cursor_x:])
            editor_state['cursor_y'] += 1
            editor_state['cursor_x'] = 0
            change_type = "view_update" # Structural change, may need full refresh
        elif code == ecodes.KEY_BACKSPACE:
            # Unify backspace logic for a more natural feel, especially with wrapping.
            if cursor_x == 0 and cursor_y == 0:
                # At the very beginning of the document, do nothing.
                change_type = None
            elif cursor_x > 0:
                # Standard character deletion
                lines[cursor_y] = lines[cursor_y][:cursor_x - 1] + lines[cursor_y][cursor_x:]
                editor_state['cursor_x'] -= 1
            elif cursor_y > 0:
                # At the start of a source line, join with the previous line.
                original_line_content = lines.pop(cursor_y)
                prev_line_len = len(lines[cursor_y - 1])
                lines[cursor_y - 1] += original_line_content
                editor_state['cursor_y'] -= 1
                editor_state['cursor_x'] = prev_line_len
                change_type = "view_update"
        elif code == ecodes.KEY_F1:
            word_count = len("\n".join(lines).split())
            self.current_word_count_text = f"Words: {word_count}"
            self.word_count_active, self.word_count_timer = True, pygame.time.get_ticks()
            change_type = "view_update" # Indicator popup needs full refresh
        elif code == ecodes.KEY_F2:
            self.current_time_text = datetime.now().strftime("%I:%M %p")
            self.time_display_active, self.time_display_timer = True, pygame.time.get_ticks()
            change_type = "view_update"
        else:
            char_to_add = self._get_char_from_event(code)
            if char_to_add:
                lines[cursor_y] = lines[cursor_y][:cursor_x] + char_to_add + lines[cursor_y][cursor_x:]
                editor_state['cursor_x'] += len(char_to_add)
                change_type = "content_update" # Flag that content has changed.
            else:
                change_type = None # Unhandled key, no change

        return change_type
    
    def _calculate_cursor_on_display(self, display_lines, source_line_map, source_cursor_y, source_cursor_x):
        """Calculates the cursor's (y, x) position on the wrapped display lines."""
        cursor_display_y, cursor_display_x = -1, -1
        if source_line_map and source_cursor_y < len(source_line_map):
            try:
                first_display_line_for_source = source_line_map.index(source_cursor_y)
                remaining_x = source_cursor_x
                
                for i in range(first_display_line_for_source, len(display_lines)):
                    if source_line_map[i] != source_cursor_y: break
                    line_len = len(display_lines[i])
                    if remaining_x <= line_len:
                        cursor_display_y, cursor_display_x = i, remaining_x
                        break
                    remaining_x -= (line_len + 1)
                # If cursor is at the very end of a wrapped line
                if cursor_display_y == -1 and remaining_x >= 0:
                    # This handles the case where the cursor is at the very end of the source line,
                    # which corresponds to the end of the last display line for that source line.
                    last_display_line_for_source = -1
                    for i in range(len(source_line_map) - 1, -1, -1):
                        if source_line_map[i] == source_cursor_y:
                            cursor_display_y, cursor_display_x = i, len(display_lines[i])
                            break
            except (ValueError, IndexError): pass # Gracefully fail
        return cursor_display_y, cursor_display_x

    def _get_source_coords_from_display_coords(self, display_lines, source_line_map, display_y, target_display_x):
        """Converts display (y, x) coordinates back to source (y, x) coordinates."""
        if not (0 <= display_y < len(display_lines)):
            return 0, 0

        source_y = source_line_map[display_y]
        source_x = 0
        
        # Calculate the source_x by summing lengths of previous display lines for the same source line
        for i in range(display_y):
            if source_line_map[i] == source_y:
                source_x += len(display_lines[i]) + 1 # +1 for the space that was split on
        
        source_x += min(target_display_x, len(display_lines[display_y]))
        return source_y, source_x

    def _edit_project_loop(self, file_path, lines, cursor_x, cursor_y, editor_title, is_journal, initial_scroll_offset=0):
        """The refactored main loop for the text editor, optimized for responsiveness."""
        editor_state = {
            'lines': lines, 'cursor_x': cursor_x, 'cursor_y': cursor_y, 'scroll_offset': initial_scroll_offset, 
            'title': editor_title, 'is_journal': is_journal
        }
        draw = self.display.draw # Use the persistent draw object from DisplayManager
        
        change_type = "view_update" # Start with a full draw to show initial state
        last_save_time = pygame.time.get_ticks()
        content_changed_since_last_save = False
        self.keyboard.shift_pressed = False
        
        # Pre-calculate for the loop
        line_height = self.display.fonts['editor'].getbbox("Tg")[3] + 2

        while True:
            current_time_ms = pygame.time.get_ticks()

            if change_type:
                # --- EFFICIENT DRAW CYCLE ---
                # 1. Calculate wrapped text and where the cursor should be.
                display_lines, source_line_map = self._get_wrapped_lines(editor_state['lines'], editor_state['cursor_y'], editor_state['cursor_x'])
                cursor_display_y, cursor_display_x = self._calculate_cursor_on_display(display_lines, source_line_map, editor_state['cursor_y'], editor_state['cursor_x'])

                # 2. Adjust scroll offset based on new cursor position (Typewriter scrolling).
                max_display_lines = (self.display.height - config.EDITOR_HEADER_HEIGHT - config.EDITOR_FOOTER_HEIGHT) // line_height
                scroll_top_margin = int(max_display_lines * 0.3)  # e.g., 30% from top
                scroll_bottom_margin = int(max_display_lines * 0.7) # e.g., 70% from top

                if cursor_display_y < editor_state['scroll_offset'] + scroll_top_margin:
                    editor_state['scroll_offset'] = max(0, cursor_display_y - scroll_top_margin) # Scroll up
                elif cursor_display_y >= editor_state['scroll_offset'] + scroll_bottom_margin -1:
                    editor_state['scroll_offset'] = max(0, cursor_display_y - scroll_bottom_margin + 2) # Scroll down

                # 3. Perform a SINGLE draw to the buffer with the final state, including adjusted scroll
                self._draw_editor_ui(draw, editor_state, display_lines, cursor_display_y, cursor_display_x)

                # 4. Push to screen with appropriate refresh type.
                if change_type == "view_update":
                    self.display.display_image(is_full_refresh=True)
                elif change_type == "content_update":
                    self.display.display_image(is_full_refresh=False)

            change_type = None # Reset change flag after the draw cycle completes.

            # --- NEW, STABLE EVENT HANDLING LOGIC ---
            # Wait for an event to happen (keyboard or timeout)
            if self.keyboard.has_input(0.05):
                for event in self.keyboard.read_events():
                    if event.type != ecodes.EV_KEY: continue
                    self.last_activity = time.time()

                    if event.code == ecodes.KEY_ESC and event.value == 1:
                        if content_changed_since_last_save:
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.write('\n'.join(editor_state['lines']))
                            self.show_message("Saved!", duration_sec=1, full_refresh=False)
                        if is_journal: self._update_monthly_journal(file_path)
                        return
                    
                    # Handle input and get the type of change it caused
                    input_change_type = self._handle_editor_input(event, editor_state)
                    if input_change_type: # If a keypress caused a change...
                        change_type = input_change_type # Set the change type for the next loop iteration
                        if input_change_type == "content_update":
                            content_changed_since_last_save = True
            else:
                # No keyboard input, check for timed events
                # Check if a status indicator (like "Saved") has timed out.
                if self._update_editor_indicators():
                    change_type = "view_update" # Force a full redraw to remove the indicator.
                
                # Inactivity Save
                if content_changed_since_last_save and (time.time() - self.last_activity > (config.INACTIVITY_SAVE_TIMEOUT / 1000)):
                    with open(file_path, 'w', encoding='utf-8') as f: f.write("\n".join(editor_state['lines']))
                    last_save_time = current_time_ms
                    self.save_indicator_active, self.save_indicator_timer = True, last_save_time
                    content_changed_since_last_save = False
                    change_type = "view_update" # Show "Saved" message.

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

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    # Keep a reference to the original stderr, so we can see startup errors
    original_stderr = sys.stderr
    try:
        logger.info("AdaWriter starting up.")
        keyboard_device = Keyboard()
        app = AdaWriter(keyboard_device)
        app.run()
    except Exception as e:
        # If something goes wrong during init, log it and print to original stderr
        # This is crucial for debugging when the screen isn't working yet.
        logger.error("--- CRITICAL STARTUP FAILURE ---", exc_info=True)
        traceback.print_exc(file=original_stderr)

        # Attempt to show error on screen if display was initialized
        try:
            display_manager = DisplayManager()
            display_manager.show_message(f"FATAL STARTUP ERROR:\n{e}", fatal_error=True)
            time.sleep(20)
        except Exception as display_e:
            logger.error(f"Could not even show error on display: {display_e}")
            traceback.print_exc(file=original_stderr)
    finally:
        logger.info("AdaWriter shutting down.")
        # Ensure pygame quits properly if the loop exits cleanly
        pygame.quit()
        sys.exit(0)