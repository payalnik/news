#!/bin/bash

# Colors for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  News Updater Startup Script (Basic)  ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if Redis is installed and running
echo -e "${YELLOW}Checking Redis installation...${NC}"
if command_exists redis-cli; then
    echo -e "${GREEN}✓ Redis is installed.${NC}"
    
    # Check if Redis server is running
    if redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Redis server is running.${NC}"
    else
        echo -e "${RED}✗ Redis server is not running.${NC}"
        echo -e "  Redis is required for Celery. Starting Redis server..."
        
        # Try to start Redis server
        if command_exists redis-server; then
            redis-server --daemonize yes
            sleep 2
            if redis-cli ping > /dev/null 2>&1; then
                echo -e "${GREEN}✓ Redis server started successfully.${NC}"
            else
                echo -e "${RED}✗ Failed to start Redis server.${NC}"
                echo -e "  Please start Redis server manually with: ${YELLOW}redis-server${NC}"
                exit 1
            fi
        else
            echo -e "${RED}✗ Cannot start Redis server automatically.${NC}"
            echo -e "  Please start Redis server manually with: ${YELLOW}redis-server${NC}"
            exit 1
        fi
    fi
else
    echo -e "${RED}✗ Redis is not installed.${NC}"
    echo -e "Redis is required for Celery task scheduling. Please install Redis:"
    echo -e "  - macOS: ${YELLOW}brew install redis${NC}"
    echo -e "  - Linux: ${YELLOW}sudo apt-get install redis-server${NC}"
    echo -e "  - Windows: Download from https://github.com/tporadowski/redis/releases"
    exit 1
fi

# Check if .env file exists
echo -e "${YELLOW}Checking .env file...${NC}"
if [ ! -f .env ]; then
    echo -e "${RED}✗ .env file not found.${NC}"
    echo -e "  Please create a .env file in the project root directory."
    echo -e "  You can run: ${YELLOW}./setup_email_environment.sh${NC} to set up your email configuration."
    exit 1
else
    echo -e "${GREEN}✓ .env file exists.${NC}"
fi

# Check if virtual environment is activated
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo -e "${YELLOW}! Virtual environment is not activated.${NC}"
    
    # Check if venv directory exists
    if [ -d "venv" ]; then
        echo -e "  Activating virtual environment..."
        source venv/bin/activate
        echo -e "${GREEN}✓ Virtual environment activated.${NC}"
    else
        echo -e "${YELLOW}! Virtual environment directory 'venv' not found.${NC}"
        echo -e "  It's recommended to use a virtual environment."
        echo -e "  You can create one with: ${YELLOW}python -m venv venv${NC}"
        echo -e "  And activate it with: ${YELLOW}source venv/bin/activate${NC}"
        
        # Ask if user wants to continue without virtual environment
        echo -e "${YELLOW}Do you want to continue without a virtual environment? (y/n)${NC}"
        read -r continue_without_venv
        
        if [[ "$continue_without_venv" != "y" && "$continue_without_venv" != "Y" ]]; then
            exit 1
        fi
    fi
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Function to run a command with a prefix for each line of output
run_with_prefix() {
    local prefix="$1"
    local command="$2"
    local log_file="$3"
    
    # Run the command and capture its PID
    (
        # Change to the news_updater directory
        cd news_updater
        
        # Run the command and pipe its output through sed to add the prefix
        eval "$command" 2>&1 | sed "s/^/${prefix} /" | tee "../$log_file"
    ) &
    
    # Return the PID of the background process
    echo $!
}

echo -e "${YELLOW}Starting all services...${NC}"
echo -e "${GREEN}✓ All output will be prefixed with the service name and logged to files${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo -e "${BLUE}=======================================${NC}"

# Start Django server
DJANGO_PID=$(run_with_prefix "[Django]" "python manage.py runserver" "logs/django.log")
echo -e "${GREEN}✓ Django server started (PID: $DJANGO_PID)${NC}"

# Start Celery worker
WORKER_PID=$(run_with_prefix "[Celery-Worker]" "celery -A news_updater worker -l info" "logs/celery_worker.log")
echo -e "${GREEN}✓ Celery worker started (PID: $WORKER_PID)${NC}"

# Start Celery beat
BEAT_PID=$(run_with_prefix "[Celery-Beat]" "celery -A news_updater beat -l info" "logs/celery_beat.log")
echo -e "${GREEN}✓ Celery beat started (PID: $BEAT_PID)${NC}"

# Save PIDs to a file for cleanup
echo "$DJANGO_PID $WORKER_PID $BEAT_PID" > logs/pids.txt

echo
echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  News Updater is now running!        ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "${GREEN}Access the application at: http://localhost:8000${NC}"
echo -e "${YELLOW}Logs are also being saved to the logs/ directory${NC}"

# Function to clean up processes when script is terminated
cleanup() {
    echo
    echo -e "${YELLOW}Stopping all services...${NC}"
    kill $DJANGO_PID $WORKER_PID $BEAT_PID 2>/dev/null
    echo -e "${GREEN}✓ All services stopped${NC}"
    exit 0
}

# Set up trap to catch Ctrl+C and other termination signals
trap cleanup SIGINT SIGTERM

# Wait for all background processes to finish (which they won't unless terminated)
wait
