#!/usr/bin/env python
import sys
print(f"Python path: {sys.path}")
try:
    import google.generativeai as genai
    print("Google Generative AI module imported successfully!")
except ImportError as e:
    print(f"Error importing Google Generative AI: {e}")
