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
echo -e "${BLUE}  Playwright Dependencies Installer    ${NC}"
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

# Install dependencies based on OS
if [[ "$OS" == *"Ubuntu"* ]] || [[ "$OS" == *"Debian"* ]]; then
    echo -e "${YELLOW}Installing Playwright dependencies on Ubuntu/Debian...${NC}"
    
    # Update package lists
    apt-get update
    
    # Install dependencies
    apt-get install -y \
        libwoff2dec1.0.2 \
        libvpx7 \
        libevent-2.1-7 \
        libopus0 \
        libharfbuzz-icu0 \
        libgstreamer-plugins-base1.0-0 \
        gstreamer1.0-plugins-base \
        libgstreamer1.0-0 \
        libgstreamer-gl1.0-0 \
        libgstreamer-plugins-bad1.0-0 \
        libwebpdemux2 \
        libenchant-2-2 \
        libsecret-1-0 \
        libhyphen0 \
        libmanette-0.2-0 \
        libx264-dev \
        libwebp-dev \
        libflite1 \
        libgles2
    
    # Install additional dependencies that might be needed
    apt-get install -y \
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libdbus-1-3 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libatspi2.0-0 \
        libwayland-client0
    
    echo -e "${GREEN}Playwright dependencies installed successfully!${NC}"
    
elif [[ "$OS" == *"CentOS"* ]] || [[ "$OS" == *"Red Hat"* ]] || [[ "$OS" == *"Fedora"* ]]; then
    echo -e "${YELLOW}Installing Playwright dependencies on CentOS/RHEL/Fedora...${NC}"
    
    # Install dependencies
    if command -v dnf &>/dev/null; then
        dnf install -y \
            libvpx \
            libevent \
            opus \
            harfbuzz \
            gstreamer1 \
            gstreamer1-plugins-base \
            webp \
            enchant2 \
            libsecret \
            hyphen \
            libmanette \
            x264 \
            flite \
            mesa-libGLES
    else
        yum install -y \
            libvpx \
            libevent \
            opus \
            harfbuzz \
            gstreamer1 \
            gstreamer1-plugins-base \
            webp \
            enchant2 \
            libsecret \
            hyphen \
            libmanette \
            x264 \
            flite \
            mesa-libGLES
    fi
    
    echo -e "${GREEN}Playwright dependencies installed successfully!${NC}"
    
else
    echo -e "${RED}Unsupported operating system: $OS${NC}"
    echo -e "${YELLOW}Please install Playwright dependencies manually.${NC}"
    echo -e "${YELLOW}You can run 'playwright install-deps' to see what dependencies are needed.${NC}"
    exit 1
fi

# Run playwright install to download browsers
echo -e "${YELLOW}Running 'playwright install' to download browsers...${NC}"
playwright install

echo -e "${BLUE}=======================================${NC}"
echo -e "${GREEN}Installation complete!${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "${YELLOW}If you still encounter issues, try running:${NC}"
echo -e "${YELLOW}playwright install-deps${NC}"
echo -e "${BLUE}=======================================${NC}"
