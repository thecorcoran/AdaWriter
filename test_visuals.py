# test_visuals.py (Version 1.1 - Bug Fixes)
# Visual Regression Testing framework for AdaWriter.
#
# Usage:
# 1. Generate the initial "golden master" images:
#    python3 test_visuals.py --update
#
# 2. Run the tests to compare current output against masters:
#    python3 test_visuals.py
#
import os
import sys
import argparse
from PIL import Image, ImageChops
import shutil

# --- Mock objects to simulate the full app environment ---
class MockKeyboard:
    def __init__(self):
        self.shift_pressed = False

class MockAdaWriter:
    def __init__(self, display):
        self.display = display
        self.save_indicator_active = False
        self.word_count_active = False
        self.current_word_count_text = ""
    def _get_active_indicator_text(self):
        if self.save_indicator_active: return "Saved"
        if self.word_count_active: return self.current_word_count_text
        return ""

# --- Test Runner Setup ---
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from display_manager import DisplayManager
from ada_writer import TextEditor
import config

GOLDEN_MASTERS_DIR = os.path.join(project_root, "tests", "golden_masters")
TEST_OUTPUT_DIR = os.path.join(project_root, "tests", "output")
os.makedirs(GOLDEN_MASTERS_DIR, exist_ok=True)
os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)


def run_test_scenario(test_name, lines, cursor_x, cursor_y, title="Test Case"):
    print(f"  Running scenario: {test_name}...")
    
    display = DisplayManager()
    keyboard = MockKeyboard()
    app = MockAdaWriter(display)
    editor = TextEditor(display, keyboard, app)

    display_lines, source_line_map = editor._get_wrapped_lines(lines)
    cursor_display_y, _ = editor._calculate_cursor_on_display(
        display_lines, source_line_map, cursor_y, cursor_x
    )
    
    line_height = (display.fonts['editor'].getbbox("Tg")[3] - display.fonts['editor'].getbbox("Tg")[1]) + 4
    max_lines_on_screen = (display.height - config.EDITOR_HEADER_HEIGHT - config.EDITOR_FOOTER_HEIGHT) // line_height
    scroll_offset = max(0, cursor_display_y - (max_lines_on_screen - 2))

    editor_state = {
        'lines': list(lines), 'cursor_x': cursor_x, 'cursor_y': cursor_y,
        'scroll_offset': scroll_offset, 'title': title, 'cursor_visible': True,
        'is_journal': False, 'layout_changed': False, 'content_changed': False
    }
    
    display.draw.rectangle((0, 0, display.width, display.height), fill=255)
    
    cursor_display_pos = editor._calculate_cursor_on_display(
        display_lines, source_line_map, editor_state['cursor_y'], editor_state['cursor_x'] # Corrected
    )
    
    editor.renderer.draw_ui(display.draw, editor_state, display_lines, cursor_display_pos, True)

    output_path = os.path.join(TEST_OUTPUT_DIR, f"{test_name}.png")
    # This uses the overriden save method in DisplayManager for simulation mode
    display.display_image(image=display.image) 
    shutil.copy("sim_output.png", output_path)
    
    return output_path


def define_scenarios():
    long_line = "This is a very long line of text that is specifically designed to test the word wrapping functionality of the text editor."
    multi_line_text = ["First line.", "Second line has some length to it.", "", "Fourth line, after a blank one."]

    return {
        "01_empty_document": {"lines": [""], "cursor_x": 0, "cursor_y": 0},
        "02_simple_text": {"lines": ["Hello, world."], "cursor_x": 7, "cursor_y": 0},
        "03_word_wrap": {"lines": [long_line], "cursor_x": 25, "cursor_y": 0},
        "04_multi_line": {"lines": multi_line_text, "cursor_x": 0, "cursor_y": 3},
        "05_cursor_at_end_of_line": {"lines": ["A line of text."], "cursor_x": 15, "cursor_y": 0}
    }


def main():
    parser = argparse.ArgumentParser(description="Visual Regression Tests for AdaWriter")
    parser.add_argument('--update', action='store_true', help="Update the golden master images.")
    args = parser.parse_args()

    scenarios = define_scenarios()
    
    if args.update:
        print("--- Updating Golden Master Images ---")
        if os.path.exists(GOLDEN_MASTERS_DIR): shutil.rmtree(GOLDEN_MASTERS_DIR)
        os.makedirs(GOLDEN_MASTERS_DIR)
        
        for name, params in scenarios.items():
            output_path = run_test_scenario(name, **params)
            shutil.copy(output_path, os.path.join(GOLDEN_MASTERS_DIR, f"{name}.png"))
        print("\nGolden masters updated successfully.")
        return

    print("--- Running Visual Regression Tests ---")
    failures = 0
    for name, params in scenarios.items():
        output_path = run_test_scenario(name, **params)
        master_path = os.path.join(GOLDEN_MASTERS_DIR, f"{name}.png")

        if not os.path.exists(master_path):
            print(f"❌ FAIL: Golden master for '{name}' not found. Run with --update first.")
            failures += 1
            continue

        master_img = Image.open(master_path).convert('RGB')
        output_img = Image.open(output_path).convert('RGB')
        diff = ImageChops.difference(master_img, output_img)
        
        if diff.getbbox() is None:
            print(f"✅ PASS: {name}")
        else:
            print(f"❌ FAIL: Visual difference detected in '{name}'")
            diff_path = os.path.join(TEST_OUTPUT_DIR, f"{name}_diff.png")
            diff.save(diff_path)
            print(f"   - Difference image saved to: {diff_path}")
            failures += 1
            
    print("-" * 35)
    if failures == 0:
        print("🎉 All visual tests passed!")
        sys.exit(0)
    else:
        print(f"🔥 {failures} visual test(s) failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()