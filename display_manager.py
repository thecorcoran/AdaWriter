# display_manager.py (Version 2.0 - Corrected)
# Manages all e-ink display rendering for the AdaWriter project.

import os
import time
import logging
from PIL import Image, ImageDraw, ImageFont

# This try/except block is important for allowing the code to run
# on a computer for testing, even without the hardware libraries.
try:
    from waveshare_epd import epd4in2_V2
except ImportError:
    epd4in2_V2 = None

import config

class DisplayManager:
    def __init__(self):
        self.simulated_display = False
        if epd4in2_V2 is None:
            self.simulated_display = True
            logging.warning("E-ink library not found. Running in simulation mode.")
            self.width = 400
            self.height = 300
        else:
            try:
                self.epd = epd4in2_V2.EPD()
                self.width = self.epd.width
                self.height = self.epd.height
                logging.info("E-ink display object created.")
            except Exception as e:
                logging.error(f"E-ink hardware not found: {e}. Running in simulation mode.")
                self.simulated_display = True
                self.width = 400
                self.height = 300

        # Initialize persistent image buffer and draw object
        self.image = Image.new('1', (self.width, self.height), 255) # 255 for white
        self.draw = ImageDraw.Draw(self.image)
        self._is_sleeping = True
        self.start()

        # Pre-load all fonts
        font_path_serif = '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf'
        font_path_sans = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
        font_path_custom = os.path.join(config.BASE_DIR, config.ASSETS_FOLDER, "Cyrillic Old.otf")

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
        if not self.simulated_display:
            logging.info("Initializing and clearing display...")
            self.epd.init()
            self.epd.Clear()
            self._is_sleeping = False
            logging.info("Display initialized.")

    def _load_font(self, path, size, fallback=None):
        try:
            return ImageFont.truetype(path, size)
        except IOError:
            if fallback:
                try:
                    return ImageFont.truetype(fallback, size)
                except IOError:
                    pass
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

    def display_image(self, is_full_refresh=True):
        """Displays the given PIL image on the e-ink screen."""
        # This method now operates on the persistent self.image
        # The image buffer is already prepared by the calling function.
        if self.simulated_display:
            filename = "sim_output.png"
            self.image.save(filename)
            logging.debug(f"Saved simulated display to {filename}")
        elif is_full_refresh:
            # A true full refresh involves re-initializing and clearing.
            # This is what causes the "flash".
            logging.debug("Performing full display refresh.")
            self.epd.init()
            self.epd.display(self.epd.getbuffer(self.image))
            self.epd.sleep() # Put to sleep to save power after full refresh
            self._is_sleeping = True
        else:
            # For a partial refresh, we need to wake the display up if it was sleeping.
            # Re-initializing also helps clear ghosting artifacts from previous partial updates.
            logging.debug("Performing partial display refresh.")
            if self._is_sleeping:
                self.epd.init() # Wake the display up
                self._is_sleeping = False
            # For V2 displays, re-initializing before a partial draw is key to clearing ghosting.
            self.epd.display_Partial(self.epd.getbuffer(self.image))

    def sleep(self):
        """Puts the display to sleep."""
        if not self.simulated_display and not self._is_sleeping:
            logging.info("Putting display to sleep.")
            self.epd.sleep()
            self._is_sleeping = True

    # --- Helper drawing methods to be used by ada_writer.py ---

    def _draw_text_centered(self, draw, y, text, font):
        """Helper to draw centered text. Returns the new y-position."""
        # Use textbbox to get the bounding box of the text.
        lines = text.split('\n')
        total_height = sum(self.draw.textbbox((0,0), line, font=font)[3] for line in lines)
        current_y = y - total_height // 2

        for line in lines:
            bbox = self.draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) / 2
            draw.text((x, current_y), line, font=font, fill=0)
            current_y += bbox[3] + 4 # Add line height plus a small gap
        return current_y

    def _draw_wrapped_text(self, y, text, font, margin):
        """Helper to draw text that wraps within the screen margins."""
        words = text.split(' ')
        lines = []
        current_line = ""
        
        max_width = self.width - (2 * margin)

        for word in words:
            # Check if adding the new word exceeds the max width
            if self.draw.textbbox((0, 0), current_line + word, font=font)[2] <= max_width:
                current_line += word + " "
            else:
                lines.append(current_line.strip())
                current_line = word + " "
        lines.append(current_line.strip()) # Add the last line

        for line in lines:
            bbox = self.draw.textbbox((0, y), line, font=font)
            self.draw.text((margin, y), line, font=font, fill=0)
            y += (bbox[3] - bbox[1]) + 4 # Add line height plus a small gap
        return y