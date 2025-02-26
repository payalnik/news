# News Updater Startup Scripts

This directory contains several scripts to help you run the News Updater application with all its required services (Django server, Celery worker, and Celery beat) in a single terminal window.

## Prerequisites

- Python with Django installed
- Redis server (for Celery)
- A properly configured `.env` file with email settings

## Available Scripts

### 1. `run_news_updater.sh` (Recommended for tmux users)

This script uses `tmux` to run all services in a single terminal window with split panes.

**Requirements:**
- tmux (`brew install tmux` on macOS, `apt-get install tmux` on Ubuntu/Debian)

**Features:**
- Runs Django server, Celery worker, and Celery beat in separate panes
- Allows easy navigation between services
- Checks for Redis and virtual environment
- Automatically starts Redis if needed

**Usage:**
```bash
./run_news_updater.sh
```

**Tmux Controls:**
- Switch between panes: `Ctrl+B`, then arrow keys
- Detach from session: `Ctrl+B`, then `D`
- Reattach to session: `tmux attach-session -t news_updater`
- Scroll in a pane: `Ctrl+B`, then `[` (use arrow keys to scroll, press `q` to exit scroll mode)

### 2. `run_news_updater_simple.sh` (Alternative)

This script uses `screen` if available, or runs services in the background if not.

**Requirements:**
- None (works with `screen` if available, but can run without it)

**Features:**
- Runs Django server, Celery worker, and Celery beat in separate screen sessions or background processes
- Logs output to files if running in background
- Checks for Redis and virtual environment
- Automatically starts Redis if needed

**Usage:**
```bash
./run_news_updater_simple.sh
```

### 3. `run_news_updater_parallel.sh` (For GNU Parallel users)

This script uses GNU Parallel to run all services in a single terminal with labeled output.

**Requirements:**
- GNU Parallel (`brew install parallel` on macOS, `apt-get install parallel` on Ubuntu/Debian)

**Features:**
- Runs all services in the foreground in a single terminal
- Labels each line of output with the service name
- Checks for Redis and virtual environment
- Automatically starts Redis if needed

**Usage:**
```bash
./run_news_updater_parallel.sh
```

### 4. `run_news_updater_basic.sh` (Simplest, no dependencies)

This script uses basic bash features to run all services in a single terminal with labeled output.

**Requirements:**
- None (uses only standard bash features)

**Features:**
- Runs all services in the foreground in a single terminal
- Labels each line of output with the service name
- Logs output to files for reference
- Checks for Redis and virtual environment
- Automatically starts Redis if needed
- Handles clean shutdown with Ctrl+C

**Usage:**
```bash
./run_news_updater_basic.sh
```

## Choosing the Right Script

1. If you have `tmux` installed or are willing to install it, use `run_news_updater.sh` for the best experience.
2. If you prefer a simpler approach or don't want to install additional tools, use `run_news_updater_simple.sh`.
3. If you want the simplest possible approach with no dependencies, use `run_news_updater_basic.sh`.
4. If you have GNU Parallel installed, you can also try `run_news_updater_parallel.sh`.

## Troubleshooting

If you encounter any issues:

1. Make sure Redis is installed and running
2. Verify that your `.env` file is properly configured
3. Ensure you have activated your virtual environment
4. Check that all required Python packages are installed

For more detailed setup instructions, refer to the main `README.md` file.
