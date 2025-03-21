#!/bin/bash

# Exit on error
set -e

# Update package lists
apt-get update

# Install required packages
apt-get install -y python3 python3-pip python3-venv nginx redis-server supervisor git

# Install browser for web scraping
echo "Which browser would you like to install for web scraping?"
echo "1) Google Chrome"
echo "2) Chromium (open-source version of Chrome)"
read -p "Enter your choice (1 or 2, default: 1): " browser_choice

if [[ "$browser_choice" == "2" ]]; then
    echo "Installing Chromium..."
    apt-get update
    apt-get install -y chromium-browser || apt-get install -y chromium
    echo "Chromium installed successfully!"
else
    echo "Installing Google Chrome..."
    wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
    apt-get update
    apt-get install -y google-chrome-stable
    echo "Google Chrome installed successfully!"
fi

# Create directory for the application
mkdir -p /var/www/news
cd /var/www/news

# Clone the repository
git clone https://github.com/payalnik/news.git .

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install gunicorn

# Create .env file
cat > .env << EOL
# Django settings
SECRET_KEY=your_django_secret_key_heresuo
DEBUG=False

# Email settings
EMAIL_HOST=email-smtp.us-west-1.amazonaws.com
EMAIL_PORT=587
EMAIL_HOST_USER=AKIA4DJXCSWWCBL74HHO
EMAIL_HOST_PASSWORD=BEAJg6U8T3ppzmBOwbEQ0yO6PK7AF4o7S0b7d3DVnZ0q
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=news@alexilin.com

# Google API key for Gemini Flash 2.0
GOOGLE_API_KEY=AIzaSyCJuq7jisYsID3bbAc4sdyMb63RhI2_gcY
EOL

# Update Django settings for production
cd news_updater
sed -i "s/ALLOWED_HOSTS = \['localhost', '127.0.0.1'\]/ALLOWED_HOSTS = \['news.alexilin.com', 'localhost', '127.0.0.1'\]/" news_updater/settings.py

# Create static directory and collect static files
mkdir -p static
python manage.py collectstatic --noinput

# Run migrations
python manage.py migrate

# Create superuser (non-interactive)
echo "from django.contrib.auth.models import User; User.objects.create_superuser('admin', 'admin@example.com', 'admin')" | python manage.py shell

# Set up periodic tasks
python manage.py setup_periodic_tasks

# Configure Nginx
cat > /etc/nginx/sites-available/news << EOL
server {
    listen 80;
    server_name news.alexilin.com;

    location = /favicon.ico { access_log off; log_not_found off; }
    
    location /static/ {
        root /var/www/news/news_updater;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/news/news.sock;
    }
}
EOL

# Create proxy_params file if it doesn't exist
if [ ! -f /etc/nginx/proxy_params ]; then
    cat > /etc/nginx/proxy_params << EOL
proxy_set_header Host \$http_host;
proxy_set_header X-Real-IP \$remote_addr;
proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto \$scheme;
EOL
fi

# Enable the site
ln -sf /etc/nginx/sites-available/news /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Configure Supervisor for Gunicorn
cat > /etc/supervisor/conf.d/news_gunicorn.conf << EOL
[program:news_gunicorn]
directory=/var/www/news/news_updater
command=/var/www/news/venv/bin/gunicorn --workers 3 --bind unix:/var/www/news/news.sock news_updater.wsgi:application
autostart=true
autorestart=true
stderr_logfile=/var/log/news_gunicorn.err.log
stdout_logfile=/var/log/news_gunicorn.out.log
user=root
group=www-data
environment=LANG=en_US.UTF-8,LC_ALL=en_US.UTF-8
EOL

# Configure Supervisor for Celery worker
cat > /etc/supervisor/conf.d/news_celery_worker.conf << EOL
[program:news_celery_worker]
directory=/var/www/news/news_updater
command=/var/www/news/venv/bin/celery -A news_updater worker -l info
autostart=true
autorestart=true
stderr_logfile=/var/log/news_celery_worker.err.log
stdout_logfile=/var/log/news_celery_worker.out.log
user=root
group=www-data
environment=LANG=en_US.UTF-8,LC_ALL=en_US.UTF-8
EOL

# Configure Supervisor for Celery beat
cat > /etc/supervisor/conf.d/news_celery_beat.conf << EOL
[program:news_celery_beat]
directory=/var/www/news/news_updater
command=/var/www/news/venv/bin/celery -A news_updater beat -l info
autostart=true
autorestart=true
stderr_logfile=/var/log/news_celery_beat.err.log
stdout_logfile=/var/log/news_celery_beat.out.log
user=root
group=www-data
environment=LANG=en_US.UTF-8,LC_ALL=en_US.UTF-8
EOL

# Reload supervisor
supervisorctl reread
supervisorctl update

# Test Nginx configuration
nginx -t

# Restart Nginx
systemctl restart nginx

# Open firewall for HTTP and HTTPS
ufw allow 'Nginx Full'

echo "Setup completed successfully!"
echo "You can now access the application at http://news.alexilin.com"
echo "Admin credentials: username=admin, password=admin"
