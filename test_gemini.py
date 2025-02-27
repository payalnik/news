#!/usr/bin/env python
# This script should be run with the virtual environment activated:
# source venv/bin/activate && python test_gemini.py
import os
import sys
from pathlib import Path

# Add the project directory to the Python path
current_dir = Path(__file__).resolve().parent
news_updater_dir = current_dir / 'news_updater'
sys.path.append(str(news_updater_dir))

try:
    import google.generativeai as genai
    print("Google Generative AI module imported successfully!")
    
    # Try to import the tasks module without Django setup
    try:
        from news_app.tasks import send_news_update
        print("Tasks module imported successfully!")
    except ImportError as e:
        print(f"Could not import tasks module (expected without Django setup): {e}")
        print("This is normal if Django is not set up.")
    
    print("\nTest completed successfully. The Google Generative AI module is now properly installed.")
    print("You can now run the news updater application with the scripts:")
    print("  - ./run_news_updater.sh")
    print("  - ./run_news_updater_simple.sh")
    
except ImportError as e:
    print(f"Error importing Google Generative AI: {e}")
    print("Please make sure the google-generativeai package is installed.")
    print("You can install it with: pip install google-generativeai")
