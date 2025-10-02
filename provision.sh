#!/bin/bash

# --- AdaWriter Provisioning Script ---
# This script automates the complete setup of the AdaWriter software
# on a fresh Raspberry Pi OS Lite installation.

set -e # Exit immediately if a command exits with a non-zero status.

echo "--- Starting AdaWriter Provisioning ---"

# Ensure the script is not run as root, but will use sudo when needed.
if [ "$EUID" -eq 0 ]; then
  echo "Please do not run this script as root. It will use 'sudo' for commands that require root privileges."
  exit 1
fi

# Step 1: Update system and install dependencies
echo "--> Updating package lists and installing system dependencies..."
sudo apt-get update
sudo apt-get install -y git python3-pip python3-pil python3-numpy libxml2-dev libxslt1-dev python3-venv

# Step 2: Enable SPI interface
echo "--> Enabling SPI interface via raspi-config non-interactively..."
sudo raspi-config nonint do_spi 0

# Step 3: Install Waveshare E-Paper Driver
echo "--> Cloning and installing the Waveshare e-Paper driver..."
if [ -d "e-Paper" ]; then
  echo "e-Paper directory already exists. Skipping clone."
else
  git clone https://github.com/waveshare/e-Paper.git
fi
cd e-Paper/RaspberryPi_JetsonNano/python/
sudo python3 setup.py install
cd ../../../
echo "--> E-Paper driver installed."

# Step 4: Set up Python virtual environment and install packages
# This assumes the script is run from within the cloned AdaWriter directory.
echo "--> Setting up Python virtual environment and installing dependencies..."
if [ -d "venv" ]; then
  echo "Virtual environment 'venv' already exists. Skipping creation."
else
  python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt

echo "--- ✅ AdaWriter Provisioning Complete! ---"
echo "You can now run the application with: sudo venv/bin/python3 ada_writer.py"