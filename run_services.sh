#!/bin/bash
# Run all NRSC Student Application Pipeline services locally
# This script helps with development by starting all services in separate terminals

# Load environment variables
source .env 2>/dev/null || echo "Warning: .env file not found. Using default environment."

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Starting NRSC Student Application Pipeline ===${NC}"

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not found. Please install Python 3 and try again."
    exit 1
fi

# Check for required directories
for dir in servers/db servers/emails servers/email_polling servers/ai; do
    if [ ! -d "$dir" ]; then
        echo "Required directory $dir not found. Please ensure you're in the project root."
        exit 1
    fi
done

# Function to start a service in a new terminal
start_service() {
    local service_name=$1
    local command=$2
    local port=$3
    
    echo -e "${GREEN}Starting $service_name on port $port...${NC}"
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        osascript -e "tell app \"Terminal\" to do script \"cd $(pwd) && $command\""
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v gnome-terminal &> /dev/null; then
            gnome-terminal -- bash -c "cd $(pwd) && $command; exec bash"
        elif command -v xterm &> /dev/null; then
            xterm -e "cd $(pwd) && $command; exec bash" &
        else
            echo "Could not find suitable terminal emulator. Please start manually:"
            echo "cd $(pwd) && $command"
        fi
    else
        echo "Unsupported OS. Please start the service manually:"
        echo "cd $(pwd) && $command"
    fi
}

# Start DB Server
start_service "DB Server" "cd servers/db && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000" 8000
sleep 2

# Start Email Server
start_service "Email Server" "cd servers/emails && python3 -m uvicorn main:app --host 0.0.0.0 --port 8001" 8001
sleep 2

# Start Email Polling Server
start_service "Email Polling Server" "cd servers/email_polling && python3 -m uvicorn main:app --host 0.0.0.0 --port 8002" 8002
sleep 2

# Start AI Server
start_service "AI Server" "cd servers/ai && python3 -m uvicorn server:app --host 0.0.0.0 --port 8003" 8003

echo -e "${YELLOW}All services started. Access them at:${NC}"
echo "DB Server:          http://localhost:8000"
echo "Email Server:       http://localhost:8001"
echo "Email Polling:      http://localhost:8002"
echo "AI Server:          http://localhost:8003"

echo -e "${BLUE}=== Services are now running ===${NC}"
