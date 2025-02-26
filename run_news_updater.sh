#!/bin/bash

# Colors for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  News Updater Startup Script         ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if tmux is installed
if ! command_exists tmux; then
    echo -e "${RED}Error: tmux is not installed.${NC}"
    echo -e "This script requires tmux to run multiple processes in one terminal."
    echo -e "Please install tmux:"
    echo -e "  - macOS: ${YELLOW}brew install tmux${NC}"
    echo -e "  - Linux: ${YELLOW}sudo apt-get install tmux${NC}"
    exit 1
fi

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

# Create a new tmux session detached
echo -e "${YELLOW}Starting services...${NC}"
tmux new-session -d -s news_updater

# Split the window into three panes
tmux split-window -h -t news_updater
tmux split-window -v -t news_updater:0.1

# Start Django server in the first pane
tmux send-keys -t news_updater:0.0 "cd news_updater && python manage.py runserver" C-m

# Start Celery worker in the second pane
tmux send-keys -t news_updater:0.1 "cd news_updater && celery -A news_updater worker -l info" C-m

# Start Celery beat in the third pane
tmux send-keys -t news_updater:0.2 "cd news_updater && celery -A news_updater beat -l info" C-m

# Attach to the tmux session
echo -e "${GREEN}✓ All services started successfully.${NC}"
echo -e "${YELLOW}Attaching to tmux session...${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  Tmux Controls:                      ${NC}"
echo -e "${BLUE}  - Switch panes: Ctrl+B, arrow keys  ${NC}"
echo -e "${BLUE}  - Detach: Ctrl+B, D                 ${NC}"
echo -e "${BLUE}  - Scroll: Ctrl+B, [                 ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "${GREEN}Press Enter to continue...${NC}"
read

# Attach to the tmux session
tmux attach-session -t news_updater
