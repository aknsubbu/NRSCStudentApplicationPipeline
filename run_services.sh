#!/bin/bash
# Run all NRSC Student Application Pipeline services locally
# This script helps with development by starting all services in separate terminals

# Load environment variables
source .env 2>/dev/null || echo "Warning: .env file not found. Using default environment."

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Starting NRSC Student Application Pipeline ===${NC}"

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is required but not found. Please install Python 3 and try again.${NC}"
    exit 1
fi

# Check for virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${RED}Virtual environment not found. Please create it first with 'python3 -m venv .venv'${NC}"
    exit 1
fi

# Check for required directories
for dir in servers/db servers/emails servers/manager servers/ai; do
    if [ ! -d "$dir" ]; then
        echo -e "${RED}Required directory $dir not found. Please ensure you're in the project root.${NC}"
        exit 1
    fi
done

# Function to start a service in a new terminal
start_service() {
    local service_name=$1
    local command=$2
    local port=$3
    
    echo -e "${GREEN}Starting $service_name on port $port...${NC}"
    
    # Construct the full command with venv activation
    local full_command="cd $(pwd) && source .venv/bin/activate && $command"
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        osascript -e "tell app \"Terminal\" to do script \"$full_command\""
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v gnome-terminal &> /dev/null; then
            gnome-terminal -- bash -c "$full_command; exec bash"
        elif command -v xterm &> /dev/null; then
            xterm -e "$full_command; exec bash" &
        else
            echo -e "${RED}Could not find suitable terminal emulator. Please start manually:${NC}"
            echo "$full_command"
        fi
    else
        echo -e "${RED}Unsupported OS. Please start the service manually:${NC}"
        echo "$full_command"
    fi
}

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -i :$port > /dev/null 2>&1; then
        echo -e "${RED}Port $port is already in use. Please free up the port and try again.${NC}"
        exit 1
    fi
}

# Check if ports are available
for port in 8000 8001 8002 8003; do
    check_port $port
done

# Start DB Server
start_service "DB Server" "python3 servers/db/main.py" 8000
sleep 2

# Start Email Server
start_service "Email Server" "python3 servers/emails/main.py" 8001
sleep 2

# Start Manager Server
start_service "Manager Server" "python3 servers/manager/main.py" 8002
sleep 2

# Start AI Server
start_service "AI Server" "python3 servers/ai/server.py" 8003

echo -e "${YELLOW}All services started. Access them at:${NC}"
echo "DB Server:          http://localhost:8000"
echo "Email Server:       http://localhost:8001"
echo "Manager Server:     http://localhost:8002"
echo "AI Server:          http://localhost:8003"

echo -e "${BLUE}=== Services are now running ===${NC}"
echo -e "${YELLOW}Note: Press Ctrl+C in each terminal window to stop individual services${NC}"
