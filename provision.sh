#!/bin/bash

# --- AdaWriter Provisioning Script v3.6 ---

echo "Waiting for time synchronization..."
while ! timedatectl status | grep -q "System clock synchronized: yes"; do
    echo "Time not synchronized, sleeping for 5 seconds..."
    sleep 5
done
echo "Time is synchronized. Proceeding with provisioning."

set -e
export DEBIAN_FRONTEND=noninteractive

LOG_FILE="/var/log/adawriter-provisioning.log"
exec &> >(tee -a "${LOG_FILE}")

TARGET_USER="admin"
TARGET_HOME="/home/${TARGET_USER}"
PROJECT_DIR="${TARGET_HOME}/AdaWriter"

echo "--- Starting AdaWriter Provisioning for user '${TARGET_USER}' ---"

# --- Installation with Retry Loop ---
MAX_RETRIES=5
COUNT=0
echo "--> Updating package lists and installing system dependencies..."
until apt-get install -y git python3-pip python3-numpy libxml2-dev libxslt1-dev python3-venv libopenjp2-7 build-essential python3-gpiozero python3-rpi.gpio python3-full libbcm2835-dev; do
    COUNT=$((COUNT+1))
    if [ $COUNT -ge $MAX_RETRIES ]; then
        echo "Failed to install packages after $MAX_RETRIES attempts. Aborting."
        exit 1
    fi
    echo "apt-get install failed. Retrying in 15 seconds..."
    sleep 15
    apt-get update -y # Refresh package list before retrying
done
# --- End of Installation ---


echo "--> Enabling SPI interface..."
raspi-config nonint do_spi 0

echo "--> Copying AdaWriter project from /boot/firmware/AdaWriter..."
if [ -d "${PROJECT_DIR}" ]; then
    rm -rf "${PROJECT_DIR}"
fi
mkdir -p "${PROJECT_DIR}"
cp -r /boot/firmware/AdaWriter/. "${PROJECT_DIR}/"
chown -R ${TARGET_USER}:${TARGET_USER} "${PROJECT_DIR}"

echo "--> Pausing for 15 seconds to ensure network services are stable..."
sleep 15

echo "--> Creating Python virtual environment at ${PROJECT_DIR}/venv..."
python3 -m venv --system-site-packages "${PROJECT_DIR}/venv"

echo "--> Installing Python dependencies into the virtual environment..."
"${PROJECT_DIR}/venv/bin/pip" install -r "${PROJECT_DIR}/requirements.txt" --no-input

echo '--> Cloning and installing Waveshare e-Paper driver into venv...'
git clone --depth 1 https://github.com/waveshare/e-Paper.git "${TARGET_HOME}/e-Paper"
"${PROJECT_DIR}/venv/bin/pip" install "${TARGET_HOME}/e-Paper/RaspberryPi_JetsonNano/python" --no-input
rm -rf "${TARGET_HOME}/e-Paper"

echo '--> Surgically removing conflicting libraries...'
SITE_PACKAGES=$(find "${PROJECT_DIR}/venv/lib/" -type d -name "site-packages")
rm -rf "${SITE_PACKAGES}/Jetson"
find "${SITE_PACKAGES}" -maxdepth 1 -type d -name 'Jetson.GPIO-*' -exec rm -rf {} +
rm -rf "${SITE_PACKAGES}/RPi"

echo "--> Creating and enabling systemd service for auto-start..."
SERVICE_FILE_PATH="/etc/systemd/system/adawriter.service"
cat > "${SERVICE_FILE_PATH}" << EOF
[Unit]
Description=AdaWriter Distraction-Free Writing Device
After=network.target

[Service]
ExecStart=${PROJECT_DIR}/venv/bin/python3 ${PROJECT_DIR}/ada_writer.py
WorkingDirectory=${PROJECT_DIR}
StandardOutput=inherit
StandardError=inherit
Restart=always
User=${TARGET_USER}

[Install]
WantedBy=multi-user.target
EOF
systemctl enable adawriter.service

echo "--> Adding user to hardware groups..."
adduser ${TARGET_USER} spi
adduser ${TARGET_USER} gpio
adduser ${TARGET_USER} input

echo "Disabling one-time provisioning service..."
systemctl disable provision.service

echo "--- ✅ AdaWriter Provisioning Complete! ---"
echo "Rebooting now to start the AdaWriter service..."
reboot
