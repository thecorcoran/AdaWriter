# AdaWriter

AdaWriter is a minimalist, distraction-free writing device powered by a Raspberry Pi and an e-paper display. It's designed for writers who want to focus on their craft without the interruptions of a modern computer.

![AdaWriter Screenshot](sim_output.png)

## Features

*   **Distraction-Free E-Paper Display**: Easy on the eyes, with a simple, clean interface.
*   **Full-Fledged Text Editor**:
    *   Full cursor navigation (Up, Down, Left, Right).
    *   Character, word, and line manipulation.
    *   Auto-saving and manual saving on exit.
*   **File Management**:
    *   **Daily Journal**: A one-press option to open a timestamped journal entry for the current day.
    *   **Project Browser**: A scrollable list to manage and edit multiple project files.
*   **Wi-Fi Connectivity**:
    *   Connect to new Wi-Fi networks directly from the device.
    *   Start a web server to download your project files to any computer on the same network.
*   **Portable and Low-Power**: Designed to be used anywhere.

## Hardware Requirements

*   Raspberry Pi (tested with Raspberry Pi Zero and similar models).
*   Waveshare 4.2" E-Paper Display (V2).
*   An external USB keyboard.
*   A power source (e.g., a power bank).
*   An SD card for the OS and project files.

## Setup and Installation

These instructions assume you are starting with a fresh installation of Raspberry Pi OS Lite.

### 1. System Configuration

First, enable the SPI interface, which is required for the e-paper display.

```bash
sudo raspi-config
```
Navigate to `3 Interface Options` -> `I4 SPI` and select `<Yes>` to enable it.

### 2. Install System Dependencies

Install the necessary system libraries and tools.

```bash
sudo apt-get update
sudo apt-get install -y git python3-pip python3-pil python3-numpy
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