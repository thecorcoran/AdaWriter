# AdaWriter

AdaWriter is a minimalist, distraction-free writing device powered by a Raspberry Pi and an e-paper display. It is designed for writers who want to focus on their craft without the interruptions of a modern computer. Its philosophy is rooted in simplicity, providing just the tools you need to write and nothing more.

![AdaWriter Screenshot](sim_output.png)

## Core Features

### Distraction-Free Writing
*   **E-Paper Display**: A beautiful, paper-like 4.2" display that is easy on the eyes and free of distracting backlight.
*   **Minimalist Editor**: The writing screen shows only your text and a subtle cursor. Status information like word count or the time appears only when requested and fades away automatically.
*   **Focused Workflow**: The device boots directly into a simple menu, guiding you straight into your writing. There is no web browser, no notifications, and no other apps to pull you out of your flow.

### Simple & Powerful Text Editing
*   **Robust Text Editor**: A full-featured plain text editor that supports seamless cursor navigation across word-wrapped lines.
*   **Automatic Saving**: Your work is saved automatically after a few seconds of inactivity and again when you exit the editor, so you never have to worry about losing your progress.
*   **Daily Journal**: A dedicated "Daily Journal" mode that automatically opens or creates an entry for the current day, timestamped and ready for your thoughts.
*   **Project Management**: Keep your writing organized with a simple, scrollable list of project files. You can create, rename, and delete projects directly on the device.

### Easy File Management via Web Interface
*   **Built-in Web Server**: Activate the Wi-Fi and start a web server directly from the device menu.
*   **Access From Any Device**: Connect to the AdaWriter from any computer or phone on the same Wi-Fi network to easily manage your files.
*   **Upload and Download**:
    *   Download your project files as `.txt` or convert them to `.docx` on the fly.
    *   Upload `.txt` files directly or upload `.docx` files, which are automatically converted to plain text for editing.
*   **Full File Control**: The web interface allows you to edit files, archive old projects, and move files to or restore them from a trash folder.

## Hardware Requirements

*   **Raspberry Pi**: Tested with Raspberry Pi Zero W/WH and similar models.
*   **E-Paper Display**: Waveshare 4.2" E-Paper Display (V2).
*   **Real-Time Clock**: DS3231 RTC Module (for accurate offline timekeeping).
*   **Input**: A standard external USB keyboard.
*   **Power**: A USB power source, such as a power bank or wall adapter.
*   **Storage**: A microSD card (8GB or larger recommended).

## Software & Dependencies

The application is built with Python and relies on the following key libraries:

*   `pygame`: For the main application loop and event handling.
*   `evdev`: For low-level keyboard input.
*   `Pillow`: For drawing text and shapes on the display.
*   `Flask`: To power the web interface.
*   `python-docx`: For handling `.docx` file conversions.
*   `netifaces`: To detect the device's IP address.

The hardware drivers (`waveshare-epd`, `spidev`, `RPi.GPIO`) are also required and are installed by the provisioning script.

## Setup and Installation

> [!WARNING]
> The fully automated setup method (`first-boot.sh`) is currently experimental and may have bugs. The manual setup is the recommended and most reliable method.

### Manual Setup (Recommended)

1.  **Flash OS**: Flash a new microSD card with **Raspberry Pi OS Lite (64-bit)** using the official Raspberry Pi Imager. Use the advanced settings (⚙️) to pre-configure your username, password, and Wi-Fi credentials.
2.  **Boot and Connect**: Insert the card into your Pi, power it on, and connect to it via SSH.
3.  **Clone Repository**:
    ```bash
    git clone https://github.com/thecorcoran/AdaWriter.git
    cd AdaWriter
    ```
4.  **Run Provisioning Script**: Make the script executable and run it. This will install all dependencies, configure the system, and set up the application to run automatically on boot.
    ```bash
    chmod +x provision.sh
    sudo ./provision.sh
    ```
After the script completes and the device reboots, the AdaWriter application will start automatically.

## How to Use

### On the Device
The device is controlled with a USB keyboard.

*   **Main Menu**:
    *   `1`: Open today's Daily Journal entry.
    *   `2`: View and manage your list of projects.
    *   `W`: Open the Wi-Fi & Network menu.
    *   `Q`: Shut down the device.
*   **Editor**:
    *   `Arrow Keys`: Move the cursor.
    *   `Enter`: Create a new line.
    *   `Backspace`: Delete characters.
    *   `F1`: Briefly display the current word count.
    *   `F2`: Briefly display the current time.
    *   `ESC`: Save your work and return to the previous menu.

### Using the Web Interface
1.  On the AdaWriter, navigate to **W for Wi-Fi** -> **1. Start Web Server**.
2.  The device will display its IP address (e.g., `http://192.168.1.100:8000`).
3.  Open that address in a web browser on another device on the same network.
4.  From here, you can download, upload, edit, and manage all your project files.

## Configuration & Development

### Application Configuration
You can modify the application's behavior by editing `config.py`:
*   `INACTIVITY_TIMEOUT_SECONDS`: Set how long the device waits before automatically shutting down (default: 10 minutes).
*   `AUTO_SAVE_INTERVAL`: Set the timing for automatic saves while writing.
*   `KEYBOARD_LAYOUT_FILE`: Change the keyboard mapping file (default: `us_qwerty.json`).

### Development
The `deploy.sh` script provides a convenient way to sync your local code changes to the AdaWriter device and restart the application.

1.  Update the IP address and username in `deploy.sh` to match your device.
2.  For passwordless deploys, copy your SSH key to the device: `ssh-copy-id your_user@your_pi_ip`.
3.  Run the script from your development machine:
    ```bash
    ./deploy.sh
    ```
This will rsync the files, reinstall dependencies, and restart the `adawriter` service. You can monitor the application logs with `sudo journalctl -u adawriter.service -f`.
