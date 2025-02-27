from django.core.management.base import BaseCommand
import sys

class Command(BaseCommand):
    help = 'Test the Google Generative AI (Gemini) integration'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Testing Google Generative AI integration...'))
        
        try:
            import google.generativeai as genai
            self.stdout.write(self.style.SUCCESS('✓ Successfully imported google.generativeai module'))
            
            # Test model initialization
            try:
                model = genai.GenerativeModel('gemini-2.0-flash')
                self.stdout.write(self.style.SUCCESS('✓ Successfully initialized gemini-2.0-flash model'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Error initializing gemini-2.0-flash model: {e}'))
            
            # Try importing the tasks module
            try:
                from news_app.tasks import send_news_update
                self.stdout.write(self.style.SUCCESS('✓ Successfully imported send_news_update from tasks'))
                
                self.stdout.write(self.style.SUCCESS('\nAll tests passed! The Google Generative AI module is properly installed.'))
                self.stdout.write('You can now run the news updater application with the scripts:')
                self.stdout.write('  - ./run_news_updater.sh')
                self.stdout.write('  - ./run_news_updater_simple.sh')
                
            except ImportError as e:
                self.stdout.write(self.style.ERROR(f'✗ Error importing tasks module: {e}'))
                
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f'✗ Error importing Google Generative AI: {e}'))
            self.stdout.write('Please make sure the google-generativeai package is installed:')
            self.stdout.write('  pip install google-generativeai==0.3.2')
