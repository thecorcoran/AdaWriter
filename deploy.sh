#!/bin/bash

# --- AdaWriter Deploy Script ---
# This script syncs the local files to the Pi,
# kills any old running process, and starts the new one.

echo "🔄 Syncing files to AdaWriter..."

# Step 1: Sync files using your rsync command
rsync -avz --delete \
  --exclude 'projects/' \
  --exclude '*.pyc' \
  --exclude '__pycache__/' \
  --exclude '.venv/' \
  --exclude 'venv/' \
  --exclude 'adawriter.log' \
  --exclude 'sim_output.png' \
  --exclude '.git/' \
  ~/Desktop/AdaWriter/ \
  admin@10.0.0.31:~/

# Check if rsync was successful
if [ $? -eq 0 ]; then
  echo "✅ Sync complete."
  echo "🚀 Restarting the AdaWriter service on the Pi..."

  # Step 2: SSH into the Pi and run the commands
  ssh admin@10.0.0.31 << EOF
    # Stop the service to release all resources (like the keyboard)
    sudo systemctl stop adawriter.service

    # Ensure all Python dependencies are installed
    echo "Installing/updating Python packages..."
    source ~/AdaWriter/venv/bin/activate
    pip install -r ~/AdaWriter/requirements.txt --no-input
    
    # Restart the service with the new code
    sudo systemctl start adawriter.service
    
    echo "Service restarted. Tailing logs for 10 seconds..."
    timeout 10 sudo journalctl -u adawriter.service -f --no-pager
EOF
  echo "🎉 Deployment complete. The service is now running on the AdaWriter."
else
  echo "❌ Error: rsync failed. Please check the connection and paths."
fi