# editor_renderer.py (Version 1.0)
# Handles all UI drawing for the TextEditor.

import config

class EditorRenderer:
    def __init__(self, display_manager, app_controller):
        """
        Initializes the renderer.
        :param display_manager: The DisplayManager instance for drawing.
        :param app_controller: The main AdaWriter app instance for accessing shared state.
        """
        self.display = display_manager
        self.app = app_controller
        self.last_cursor_rect = None

    def draw_ui(self, draw, editor_state, display_lines, cursor_display_pos, cursor_blink_on):
        """
        Draws the entire editor interface onto the provided draw object.
        """
        cursor_display_y, cursor_display_x = cursor_display_pos
        editor_font = self.display.fonts['editor']
        line_bbox = editor_font.getbbox("Tg")
        line_height = (line_bbox[3] - line_bbox[1]) + 4
        max_lines_on_screen = (self.display.height - config.EDITOR_HEADER_HEIGHT - config.EDITOR_FOOTER_HEIGHT) // line_height
        
        # --- Draw Header ---
        self.display._draw_text_centered(draw, 20, editor_state['title'], self.display.fonts['heading'])
        
        # --- Draw Text Area ---
        y_pos = config.EDITOR_HEADER_HEIGHT
        start_index = editor_state['scroll_offset']
        end_index = editor_state['scroll_offset'] + max_lines_on_screen
        visible_lines = display_lines[start_index:end_index]
        
        for i, line in enumerate(visible_lines):
            current_display_y = i + editor_state['scroll_offset']
            # Only draw text if it's within the visible screen area
            if y_pos < self.display.height - config.EDITOR_FOOTER_HEIGHT:
                draw.text((config.TEXT_MARGIN, y_pos), line, font=editor_font, fill=0)

            # --- Draw Cursor ---
            if editor_state['cursor_visible'] and cursor_blink_on and current_display_y == cursor_display_y:
                line_prefix = line[:cursor_display_x]
                if line_prefix:
                    cursor_x_start = config.TEXT_MARGIN + editor_font.getbbox(line_prefix)[2]
                else:
                    cursor_x_start = config.TEXT_MARGIN
                
                cursor_width = 8
                # Ensure cursor is drawn within the visible area
                if y_pos < self.display.height - config.EDITOR_FOOTER_HEIGHT:
                    cursor_y_pos = y_pos + line_height - 4
                    self.last_cursor_rect = [cursor_x_start, cursor_y_pos, cursor_x_start + cursor_width, cursor_y_pos + 1]
                    draw.rectangle(self.last_cursor_rect, fill=0)
            y_pos += line_height

        # --- Draw Status Indicators ---
        indicator_text = self.app._get_active_indicator_text()
        if indicator_text:
            bbox = self.display.fonts['status'].getbbox(indicator_text)
            text_w = bbox[2] - bbox[0]
            draw.text((self.display.width - config.TEXT_MARGIN - text_w, 10), indicator_text, font=self.display.fonts['status'], fill=0)
        
        # --- Draw Footer ---
        self.display._draw_text_centered(draw, self.display.height - 25, "Arrows=Move, ESC=Save & Exit, F1=Words, F2=Time", self.display.fonts['footer'])