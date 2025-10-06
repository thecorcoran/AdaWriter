#!/bin/bash

# --- AdaWriter Provisioning Script ---
# This script automates the complete setup of the AdaWriter software on a fresh
# Raspberry Pi OS Lite installation. It is designed to be used with the
# Raspberry Pi Imager's "first-boot" or cloud-init functionality.

set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
# The user that will own the AdaWriter directory and run the application.
# It automatically detects the user who ran `sudo`. If not found, defaults to 'pi'.
TARGET_USER="${SUDO_USER:-admin}"

# Define home and project directories based on the detected user.
export TARGET_HOME="/home/${TARGET_USER}" # e.g., /home/admin
export PROJECT_DIR="${TARGET_HOME}/AdaWriter"

echo "--- Starting AdaWriter Provisioning for user '${TARGET_USER}' ---"

# Wait for network connectivity.
echo "--> Waiting for network connection..."
while ! ping -c 1 -W 1 google.com &> /dev/null; do
    echo "    Still waiting for network..."
    sleep 2
done
echo "--> Network is up."

# Step 1: Update system and install dependencies
echo "--> Updating package lists and installing system dependencies..."
apt-get update
# We install build tools and libraries, but NOT python3-pil.
# Pillow will be installed correctly via pip in the virtual environment.
apt-get install -y git python3-pip python3-numpy libxml2-dev libxslt1-dev python3-venv libopenjp2-7 build-essential

# Step 2: Enable SPI interface
echo "--> Enabling SPI interface via raspi-config non-interactively..."
raspi-config nonint do_spi 0

# Step 3: Clone the AdaWriter repository from GitHub
echo "--> Cloning AdaWriter repository into ${PROJECT_DIR}..."
# Remove the directory if it exists to ensure a fresh clone
if [ -d "${PROJECT_DIR}" ]; then
    rm -rf "${PROJECT_DIR}"
fi
git clone https://github.com/thecorcoran/AdaWriter.git "${PROJECT_DIR}"
chown -R ${TARGET_USER}:${TARGET_USER} "${PROJECT_DIR}"
echo "--> Repository cloned successfully."

# Step 4: Set up Python virtual environment
echo "--> Setting up Python virtual environment in ${PROJECT_DIR}..."
sudo -u ${TARGET_USER} python3 -m venv "${PROJECT_DIR}/venv"

# Step 5: Install all Python dependencies into the virtual environment
echo "--> Installing Python dependencies into the virtual environment..."
sudo -u ${TARGET_USER} bash -c "
    set -e
    source \"${PROJECT_DIR}/venv/bin/activate\"
    echo '--> Installing dependencies from requirements.txt...'
    pip install -r \"${PROJECT_DIR}/requirements.txt\" --no-input

    echo '--> Cloning Waveshare e-Paper driver (this may take a moment)...'
    # We clone manually to show git's progress, as the repo is large and pip hides the output.
    # --depth 1 creates a shallow clone, which is much faster.
    git clone --depth 1 https://github.com/waveshare/e-Paper.git \"${TARGET_HOME}/e-Paper\"

    echo '--> Installing the cloned e-Paper driver...'
    pip install \"${TARGET_HOME}/e-Paper/RaspberryPi_JetsonNano/python\" --no-input

    # Clean up the cloned repository
    rm -rf \"${TARGET_HOME}/e-Paper\"
    echo '--> All Python dependencies installed.'
"

# Step 6: Install and enable the systemd service for auto-start
echo "--> Installing and enabling systemd service for auto-start on boot..."
SERVICE_FILE_PATH="/etc/systemd/system/adawriter.service"
SOURCE_SERVICE_FILE="${PROJECT_DIR}/adawriter.service"

if [ ! -f "${SOURCE_SERVICE_FILE}" ]; then
    echo "    ERROR: Service file not found at ${SOURCE_SERVICE_FILE}. Aborting."
    exit 1
fi
cp "${SOURCE_SERVICE_FILE}" "${SERVICE_FILE_PATH}"
sed -i "s|/home/pi|${TARGET_HOME}|g" "${SERVICE_FILE_PATH}" # Make user home dir configurable
sed -i "s/User=pi/User=${TARGET_USER}/" "${SERVICE_FILE_PATH}" # Set the correct user to run the service
systemctl enable adawriter.service

# Step 7: Add user to required hardware groups
echo "--> Adding user '${TARGET_USER}' to 'spi', 'gpio', and 'input' groups for hardware access..."
adduser ${TARGET_USER} spi
adduser ${TARGET_USER} gpio
adduser ${TARGET_USER} input

echo "--- ✅ AdaWriter Provisioning Complete! ---"
echo "The AdaWriter service has been enabled and will start automatically on boot."
echo "Rebooting now to apply all changes..."
reboot