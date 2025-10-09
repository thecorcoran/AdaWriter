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
      # Download and execute the main provisioning script
      echo "First boot: Downloading and running provision.sh..."
      wget -O /tmp/provision.sh https://raw.githubusercontent.com/thecorcoran/AdaWriter/adawriter-features-partial/provision.sh
      chmod +x /tmp/provision.sh
      /tmp/provision.sh

runcmd:
  - /opt/first-boot-setup.sh