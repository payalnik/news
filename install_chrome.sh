#!/bin/bash

# Exit on error
set -e

# Colors for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  Browser Installation Script         ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root (use sudo)${NC}"
  exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    VER=$VERSION_ID
else
    echo -e "${RED}Cannot detect operating system.${NC}"
    exit 1
fi

echo -e "${YELLOW}Detected OS: $OS $VER${NC}"

# Ask user which browser to install
echo -e "${YELLOW}Which browser would you like to install?${NC}"
echo -e "1) Google Chrome"
echo -e "2) Chromium (open-source version of Chrome)"
read -p "Enter your choice (1 or 2): " browser_choice

if [[ "$browser_choice" == "1" ]]; then
    # Install Chrome based on OS
    if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
        echo -e "${YELLOW}Installing Google Chrome on Ubuntu/Debian...${NC}"
        
        # Add Google Chrome repository
        wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
        echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
        
        # Update package lists
        apt-get update
        
        # Install Chrome
        apt-get install -y google-chrome-stable
        
        echo -e "${GREEN}Google Chrome installed successfully!${NC}"
        
    elif [[ "$OS" == *"CentOS"* ]] || [[ "$OS" == *"Red Hat"* ]] || [[ "$OS" == *"Fedora"* ]]; then
        echo -e "${YELLOW}Installing Google Chrome on CentOS/RHEL/Fedora...${NC}"
        
        # Add Google Chrome repository
        cat > /etc/yum.repos.d/google-chrome.repo << EOL
[google-chrome]
name=google-chrome
baseurl=http://dl.google.com/linux/chrome/rpm/stable/x86_64
enabled=1
gpgcheck=1
gpgkey=https://dl.google.com/linux/linux_signing_key.pub
EOL
        
        # Install Chrome
        if command -v dnf &> /dev/null; then
            dnf install -y google-chrome-stable
        else
            yum install -y google-chrome-stable
        fi
        
        echo -e "${GREEN}Google Chrome installed successfully!${NC}"
        
    else
        echo -e "${RED}Unsupported operating system for Chrome: $OS${NC}"
        echo -e "${YELLOW}Please install Google Chrome manually:${NC}"
        echo -e "1. Download Chrome from https://www.google.com/chrome/"
        echo -e "2. Install the package using your package manager"
        exit 1
    fi

    # Verify installation
    if command -v google-chrome-stable &> /dev/null; then
        CHROME_VERSION=$(google-chrome-stable --version)
        echo -e "${GREEN}Verification: $CHROME_VERSION${NC}"
        echo -e "${GREEN}Chrome is now installed and available in PATH.${NC}"
        echo -e "${GREEN}The news updater application should now be able to use Chrome for web scraping.${NC}"
    else
        echo -e "${RED}Chrome installation verification failed.${NC}"
        echo -e "${YELLOW}Please check if Chrome is installed correctly and available in PATH.${NC}"
        exit 1
    fi

elif [[ "$browser_choice" == "2" ]]; then
    # Install Chromium based on OS
    if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
        echo -e "${YELLOW}Installing Chromium on Ubuntu/Debian...${NC}"
        
        # Install Chromium
        apt-get update
        apt-get install -y chromium-browser || apt-get install -y chromium
        
        echo -e "${GREEN}Chromium installed successfully!${NC}"
        
    elif [[ "$OS" == *"CentOS"* ]] || [[ "$OS" == *"Red Hat"* ]] || [[ "$OS" == *"Fedora"* ]]; then
        echo -e "${YELLOW}Installing Chromium on CentOS/RHEL/Fedora...${NC}"
        
        # Install Chromium
        if command -v dnf &> /dev/null; then
            dnf install -y chromium
        else
            yum install -y chromium
        fi
        
        echo -e "${GREEN}Chromium installed successfully!${NC}"
        
    else
        echo -e "${RED}Unsupported operating system for Chromium: $OS${NC}"
        echo -e "${YELLOW}Please install Chromium manually using your package manager.${NC}"
        exit 1
    fi

    # Verify installation
    if command -v chromium-browser &> /dev/null; then
        CHROMIUM_VERSION=$(chromium-browser --version)
        echo -e "${GREEN}Verification: $CHROMIUM_VERSION${NC}"
        echo -e "${GREEN}Chromium is now installed and available in PATH.${NC}"
        echo -e "${GREEN}The news updater application should now be able to use Chromium for web scraping.${NC}"
    elif command -v chromium &> /dev/null; then
        CHROMIUM_VERSION=$(chromium --version)
        echo -e "${GREEN}Verification: $CHROMIUM_VERSION${NC}"
        echo -e "${GREEN}Chromium is now installed and available in PATH.${NC}"
        echo -e "${GREEN}The news updater application should now be able to use Chromium for web scraping.${NC}"
    else
        echo -e "${RED}Chromium installation verification failed.${NC}"
        echo -e "${YELLOW}Please check if Chromium is installed correctly and available in PATH.${NC}"
        exit 1
    fi

else
    echo -e "${RED}Invalid choice. Please run the script again and select 1 or 2.${NC}"
    exit 1
fi

echo -e "${BLUE}=======================================${NC}"
echo -e "${GREEN}Installation complete!${NC}"
echo -e "${BLUE}=======================================${NC}"
