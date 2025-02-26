#!/bin/bash

# Colors for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  News Updater Startup Script (Parallel) ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if parallel is installed
if ! command_exists parallel; then
    echo -e "${RED}Error: GNU Parallel is not installed.${NC}"
    echo -e "This script requires GNU Parallel to run multiple processes in one terminal."
    echo -e "Please install GNU Parallel:"
    echo -e "  - macOS: ${YELLOW}brew install parallel${NC}"
    echo -e "  - Linux: ${YELLOW}sudo apt-get install parallel${NC}"
    echo -e "  - Or use one of the other startup scripts: run_news_updater.sh or run_news_updater_simple.sh"
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

echo -e "${YELLOW}Starting all services in parallel...${NC}"
echo -e "${GREEN}✓ Django server, Celery worker, and Celery beat will run in this terminal${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo -e "${BLUE}=======================================${NC}"

# Create a temporary directory for the commands
mkdir -p .tmp_commands

# Create command files
echo "cd news_updater && python manage.py runserver" > .tmp_commands/django.sh
echo "cd news_updater && celery -A news_updater worker -l info" > .tmp_commands/celery_worker.sh
echo "cd news_updater && celery -A news_updater beat -l info" > .tmp_commands/celery_beat.sh

# Make them executable
chmod +x .tmp_commands/django.sh .tmp_commands/celery_worker.sh .tmp_commands/celery_beat.sh

# Run all commands in parallel with labeled output
parallel --lb --tagstring '{1}:' :::: <(echo "Django" "Celery-Worker" "Celery-Beat") ::: .tmp_commands/django.sh .tmp_commands/celery_worker.sh .tmp_commands/celery_beat.sh

# Clean up temporary files (this will only run if the user presses Ctrl+C)
rm -rf .tmp_commands
