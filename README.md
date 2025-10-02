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

There are two primary methods for setting up an AdaWriter device: the automated method (recommended) and the manual method.

### Automated Setup (Recommended)

This method uses a provisioning script to automate all the necessary installation steps. It is the fastest and most reliable way to set up a new device.

1.  **Flash OS**: Flash a new SD card with the latest Raspberry Pi OS Lite.
2.  **Boot and Connect**: Boot the Raspberry Pi and ensure it is connected to the internet.
3.  **Clone Repository**:
    ```bash
    git clone https://github.com/thecorcoran/AdaWriter.git
    cd AdaWriter
    ```
4.  **Run Provisioning Script**: Make the script executable and run it.
    ```bash
    chmod +x provision.sh
    ./provision.sh
    ```
The script will handle system updates, dependency installation, SPI activation, and Python environment setup.

### Manual Setup

Follow these steps if you prefer to set up the device manually.

#### 1. System Configuration

Enable the SPI interface, which is required for the e-paper display.

```bash
sudo raspi-config
```
Navigate to `3 Interface Options` -> `I4 SPI` and select `<Yes>` to enable it.

### 2. Install System Dependencies

Install the necessary system libraries and tools.
```bash
sudo apt-get update
sudo apt-get install -y git python3-pip python3-pil python3-numpy libxml2-dev libxslt1-dev python3-venv
```

### 3. Install E-Paper Driver

The Waveshare driver must be installed from its official GitHub repository.

```bash
git clone https://github.com/waveshare/e-Paper.git
cd e-Paper/RaspberryPi_JetsonNano/python/
sudo python3 setup.py install
cd ../../../
```

### 4. Install Python Dependencies

Clone this repository and install the required Python packages using `pip`.

```bash
git clone https://github.com/thecorcoran/AdaWriter.git
cd AdaWriter
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## How to Run

To run the application, you must run it with `sudo` to grant the necessary permissions for accessing the keyboard device directly and controlling the system.

With the virtual environment activated, run the main application script:

```bash
sudo python3 ada_writer.py
```