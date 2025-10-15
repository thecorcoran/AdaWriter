# display_manager.py (Version 2.1 - Portable Fonts)
# Manages all e-ink display rendering for the AdaWriter project.

import os
import time
import logging
from PIL import Image, ImageDraw, ImageFont

# This try/except block is important for allowing the code to run
# on a computer for testing, even without the hardware libraries.
try:
    import waveshare_epd
    logging.info(f"Successfully imported waveshare_epd package. Contents: {dir(waveshare_epd)}")
    from waveshare_epd import epd4in2_V2
    logging.info("Successfully imported epd4in2_V2 submodule.")
except ImportError as e:
    logging.error(f"Failed to import a waveshare submodule: {e}")
    epd4in2_V2 = None

import config

class DisplayManager:
    def __init__(self, eink_driver_available=False):
        self.is_simulation = not eink_driver_available
        self.epd = None

        if self.is_simulation:
            logging.warning("E-ink library not found or hardware init failed. Running in simulation mode.")
            self.width = 400
            self.height = 300
        else:
            try:
                self.epd = epd4in2_V2.EPD()
                self.width = self.epd.width
                self.height = self.epd.height
            except Exception as e:
                logging.error(f"E-ink hardware not found: {e}. Running in simulation mode.")
                self.is_simulation = True
                self.width = 400
                self.height = 300

        # Initialize persistent image buffer and draw object
        self.image = Image.new('1', (self.width, self.height), 255) # 255 for white
        self.draw = ImageDraw.Draw(self.image)
        self._is_sleeping = True
        # self.start() # We will now call this manually after drawing the first screen

        # Pre-load all fonts using portable paths
        assets_path = os.path.join(config.BASE_DIR, config.ASSETS_FOLDER)
        font_path_serif = os.path.join(assets_path, 'DejaVuSerif.ttf')
        font_path_sans = os.path.join(assets_path, 'DejaVuSans.ttf')
        font_path_custom = os.path.join(assets_path, "Cyrillic Old.otf")

        self.fonts = {
            'title': self._load_font(font_path_custom, 70, fallback=font_path_serif),
            'heading': self._load_font(font_path_serif, 36),
            'menu': self._load_font(font_path_serif, 26),
            'list': self._load_font(font_path_serif, 24),
            'editor': self._load_font(font_path_serif, 20),
            'body': self._load_font(font_path_serif, 16),
            'status': self._load_font(font_path_sans, 14),
            'footer': self._load_font(font_path_sans, 14)
        }
        self.shutdown_image = self._preload_shutdown_image()

    def start(self):
        """Initializes the display. This should be called once when the app starts."""
        if not self.is_simulation:
            logging.info("Initializing and clearing display...")
            self.epd.init() # Use full init for the first draw
            self.epd.display(self.epd.getbuffer(self.image))
            self._is_sleeping = False
            logging.info("Display initialized.")
            self._current_mode = 'fast'

    def _load_font(self, path, size, fallback=None):
        try:
            return ImageFont.truetype(path, size)
        except IOError:
            logging.warning(f"Font not found at '{path}'. Trying fallback.")
            if fallback:
                try:
                    return ImageFont.truetype(fallback, size)
                except IOError:
                    logging.error(f"Fallback font not found at '{fallback}'. Loading default.")
            return ImageFont.load_default()

    def _preload_shutdown_image(self):
        try:
            image_path = os.path.join(config.BASE_DIR, config.ASSETS_FOLDER, "tolstoy.png")
            img = Image.open(image_path).convert('L') # Convert to grayscale
            
            # Create a new blank 1-bit image and paste the dithered version
            bw_image = img.convert('1', dither=Image.FLOYDSTEINBERG)
            
            bw_image.thumbnail((self.width - 40, 240), Image.LANCZOS)
            return bw_image
        except Exception as e:
            logging.error(f"Could not load or process shutdown image: {e}")
            return None

    def display_image(self, is_full_refresh=True, image=None):
        """
        Displays an image on the e-ink screen.
        - For full refresh, it wakes the display, clears it, and shows the image.
        - For partial refresh, it's recommended to use display_partial for efficiency.
        """
        img = image if image is not None else self.image
        if self.is_simulation:
            # The test script relies on this behavior.
            img.save("sim_output.png")
            return

        if self._is_sleeping:
            # If waking from sleep, always do a full init first.
            logging.debug("Waking display from sleep with full init.")
            self.epd.init() # Full init
            self._is_sleeping = False
            self._current_mode = 'full' # After full init, it's in full refresh mode

        if is_full_refresh:
            if self._current_mode != 'full':
                logging.debug("Switching to full refresh mode.")
                self.epd.init() # Switch to full refresh mode
                self._current_mode = 'full'
            logging.debug("Performing full display refresh (clear and display).")
            self.epd.Clear() # Clear the physical display buffer
            self.epd.display(self.epd.getbuffer(img))
        else:
            if self._current_mode != 'fast':
                logging.debug("Switching to fast refresh mode.")
                self.epd.init_fast(self.epd.Seconds_1_5S) # Switch to fast refresh mode
                self._current_mode = 'fast'
            logging.debug("Performing full-frame partial refresh.")
            self.epd.display_Partial(self.epd.getbuffer(img))


    def display_partial(self, image, box):
        """
        Updates a specific rectangular area of the display.
        Box is a tuple (x_start, y_start, x_end, y_end).
        """
        if self.is_simulation or self._is_sleeping:
            return

        x_start, y_start, x_end, y_end = box
        x_start = x_start - (x_start % 8)
        x_end = x_end + (8 - x_end % 8) if x_end % 8 != 0 else x_end
        
        if x_end > self.width: x_end = self.width
        if y_end > self.height: y_end = self.height

        self.epd.send_command(0x3C)
        self.epd.send_data(0x80)
        self.epd.send_command(0x44)
        self.epd.send_data(x_start // 8)
        self.epd.send_data(x_end // 8)
        self.epd.send_command(0x45)
        self.epd.send_data(y_start & 0xFF)
        self.epd.send_data((y_start >> 8) & 0xFF)
        self.epd.send_data(y_end & 0xFF)
        self.epd.send_data((y_end >> 8) & 0xFF)
        self.epd.send_command(0x4E)
        self.epd.send_data(x_start // 8)
        self.epd.send_command(0x4F)
        self.epd.send_data(y_start & 0xFF)
        self.epd.send_data((y_start >> 8) & 0xFF)

        partial_image = image.crop((x_start, y_start, x_end, y_end))
        partial_buffer = self.epd.getbuffer(partial_image)
        
        self.epd.send_command(0x24)
        self.epd.send_data2(partial_buffer)
        self.epd.TurnOnDisplay_Partial()

    def update_text_area(self, image, dirty_rects):
        """
        Updates multiple rectangular areas of the display.
        """
        if self.is_simulation or self._is_sleeping:
            return
        for box in dirty_rects:
            self.display_partial(image, box)

    def sleep(self):
        """Puts the display to sleep."""
        if not self.is_simulation and not self._is_sleeping:
            logging.info("Putting display to sleep.")
            self.epd.sleep()
            self._is_sleeping = True

    def _draw_text_centered(self, draw, y, text, font):
        """Helper to draw centered text. Returns the new y-position."""
        lines = text.split('\n')
        total_height = sum(draw.textbbox((0,0), line, font=font)[3] for line in lines)
        current_y = y - total_height // 2

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) / 2
            draw.text((x, current_y), line, font=font, fill=0)
            current_y += bbox[3] + 4
        return current_y

    def show_message(self, message, fatal_error=False):
        """Displays a message on the screen for a certain duration."""
        self.draw.rectangle((0, 0, self.width, self.height), fill=255)
        self._draw_text_centered(self.draw, self.height // 2, message, self.fonts['menu'])
        self.display_image(is_full_refresh=True)
        
        if fatal_error:
            time.sleep(10)
        else:
            time.sleep(3)

    def _draw_wrapped_text(self, y, text, font, margin, centered=False):
        """Helper to draw text that wraps within the screen margins."""
        words = text.split(' ')
        lines = []
        current_line = ""
        
        max_width = self.width - (2 * margin)

        for word in words:
            if self.draw.textbbox((0, 0), current_line + word, font=font)[2] <= max_width:
                current_line += word + " "
            else:
                lines.append(current_line.strip())
                current_line = word + " "
        lines.append(current_line.strip())

        for line in lines:
            x = margin
            if centered:
                bbox = self.draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                x = (self.width - text_width) / 2
            bbox = self.draw.textbbox((0, y), line, font=font)
            self.draw.text((x, y), line, font=font, fill=0)
            y += (bbox[3] - bbox[1]) + 4
        return y

    def draw_confirmation_dialog(self, prompt, option1="Yes", option2="No"):
        """Draws a centered confirmation box. Returns y-pos for footer."""
        box_width, box_height = 300, 150
        box_x, box_y = (self.width - box_width) // 2, (self.height - box_height) // 2
        
        self.draw.rectangle((box_x + 5, box_y + 5, box_x + box_width + 5, box_y + box_height + 5), fill=0)
        self.draw.rectangle((box_x, box_y, box_x + box_width, box_y + box_height), fill=255, outline=0, width=2)

        prompt_y = self._draw_wrapped_text(box_y + 20, prompt, self.fonts['menu'], box_x + 15)

        self.draw.text((box_x + 40, prompt_y + 20), f"1. {option1}", font=self.fonts['list'], fill=0)
        self.draw.text((box_x + 180, prompt_y + 20), f"2. {option2}", font=self.fonts['list'], fill=0)
        return box_y + box_height + 20