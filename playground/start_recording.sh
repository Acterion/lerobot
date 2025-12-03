#!/bin/bash
# Start lerobot recording with keyboard control in tmux split panes
# Usage: ./start_recording.sh

SESSION_NAME="lerobot_record"

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "tmux is not installed. Installing..."
    sudo apt-get update && sudo apt-get install -y tmux
fi

# Kill existing session if it exists
tmux kill-session -t $SESSION_NAME 2>/dev/null

# Clean up any old IPC files
rm -f /tmp/lerobot_* 2>/dev/null

# Create new tmux session with the recording script
tmux new-session -d -s $SESSION_NAME -n "record" "cd ~/lerobot/playground && python record.py; echo ''; echo 'Recording script exited. Press Enter to close...'; read"

# Split horizontally and run keyboard controller
tmux split-window -h -t $SESSION_NAME "cd ~/lerobot/playground && python headless_keyboard.py; echo ''; echo 'Keyboard controller exited. Press Enter to close...'; read"

# Select the right pane (keyboard controller) so user can interact
tmux select-pane -t $SESSION_NAME:0.1

# Attach to the session
tmux attach-session -t $SESSION_NAME
