#!/bin/bash
# This script is run by the kernel as the initial process.

# Mount the root filesystem as read-write
mount -o remount,rw /

# Log all output to a file on the boot partition
exec &> /boot/firmware/init-adawriter.log

echo "--- AdaWriter Init Script Started at $(date) ---"

# Run the main provisioning script in the background
# This allows the main system init to continue booting while provisioning runs.
echo "Starting main provisioning script in the background..."
/bin/bash /boot/firmware/AdaWriter/provision.sh /boot/firmware/AdaWriter &

# Now, remove the init parameter from cmdline.txt to prevent this from running again
echo "Restoring cmdline.txt for next boot..."
# Use sed to remove our 'init=...' parameter from the cmdline file
sed -i 's| init=/boot/firmware/init-adawriter.sh||' /boot/firmware/cmdline.txt

echo "Handing over to the real systemd init..."
# Execute the real system init process
exec /sbin/init

