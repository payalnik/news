# Email Setup Guide for News Updater

This guide will help you set up your local environment to send emails from your machine using the News Updater application.

## Setting Up Gmail SMTP

The application is pre-configured to use Gmail's SMTP server. Follow these steps to set it up:

### 1. Update Your `.env` File

Edit your `.env` file in the project root directory with your Gmail credentials:

```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_actual_gmail@gmail.com
EMAIL_HOST_PASSWORD=your_app_password_here
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=your_display_name@gmail.com
```

Note: The `DEFAULT_FROM_EMAIL` setting allows you to specify a different "From" address for your emails. If not provided, the system will use `EMAIL_HOST_USER` as the sender address.

### 2. Generate an App Password for Gmail

Gmail requires an "App Password" for SMTP access when you have 2-Factor Authentication enabled (recommended):

1. Go to your [Google Account](https://myaccount.google.com/)
2. Select "Security" from the left menu
3. Under "Signing in to Google," select "2-Step Verification" (enable it if not already enabled)
4. Scroll down and select "App passwords"
5. Select "Mail" as the app and "Other" as the device (name it "Django News Updater")
6. Click "Generate"
7. Copy the 16-character password that appears
8. Paste this password in your `.env` file as the `EMAIL_HOST_PASSWORD` value

### 3. Allow Less Secure Apps (Alternative if not using App Passwords)

If you don't want to use 2-Factor Authentication and App Passwords (not recommended):

1. Go to your [Google Account](https://myaccount.google.com/)
2. Select "Security" from the left menu
3. Scroll down to "Less secure app access" and turn it on
4. Use your regular Gmail password in the `.env` file

## Alternative Email Providers

If you prefer not to use Gmail, you can configure other email providers:

### Amazon SES (Simple Email Service)

Amazon SES is a reliable, cost-effective email service built on the reliable infrastructure of Amazon.com.

#### 1. Set Up an AWS Account

If you don't already have an AWS account, sign up at [aws.amazon.com](https://aws.amazon.com/).

#### 2. Verify Email Addresses or Domains

Before you can send emails with Amazon SES, you need to verify your email addresses or domains:

1. Go to the [Amazon SES console](https://console.aws.amazon.com/ses/)
2. In the navigation pane, under "Identity Management", choose "Email Addresses" or "Domains"
3. Choose "Verify a New Email Address" or "Verify a New Domain"
4. Follow the verification process

Note: If your account is in the SES sandbox, you can only send emails to verified email addresses.

#### 3. Create SMTP Credentials

Amazon SES uses special SMTP credentials that are different from your regular AWS credentials:

1. In the Amazon SES console, in the navigation pane, choose "SMTP Settings"
2. Choose "Create My SMTP Credentials"
3. Enter a name for your IAM user and choose "Create"
4. Download the credentials (SMTP username and password)

#### 4. Configure Your .env File

Update your `.env` file with the Amazon SES SMTP settings:

```
EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_ses_smtp_username
EMAIL_HOST_PASSWORD=your_ses_smtp_password
EMAIL_USE_TLS=True
```

Replace `us-east-1` with your AWS region if different.

### Outlook/Hotmail

```
EMAIL_HOST=smtp-mail.outlook.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_outlook_email@outlook.com
EMAIL_HOST_PASSWORD=your_password
EMAIL_USE_TLS=True
```

### Yahoo Mail

```
EMAIL_HOST=smtp.mail.yahoo.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_yahoo_email@yahoo.com
EMAIL_HOST_PASSWORD=your_password
EMAIL_USE_TLS=True
```

### SendGrid

```
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=your_sendgrid_api_key
EMAIL_USE_TLS=True
```

## Testing Email Functionality

After configuring your email settings, you can test if emails are being sent correctly:

1. Start the Django development server:
   ```
   cd news_updater
   python manage.py runserver
   ```

2. Register a new user account with your email address
3. Verify that you receive the verification email
4. Alternatively, you can use the Django shell to send a test email:
   ```
   cd news_updater
   python manage.py shell
   ```
   
   Then in the shell:
   ```python
   from django.core.mail import send_mail
   send_mail(
       'Test Email from News Updater',
       'This is a test email to verify your SMTP configuration is working.',
       'your_configured_email@example.com',
       ['recipient_email@example.com'],
       fail_silently=False,
   )
   ```

## Troubleshooting

### Email Not Sending

1. Check your `.env` file for correct credentials
2. Verify that your email provider allows SMTP access
3. Check if your email provider requires specific security settings
4. Look for error messages in the Django console

### Gmail Specific Issues

1. Make sure you've generated an App Password correctly
2. Check if you need to allow less secure apps
3. Verify that your Gmail account doesn't have any security blocks

### Connection Errors

1. Check your internet connection
2. Verify that the SMTP port (587) is not blocked by your firewall
3. Try using a different port (465) with `EMAIL_USE_SSL=True` instead of `EMAIL_USE_TLS=True`

## Local SMTP Server for Development

If you don't want to use a real email service during development, you can use Django's built-in console email backend:

1. In your `.env` file, set:
   ```
   EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
   ```

This will output emails to the console instead of actually sending them.

Alternatively, you can use a local SMTP debugging server like [MailHog](https://github.com/mailhog/MailHog):

1. Install MailHog
2. Run MailHog
3. Configure your `.env` file:
   ```
   EMAIL_HOST=localhost
   EMAIL_PORT=1025
   EMAIL_HOST_USER=
   EMAIL_HOST_PASSWORD=
   EMAIL_USE_TLS=False
   ```

## Redis Setup for Celery

The News Updater application uses Celery for task scheduling, which requires Redis:

1. Install Redis:
   - macOS: `brew install redis`
   - Linux: `sudo apt-get install redis-server`
   - Windows: Download from [Redis for Windows](https://github.com/tporadowski/redis/releases)

2. Start Redis:
   - macOS/Linux: `redis-server`
   - Windows: Run the Redis server executable

3. Verify Redis is running:
   ```
   redis-cli ping
   ```
   Should return `PONG`

4. Start Celery worker and beat (as mentioned in the README)
