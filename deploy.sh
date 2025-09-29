#!/bin/bash

# --- AdaWriter Deploy Script ---
# This script syncs the local files to the Pi,
# kills any old running process, and starts the new one.

echo "🔄 Syncing files to AdaWriter..."

# Step 1: Sync files using your rsync command
rsync -avz \
  --exclude 'projects/' \
  --exclude '*.pyc' \
  --exclude '__pycache__/' \
  --exclude '.venv/' \
  --exclude 'venv/' \
  --exclude 'adawriter.log' \
  --exclude 'sim_output.png' \
  ~/Desktop/AdaWriter/ \
  admin@10.0.0.31:~/AdaWriter/

# Check if rsync was successful
if [ $? -eq 0 ]; then
  echo "✅ Sync complete."
  echo "🚀 Restarting the script on the Pi..."

  # Step 2: SSH into the Pi and run the commands
  ssh admin@10.0.0.31 << EOF
    # Go to the project directory
    cd ~/AdaWriter

    # Kill any previously running instance of the script
    pkill -f ada_writer.py
    sleep 0.5 # Give it a moment to release resources

    # Activate the virtual environment and run the new script
    source venv/bin/activate
    python3 ada_writer.py
EOF
  echo "🎉 Script is running on the AdaWriter."
else
  echo "❌ Error: rsync failed. Please check the connection and paths."
fi