#!/usr/bin/env python
import os
import sys
import django
from pathlib import Path

# Add the project directory to the Python path
current_dir = Path(__file__).resolve().parent
news_updater_dir = current_dir / 'news_updater'
sys.path.append(str(news_updater_dir))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'news_updater.settings')
django.setup()

# Try importing the tasks module
try:
    from news_app.tasks import send_news_update
    print("Tasks module imported successfully!")
    print("Google Generative AI module is working!")
except ImportError as e:
    print(f"Error importing tasks module: {e}")
except Exception as e:
    print(f"Other error: {e}")
