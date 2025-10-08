# AdaWriter

AdaWriter is a minimalist, distraction-free writing device powered by a Raspberry Pi and an e-paper display. It's designed for writers who want to focus on their craft without the interruptions of a modern computer.

![AdaWriter Screenshot](sim_output.png)

## Features

*   **Distraction-Free E-Paper Display**: Easy on the eyes, with a simple, clean interface.
*   **Full-Fledged Text Editor**:
    *   WYSIWYG cursor navigation that respects word wrapping.
    *   Character, word, and line manipulation (Enter, Backspace).
    *   Auto-saving and manual saving on exit.
*   **File Management**:
    *   **Daily Journal**: A one-press option to open a timestamped journal entry for the current day.
    *   **Project Browser**: A scrollable list to manage and edit multiple project files.
*   **Wi-Fi Connectivity**:
    *   Connect to new Wi-Fi networks directly from the device.
    *   **Web Interface**: Access a full-featured web server from another computer on the same network to:
        *   Download project files as `.txt` or `.docx`.
        *   Upload `.txt` and `.docx` files from your computer to the device.
        *   Edit files directly in the browser.
        *   Archive, delete, and restore files from a trash folder.
*   **Portable and Low-Power**: Designed to be used anywhere.

## Hardware Requirements

*   Raspberry Pi (tested with Raspberry Pi Zero and similar models).
*   Waveshare 4.2" E-Paper Display (V2).
*   An external USB keyboard.
*   A power source (e.g., a power bank).
*   An SD card for the OS and project files.

## Keyboard Layout

The keyboard layout is defined in `us_qwerty.json`. This file maps the `evdev` key codes from a standard US QWERTY keyboard to their corresponding characters, including shifted values.

If you are using a different keyboard layout, you can create a new JSON file and modify the `Keyboard` class in `keyboard.py` to load it.


## Setup and Installation

The recommended way to set up a new AdaWriter device is to use the Raspberry Pi Imager to create a pre-configured SD card that runs the provisioning script on its first boot.

### Fully Automated Setup (Recommended)

This method flashes the OS and runs the setup script automatically.

1.  **Download Raspberry Pi Imager**: Get the official imager from the [Raspberry Pi website](https://www.raspberrypi.com/software/).
2.  **Choose OS**: Select "Raspberry Pi OS (other)" -> "Raspberry Pi OS Lite (Legacy, 64-bit)" based on Debian Bullseye.
3.  **Open Advanced Settings**: Before writing, click the gear icon ⚙️ to open the advanced settings.
4.  **Configure Settings**:
    *   **Set hostname**: e.g., `adawriter`.
    *   **Enable SSH**: Choose "Use password authentication".
    *   **Set username and password**: Set the username to `admin` and choose a secure password. This is required for the setup and deployment scripts to work correctly.
    *   **Configure wireless LAN**: Enter the SSID and password for your Wi-Fi network. This is crucial for the script to download dependencies.
    *   **Set locale settings**: Set your timezone and keyboard layout.
5.  **Configure First-Boot Service**:
    *   Click "SAVE", then "WRITE" to flash the OS to your SD card.
6.  **Add the First-Boot Script**:
    *   After writing is complete, **do not eject the SD card**. Your computer should automatically mount a partition from the card named `boot` or `bootfs`.
    *   Open this `boot` partition.
    *   Create a new file inside it named `firstrun.sh`.
    *   Copy the entire contents of the `first-boot.sh` script from this repository and paste it into the new `firstrun.sh` file. Save and close the file.
7.  **Boot the Device**: Safely eject the SD card from your computer, insert it into your Raspberry Pi, and power it on. The device will boot, connect to Wi-Fi, and automatically run the setup script. This process can take 5-10 minutes. The device will be ready to use after this.

### Manual Setup

If you already have a running Raspberry Pi, you can run the provisioning script manually.

1.  **Boot and Connect**: Ensure your Raspberry Pi is running and connected to the internet.
2.  **Clone Repository**:
    ```bash
    git clone https://github.com/thecorcoran/AdaWriter.git
    cd AdaWriter
    ```
3.  **Run Provisioning Script**: Make the script executable and run it with `sudo`.
    ```bash
    chmod +x provision.sh
    sudo ./provision.sh
    ```
The script will set up all dependencies and enable the application to start automatically on boot.

## Running the Application

If you used the provisioning script, the AdaWriter application will start automatically when the device boots.

### Manual Control (for Development)

You can manually control the `adawriter` service using `systemctl`. This is useful for development or debugging.

```bash
# Stop the service
sudo systemctl stop adawriter.service

# Start the service
sudo systemctl start adawriter.service

# View the application's log output
sudo journalctl -u adawriter.service -f

# Disable auto-start on boot
sudo systemctl disable adawriter.service

# Re-enable auto-start on boot
sudo systemctl enable adawriter.service
```