AdaWriter v1.4.3
A distraction-free, e-ink writing device powered by a Raspberry Pi. AdaWriter is designed for writers who want a simple, focused tool that feels like a classic typewriter but with the conveniences of modern technology. It uses a low-power e-ink screen and a physical keyboard to create a dedicated writing environment.


Table of Contents
 * Overview
 * Features
 * Changelog
 * Hardware Requirements
 * Software & Setup
 * Running the Application
 * How to Use
Overview
AdaWriter turns a Raspberry Pi and a Waveshare e-ink display into a portable, dedicated writing machine. The project handles text editing, file management, and even allows you to transfer your work over Wi-Fi. It's built to be robust, with features like auto-saving, an inactivity shutdown timer to preserve power, and a user-friendly interface designed for the constraints of an e-paper display.
Features
 * Distraction-Free E-Ink Interface: A simple, clean UI optimized for e-paper.
 * Physical Keyboard Input: Uses evdev for direct, low-level keyboard handling.
 * Project Management: Create, rename, archive, and delete project files.
 * Automatic Daily Journal: Creates a new journal entry for each day with automatic timestamps for new sessions.
 * Monthly Log Archiving: Journal entries are automatically consolidated into monthly log files.
 * Wi-Fi File Server: Start a web server to view and download your documents from any device on the same network.
 * Multiple Download Formats: Download files as plain text (.txt) or Rich Text Format (.doc).
 * Editor Tools: On-demand word count and time display.
 * Power Management: An inactivity timer automatically saves work and safely shuts down the device to conserve power.
 * Wi-Fi Configuration: Scan for and connect to new Wi-Fi networks directly from the device.
 * Graceful Shutdown: Displays a custom screen with a quote from Tolstoy before powering off.
Changelog
v1.4.3
 * Changed web server font to a serif font for a more classic look.
v1.4.2
 * Restored the "View" button on the HTTP server page.
 * Changed directory names on the server page to be more user-friendly.
 * Changed the "Parent Directory" link on the server to "Home".
v1.4.1
 * Added option to download files as .doc (RTF format) from the HTTP server.
v1.4.0
 * Journal entries now automatically get a timestamp when a new session begins.
Hardware Requirements
 * Raspberry Pi: Any model with GPIO pins (tested on Pi Zero, but others should work).
 * E-Ink Display: Waveshare 4.2inch E-Paper Module V2.
 * Keyboard: A standard USB keyboard.
 * Power Supply & SD Card: A suitable power supply for your Pi and a microSD card for the OS.
Software & Setup
1. Raspberry Pi Configuration
Before running the script, you need to configure your Raspberry Pi:
 * Install Raspberry Pi OS.
 * Enable the SPI interface:
   * Run sudo raspi-config.
   * Navigate to Interface Options -> SPI.
   * Select <Yes> to enable the SPI interface.
 * Install nmcli: This tool is used for Wi-Fi management and is typically included with Raspberry Pi OS Desktop, but may need to be installed on Lite versions.
   sudo apt-get update
sudo apt-get install network-manager

2. Python Dependencies
Install the required Python libraries using pip.
pip install pygame netifaces evdev Pillow waveshare-epd

3. File Structure
The script expects a specific directory structure. From the same directory where ada_writer_v1.4.3.py is located, create the following folders:
.
├── ada_writer_v1.4.3.py
├── projects/
└── assets/

 * The projects/ directory is where all your text files, journals, and archives will be stored.
 * The assets/ directory can be used to store images, such as the tolstoy.png used for the shutdown screen.
Running the Application
Because the script requires low-level access to the keyboard (/dev/input/event*) and the ability to shut down the system, it must be run with sudo.
sudo python3 ada_writer_v1.4.3.py

Automatic Startup (Optional)
To make the device feel more like an appliance, you can have the script run automatically on boot. Edit the rc.local file:
sudo nano /etc/rc.local

Add the following line before exit 0, making sure to use the full path to your script:
sudo python3 /home/pi/adawriter/ada_writer_v1.4.3.py &

How to Use
Main Menu
 * 1. Daily Journal: Open or create today's journal entry.
 * 2. Projects: View, open, rename, archive, or delete your project files.
 * 3. Wi-Fi Settings: Scan for and connect to Wi-Fi networks.
 * W. Wi-Fi Transfer: Start the web server for file transfers.
 * Q. Quit: Display the shutdown screen and safely power off the device.
Text Editor
 * F1: Display the current word count.
 * PageUp / PageDown: Scroll through the document.
 * ESC: Save the current file and return to the previous menu.
Wi-Fi File Transfer
 * From the main menu, press W to start the server.
 * The e-ink screen will display a URL (e.g., http://192.168.1.10:8000).
 * Type this URL into the web browser of a computer or phone connected to the same Wi-Fi network.
 * You can browse your projects and download them as .txt or .doc files.
 * Press ESC on the AdaWriter to stop the server.
