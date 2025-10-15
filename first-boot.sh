#cloud-config

package_update: true
package_upgrade: true

write_files:
  - path: /opt/first-boot-setup.sh
    permissions: '0755'
    content: |
      #!/bin/bash
      set -e
      # Wait for network connectivity.
      echo "First boot: Waiting for network..."
      while ! ping -c 1 -W 1 google.com &> /dev/null; do
          sleep 2
      done
      echo "First boot: Network is up."
      # Copy and execute the main provisioning script from the boot partition
      echo "First boot: Copying and running provision.sh from /boot/AdaWriter..."
      cp /boot/AdaWriter/provision.sh /tmp/provision.sh
      chmod +x /tmp/provision.sh
      /tmp/provision.sh

runcmd:
  - /opt/first-boot-setup.sh