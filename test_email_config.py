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

# Import Django email functionality
from django.core.mail import send_mail
from django.conf import settings

def test_email(recipient=None):
    """
    Send a test email to verify email configuration.
    
    Args:
        recipient: Email address to send the test to. If None, uses the sender address.
    """
    if not recipient:
        # If no recipient specified, use the sender address (which should be verified)
        recipient = settings.DEFAULT_FROM_EMAIL
    
    print(f"Sending test email to: {recipient}")
    print(f"Using email configuration:")
    print(f"  EMAIL_HOST: {settings.EMAIL_HOST}")
    print(f"  EMAIL_PORT: {settings.EMAIL_PORT}")
    print(f"  EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
    print(f"  EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
    print(f"  DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
    
    try:
        send_mail(
            subject='Test Email from News Updater',
            message='This is a test email to verify your email configuration is working correctly.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        print("Test email sent successfully!")
        return True
    except Exception as e:
        print(f"Error sending test email: {str(e)}")
        return False

if __name__ == "__main__":
    # Get recipient from command line argument if provided
    recipient = sys.argv[1] if len(sys.argv) > 1 else None
    test_email(recipient)
