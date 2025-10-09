#cloud-config

# This script is designed to be run on the first boot of a Raspberry Pi.
# Its contents should be copied into a file named `user-data` on the `/boot`
# partition of the SD card after flashing a Bookworm-based OS.
# It downloads and executes the main provisioning script from the GitHub repository.
runcmd:
  - |
    #!/bin/bash
    set -e

    # Wait for network connectivity.
    echo "First boot: Waiting for network..."
    while ! ping -c 1 -W 1 google.com &> /dev/null; do
        sleep 2
    done
    echo "First boot: Network is up."
    
    # Download and execute the main provisioning script
    echo "First boot: Downloading and running provision.sh..."
    wget -O /tmp/provision.sh https://raw.githubusercontent.com/thecorcoran/AdaWriter/main/provision.sh
    chmod +x /tmp/provision.sh
    sudo /tmp/provision.sh