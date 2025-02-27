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
echo -e "${BLUE}  Compatible ChromeDriver Downloader   ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo

# Detect OS and architecture
OS="$(uname -s)"
ARCH="$(uname -m)"

echo -e "${YELLOW}Detected OS: $OS, Architecture: $ARCH${NC}"

# Create a directory for the chromedriver
INSTALL_DIR="$(pwd)"
echo -e "${YELLOW}Will install chromedriver to: $INSTALL_DIR${NC}"

# Download ChromeDriver 2.46 (compatible with Chrome 2.67)
# This is the last version of ChromeDriver that supports Chrome 2.x
echo -e "${YELLOW}Downloading ChromeDriver 2.46...${NC}"

if [[ "$OS" == "Linux" ]]; then
    if [[ "$ARCH" == "x86_64" ]]; then
        CHROMEDRIVER_URL="https://chromedriver.storage.googleapis.com/2.46/chromedriver_linux64.zip"
    else
        CHROMEDRIVER_URL="https://chromedriver.storage.googleapis.com/2.46/chromedriver_linux32.zip"
    fi
elif [[ "$OS" == "Darwin" ]]; then
    CHROMEDRIVER_URL="https://chromedriver.storage.googleapis.com/2.46/chromedriver_mac64.zip"
elif [[ "$OS" == *"MINGW"* ]] || [[ "$OS" == *"MSYS"* ]] || [[ "$OS" == *"CYGWIN"* ]]; then
    CHROMEDRIVER_URL="https://chromedriver.storage.googleapis.com/2.46/chromedriver_win32.zip"
else
    echo -e "${RED}Unsupported OS: $OS${NC}"
    exit 1
fi

# Download and extract ChromeDriver
echo -e "${YELLOW}Downloading from: $CHROMEDRIVER_URL${NC}"
curl -L -o chromedriver.zip "$CHROMEDRIVER_URL"
unzip -o chromedriver.zip
rm chromedriver.zip

# Make chromedriver executable
chmod +x chromedriver

echo -e "${GREEN}ChromeDriver 2.46 has been downloaded and installed to: $INSTALL_DIR/chromedriver${NC}"
echo -e "${YELLOW}This version is compatible with Chrome 2.67${NC}"

# Test the chromedriver
echo -e "${YELLOW}Testing ChromeDriver...${NC}"
./chromedriver --version

echo -e "${BLUE}=======================================${NC}"
echo -e "${GREEN}Installation complete!${NC}"
echo -e "${BLUE}=======================================${NC}"
