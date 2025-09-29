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
            return

        # If the display is sleeping, it must be re-initialized before an update.
        if self._is_sleeping:
            self.epd.init()
            self._is_sleeping = False

        if is_full_refresh:
            logging.debug("Performing full display refresh.")
            self.epd.display(self.epd.getbuffer(self.image))
        else:
            logging.debug("Performing partial display refresh.")
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
        total_height = sum(draw.textbbox((0,0), line, font=font)[3] for line in lines)
        current_y = y - total_height // 2

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) / 2
            draw.text((x, current_y), line, font=font, fill=0)
            current_y += bbox[3] + 4 # Add line height plus a small gap
        return current_y

    def show_message(self, message, fatal_error=False):
        """Displays a message on the screen for a certain duration."""
        # Use persistent draw object and clear it for the message
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
            # Check if adding the new word exceeds the max width
            if self.draw.textbbox((0, 0), current_line + word, font=font)[2] <= max_width:
                current_line += word + " "
            else:
                lines.append(current_line.strip())
                current_line = word + " "
        lines.append(current_line.strip()) # Add the last line

        for line in lines:
            x = margin
            if centered:
                bbox = self.draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                x = (self.width - text_width) / 2
            bbox = self.draw.textbbox((0, y), line, font=font)
            self.draw.text((x, y), line, font=font, fill=0)
            y += (bbox[3] - bbox[1]) + 4 # Add line height plus a small gap
        return y

    def draw_confirmation_dialog(self, prompt, option1="Yes", option2="No"):
        """Draws a centered confirmation box. Returns y-pos for footer."""
        box_width, box_height = 300, 150
        box_x, box_y = (self.width - box_width) // 2, (self.height - box_height) // 2
        
        # Draw shadow, then box
        self.draw.rectangle((box_x + 5, box_y + 5, box_x + box_width + 5, box_y + box_height + 5), fill=0)
        self.draw.rectangle((box_x, box_y, box_x + box_width, box_y + box_height), fill=255, outline=0, width=2)

        # Draw prompt text
        prompt_y = self._draw_wrapped_text(box_y + 20, prompt, self.fonts['menu'], box_x + 15)

        # Draw options
        self.draw.text((box_x + 40, prompt_y + 20), f"1. {option1}", font=self.fonts['list'], fill=0)
        self.draw.text((box_x + 180, prompt_y + 20), f"2. {option2}", font=self.fonts['list'], fill=0)
        return box_y + box_height + 20