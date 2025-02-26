#!/bin/bash

# Colors for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  News Updater Email Setup Assistant   ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if Redis is installed
echo -e "${YELLOW}Checking Redis installation...${NC}"
if command_exists redis-cli; then
    echo -e "${GREEN}✓ Redis is installed.${NC}"
    
    # Check if Redis server is running
    if redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Redis server is running.${NC}"
    else
        echo -e "${RED}✗ Redis server is not running.${NC}"
        echo -e "  Please start Redis server with: ${YELLOW}redis-server${NC}"
        echo -e "  You can run it in the background or in a separate terminal."
    fi
else
    echo -e "${RED}✗ Redis is not installed.${NC}"
    echo -e "Redis is required for Celery task scheduling. Please install Redis:"
    echo -e "  - macOS: ${YELLOW}brew install redis${NC}"
    echo -e "  - Linux: ${YELLOW}sudo apt-get install redis-server${NC}"
    echo -e "  - Windows: Download from https://github.com/tporadowski/redis/releases"
    echo
    echo -e "After installation, start the Redis server."
fi

echo
echo -e "${YELLOW}Checking .env file configuration...${NC}"

# Check if .env file exists
if [ -f .env ]; then
    echo -e "${GREEN}✓ .env file exists.${NC}"
    
    # Check which email provider is configured
    if grep -q "^EMAIL_HOST=email-smtp" .env; then
        echo -e "${GREEN}✓ Amazon SES appears to be configured.${NC}"
        
        # Check if SES settings are using placeholders
        if grep -q "EMAIL_HOST_USER=your_ses_smtp_username" .env; then
            echo -e "${RED}✗ Amazon SES credentials not configured.${NC}"
            echo -e "  Please edit the .env file to update your Amazon SES credentials."
            echo -e "  See amazon_ses_setup.md for detailed instructions."
        fi
        
        # Check if DEFAULT_FROM_EMAIL is configured
        if ! grep -q "^DEFAULT_FROM_EMAIL=" .env; then
            echo -e "${YELLOW}! DEFAULT_FROM_EMAIL not configured.${NC}"
            echo -e "  Consider adding DEFAULT_FROM_EMAIL to your .env file to customize the sender address."
            echo -e "  For Amazon SES, this email must be verified in the SES console."
        fi
    elif grep -q "^EMAIL_HOST=smtp.gmail.com" .env; then
        echo -e "${GREEN}✓ Gmail appears to be configured.${NC}"
        
        # Check if Gmail settings are using placeholders
        if grep -q "EMAIL_HOST_USER=your_email@gmail.com" .env; then
            echo -e "${RED}✗ Gmail credentials not configured.${NC}"
            echo -e "  Please edit the .env file to update your Gmail credentials."
            echo -e "  See email_setup_guide.md for detailed instructions."
        fi
        
        # Check if DEFAULT_FROM_EMAIL is configured
        if ! grep -q "^DEFAULT_FROM_EMAIL=" .env; then
            echo -e "${YELLOW}! DEFAULT_FROM_EMAIL not configured.${NC}"
            echo -e "  Consider adding DEFAULT_FROM_EMAIL to your .env file to customize the sender address."
        fi
    elif grep -q "^# EMAIL_HOST=" .env; then
        echo -e "${YELLOW}! Email provider commented out in .env file.${NC}"
        echo -e "  Please uncomment your preferred email provider settings."
        echo -e "  See email_setup_guide.md or amazon_ses_setup.md for instructions."
    else
        echo -e "${YELLOW}? Email provider configuration unclear.${NC}"
        echo -e "  Please check your .env file and update your email settings."
        echo -e "  See email_setup_guide.md for general instructions or"
        echo -e "  amazon_ses_setup.md for Amazon SES specific instructions."
    fi
else
    echo -e "${RED}✗ .env file not found.${NC}"
    echo -e "  Please create a .env file in the project root directory."
    echo -e "  You can copy the example settings from email_setup_guide.md"
fi

echo
echo -e "${YELLOW}Which email provider would you like to use?${NC}"
echo -e "1) Gmail"
echo -e "2) Amazon SES (recommended)"
echo -e "3) Other provider"
read -r provider_choice

case $provider_choice in
    1)
        echo -e "${GREEN}Selected Gmail as email provider.${NC}"
        echo -e "Please see email_setup_guide.md for Gmail setup instructions."
        ;;
    2)
        echo -e "${GREEN}Selected Amazon SES as email provider.${NC}"
        echo -e "Please see amazon_ses_setup.md for detailed Amazon SES setup instructions."
        ;;
    3)
        echo -e "${GREEN}Selected other email provider.${NC}"
        echo -e "Please see email_setup_guide.md for configuration options for other providers."
        ;;
    *)
        echo -e "${YELLOW}No selection made. Continuing with current configuration.${NC}"
        ;;
esac

echo
echo -e "${YELLOW}Would you like to edit your .env file now? (y/n)${NC}"
read -r edit_env

if [[ $edit_env == "y" || $edit_env == "Y" ]]; then
    # Determine which editor to use
    if command_exists nano; then
        nano .env
    elif command_exists vim; then
        vim .env
    elif command_exists vi; then
        vi .env
    else
        echo -e "${RED}No text editor found (tried nano, vim, vi).${NC}"
        echo -e "Please edit the .env file manually with your preferred editor."
    fi
fi

echo
echo -e "${YELLOW}Would you like to test your email configuration? (y/n)${NC}"
read -r test_email

if [[ $test_email == "y" || $test_email == "Y" ]]; then
    echo -e "${YELLOW}Enter recipient email address (leave blank to send to yourself):${NC}"
    read -r recipient
    
    if [ -z "$recipient" ]; then
        ./test_email_config.py
    else
        ./test_email_config.py "$recipient"
    fi
fi

echo
echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  Next Steps  ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo
echo -e "1. Start the Django development server:"
echo -e "   ${YELLOW}cd news_updater${NC}"
echo -e "   ${YELLOW}python manage.py runserver${NC}"
echo
echo -e "2. In a separate terminal, start Celery worker:"
echo -e "   ${YELLOW}cd news_updater${NC}"
echo -e "   ${YELLOW}celery -A news_updater worker -l info${NC}"
echo
echo -e "3. In another terminal, start Celery beat:"
echo -e "   ${YELLOW}cd news_updater${NC}"
echo -e "   ${YELLOW}celery -A news_updater beat -l info${NC}"
echo
echo -e "4. Access the application at: ${GREEN}http://localhost:8000${NC}"
echo
echo -e "For more information, see: ${GREEN}email_setup_guide.md${NC}"
echo
echo -e "${BLUE}=======================================${NC}"
