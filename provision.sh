#!/bin/bash

# --- AdaWriter Provisioning Script ---
# This script automates the complete setup of the AdaWriter software on a fresh
# Raspberry Pi OS Lite installation. It is designed to be used with the
# Raspberry Pi Imager's "first-boot" or cloud-init functionality.

set -e # Exit immediately if a command exits with a non-zero status.

# Redirect all output (stdout and stderr) to a log file
LOG_FILE="/var/log/adawriter-provisioning.log"
exec &> >(tee -a "${LOG_FILE}")

# --- Configuration ---
# The primary non-root user for the device. This user will own the project files.
TARGET_USER="admin"

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
apt-get install -y git python3-pip python3-numpy libxml2-dev libxslt1-dev python3-venv libopenjp2-7 build-essential python3-gpiozero python3-rpi.gpio

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

# Step 4: Install Python dependencies globally
echo "--> Installing Python dependencies globally..."
pip3 install -r "${PROJECT_DIR}/requirements.txt" --no-input

echo '--> Cloning and installing Waveshare e-Paper driver...'
# We clone manually to show git's progress, as the repo is large and pip hides the output.
# --depth 1 creates a shallow clone, which is much faster.
git clone --depth 1 https://github.com/waveshare/e-Paper.git "${TARGET_HOME}/e-Paper"

echo '--> Installing the cloned e-Paper driver...'
pip3 install "${TARGET_HOME}/e-Paper/RaspberryPi_JetsonNano/python" --no-input

# Clean up the cloned repository
rm -rf "${TARGET_HOME}/e-Paper"
echo '--> All Python dependencies installed.'

# Step 6: Install and enable the systemd service for auto-start
echo "--> Installing and enabling systemd service for auto-start on boot..."
SERVICE_FILE_PATH="/etc/systemd/system/adawriter.service"
SOURCE_SERVICE_FILE="${PROJECT_DIR}/adawriter.service"

if [ ! -f "${SOURCE_SERVICE_FILE}" ]; then
    echo "    ERROR: Service file not found at ${SOURCE_SERVICE_FILE}. Aborting."
    exit 1
fi
cp "${SOURCE_SERVICE_FILE}" "${SERVICE_FILE_PATH}"
sed -i "s|/home/pi|${TARGET_HOME}|g" "${SERVICE_FILE_PATH}" # Set the correct home directory
sed -i "s/User=pi/User=root/" "${SERVICE_FILE_PATH}" # Set the user to root for hardware access
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