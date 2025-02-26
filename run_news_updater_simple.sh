#!/bin/bash

# Colors for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  News Updater Startup Script (Simple) ${NC}"
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

# Check if screen is available
if command_exists screen; then
    echo -e "${YELLOW}Starting services with screen...${NC}"
    
    # Start Django server
    screen -dmS django bash -c "cd news_updater && python manage.py runserver; exec bash"
    echo -e "${GREEN}✓ Django server started in screen session 'django'${NC}"
    
    # Start Celery worker
    screen -dmS celery_worker bash -c "cd news_updater && celery -A news_updater worker -l info; exec bash"
    echo -e "${GREEN}✓ Celery worker started in screen session 'celery_worker'${NC}"
    
    # Start Celery beat
    screen -dmS celery_beat bash -c "cd news_updater && celery -A news_updater beat -l info; exec bash"
    echo -e "${GREEN}✓ Celery beat started in screen session 'celery_beat'${NC}"
    
    echo -e "${BLUE}=======================================${NC}"
    echo -e "${BLUE}  All services started successfully    ${NC}"
    echo -e "${BLUE}=======================================${NC}"
    echo -e "${YELLOW}To view a service, use:${NC}"
    echo -e "  ${GREEN}screen -r django${NC} - For Django server"
    echo -e "  ${GREEN}screen -r celery_worker${NC} - For Celery worker"
    echo -e "  ${GREEN}screen -r celery_beat${NC} - For Celery beat"
    echo -e "${YELLOW}To detach from a screen session:${NC}"
    echo -e "  Press ${GREEN}Ctrl+A, then D${NC}"
    echo -e "${YELLOW}To kill all sessions when done:${NC}"
    echo -e "  ${GREEN}screen -X -S django quit${NC}"
    echo -e "  ${GREEN}screen -X -S celery_worker quit${NC}"
    echo -e "  ${GREEN}screen -X -S celery_beat quit${NC}"
    
else
    echo -e "${YELLOW}Screen is not available. Starting services in background...${NC}"
    
    # Create logs directory if it doesn't exist
    mkdir -p logs
    
    # Start Django server
    cd news_updater && python manage.py runserver > ../logs/django.log 2>&1 &
    DJANGO_PID=$!
    cd ..
    echo -e "${GREEN}✓ Django server started (PID: $DJANGO_PID)${NC}"
    
    # Start Celery worker
    cd news_updater && celery -A news_updater worker -l info > ../logs/celery_worker.log 2>&1 &
    WORKER_PID=$!
    cd ..
    echo -e "${GREEN}✓ Celery worker started (PID: $WORKER_PID)${NC}"
    
    # Start Celery beat
    cd news_updater && celery -A news_updater beat -l info > ../logs/celery_beat.log 2>&1 &
    BEAT_PID=$!
    cd ..
    echo -e "${GREEN}✓ Celery beat started (PID: $BEAT_PID)${NC}"
    
    echo -e "${BLUE}=======================================${NC}"
    echo -e "${BLUE}  All services started successfully    ${NC}"
    echo -e "${BLUE}=======================================${NC}"
    echo -e "${YELLOW}Logs are being written to:${NC}"
    echo -e "  ${GREEN}logs/django.log${NC} - For Django server"
    echo -e "  ${GREEN}logs/celery_worker.log${NC} - For Celery worker"
    echo -e "  ${GREEN}logs/celery_beat.log${NC} - For Celery beat"
    echo -e "${YELLOW}To view logs in real-time:${NC}"
    echo -e "  ${GREEN}tail -f logs/django.log${NC}"
    echo -e "  ${GREEN}tail -f logs/celery_worker.log${NC}"
    echo -e "  ${GREEN}tail -f logs/celery_beat.log${NC}"
    echo -e "${YELLOW}To stop all services:${NC}"
    echo -e "  ${GREEN}kill $DJANGO_PID $WORKER_PID $BEAT_PID${NC}"
    
    # Save PIDs to a file for easy cleanup
    echo "$DJANGO_PID $WORKER_PID $BEAT_PID" > logs/pids.txt
    echo -e "${YELLOW}PIDs saved to logs/pids.txt. To stop all services:${NC}"
    echo -e "  ${GREEN}kill \$(cat logs/pids.txt)${NC}"
fi

echo
echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  News Updater is now running!        ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "${GREEN}Access the application at: http://localhost:8000${NC}"
