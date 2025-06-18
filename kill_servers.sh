#!/bin/bash

# Kill all server processes by PID
echo "Killing server processes..."

# Kill processes by PID
kill 90602 90603 90604 90605 90606 2>/dev/null

# Wait a moment for graceful shutdown
sleep 2

# Force kill if any processes are still running
kill -9 90602 90603 90604 90605 90606 2>/dev/null

# Kill background jobs (in case they're still active)
echo "Killing background jobs..."
jobs -p | xargs kill 2>/dev/null
jobs -p | xargs kill -9 2>/dev/null

echo "All server processes and jobs terminated."

# Verify no processes are still running
echo "Checking for any remaining Python server processes..."
ps aux | grep "python3 servers/" | grep -v grep || echo "No remaining server processes found."

