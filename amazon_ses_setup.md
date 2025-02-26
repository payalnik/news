# Amazon SES Setup Guide for News Updater

This guide provides detailed instructions for setting up Amazon Simple Email Service (SES) with your News Updater application.

## What is Amazon SES?

Amazon SES is a cloud-based email sending service designed to help digital marketers and application developers send marketing, notification, and transactional emails. It's a reliable, cost-effective service that leverages Amazon's robust infrastructure.

## Prerequisites

- An AWS account
- Basic familiarity with AWS console
- Your News Updater application installed and configured

## Step 1: Create an AWS Account

If you don't already have an AWS account:

1. Go to [aws.amazon.com](https://aws.amazon.com/)
2. Click "Create an AWS Account"
3. Follow the signup process
4. You'll need to provide a credit card, but SES has a free tier that includes 62,000 outbound messages per month when sent from an EC2 instance

## Step 2: Set Up Amazon SES

### Verify Email Addresses

When your account is new, it's in the SES sandbox, which means you can only send emails to verified email addresses:

1. Sign in to the AWS Management Console
2. Navigate to the Amazon SES console (search for "SES" in the services search bar)
3. In the navigation pane, under "Identity Management", choose "Email Addresses"
4. Choose "Verify a New Email Address"
5. Enter the email address you want to use as the sender for your News Updater application
6. Click "Verify This Email Address"
7. Check your email inbox for a verification message from AWS
8. Click the verification link in the email

### Verify Recipient Email Addresses (Sandbox Mode Only)

While in sandbox mode, you also need to verify any email addresses you want to send to:

1. In the SES console, under "Identity Management", choose "Email Addresses"
2. Choose "Verify a New Email Address"
3. Enter the recipient email address
4. Click "Verify This Email Address"
5. Have the recipient check their email and click the verification link

### (Optional) Request Production Access

To send emails to non-verified addresses, you need to move out of the sandbox:

1. In the SES console, in the navigation pane, choose "Sending Statistics"
2. Choose "Request a Sending Limit Increase"
3. Fill out the form with your use case details
4. Submit the request

AWS typically reviews these requests within 24-48 hours.

## Step 3: Create SMTP Credentials

Amazon SES uses special SMTP credentials that are different from your regular AWS credentials:

1. In the Amazon SES console, in the navigation pane, choose "SMTP Settings"
2. Choose "Create My SMTP Credentials"
3. Enter a name for your IAM user (e.g., "news-updater-ses-smtp")
4. Choose "Create"
5. Download the credentials CSV file (it contains your SMTP username and password)
6. Store these credentials securely - you won't be able to retrieve the password later

## Step 4: Configure Your News Updater Application

### Update Your .env File

Edit your `.env` file in the project root directory with your Amazon SES credentials:

```
# Amazon SES configuration
EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_verified_email@example.com
EMAIL_HOST_PASSWORD=your_ses_smtp_password_from_csv
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=your_verified_email@example.com
```

The `DEFAULT_FROM_EMAIL` setting allows you to specify a different "From" address for your emails. If not provided, the system will use `EMAIL_HOST_USER` as the sender address. For Amazon SES, both `EMAIL_HOST_USER` (for authentication) and `DEFAULT_FROM_EMAIL` (for the sender address) must be verified in the SES console.

**IMPORTANT**: There are two different sets of credentials you need to understand:

1. **SMTP Authentication Credentials**:
   - The SMTP username (typically starts with "AKIA...") and password from the CSV file
   - These are used for authenticating with the Amazon SES SMTP server
   - The SMTP password is used as `EMAIL_HOST_PASSWORD` in your .env file

2. **Sender Email Address**:
   - This is the verified email address you want to send emails from
   - This email address must be verified in the Amazon SES console
   - This verified email is used as `EMAIL_HOST_USER` in your .env file
   - **DO NOT use the SMTP username (AKIA...) as your EMAIL_HOST_USER**

Common mistake: Using the SMTP username (which starts with "AKIA...") as the EMAIL_HOST_USER. This will cause an "Invalid MAIL FROM address" error.

### Regional Endpoints

If you're using a different AWS region, use the appropriate endpoint:

| Region | SMTP Endpoint |
|--------|---------------|
| US East (N. Virginia) | email-smtp.us-east-1.amazonaws.com |
| US East (Ohio) | email-smtp.us-east-2.amazonaws.com |
| US West (Oregon) | email-smtp.us-west-2.amazonaws.com |
| Europe (Ireland) | email-smtp.eu-west-1.amazonaws.com |
| Europe (Frankfurt) | email-smtp.eu-central-1.amazonaws.com |
| Asia Pacific (Singapore) | email-smtp.ap-southeast-1.amazonaws.com |
| Asia Pacific (Sydney) | email-smtp.ap-southeast-2.amazonaws.com |
| Asia Pacific (Tokyo) | email-smtp.ap-northeast-1.amazonaws.com |

## Step 5: Test Your Configuration

### Using the Test Script

Run the test email script to verify your configuration:

```bash
./test_email_config.py your_verified_email@example.com
```

Remember, if your account is still in the sandbox, you can only send to verified email addresses.

### Using the Django Shell

Alternatively, you can test using the Django shell:

```bash
cd news_updater
python manage.py shell
```

Then in the shell:

```python
from django.core.mail import send_mail
send_mail(
    'Test Email from News Updater via Amazon SES',
    'This is a test email to verify your Amazon SES configuration is working.',
    'your_verified_sender@example.com',
    ['your_verified_recipient@example.com'],
    fail_silently=False,
)
```

## Step 6: Monitor Your Sending Activity

Amazon SES provides detailed metrics and logs for your email sending activity:

1. In the SES console, navigate to "Sending Statistics"
2. Here you can view your sending quota, daily sending statistics, and more
3. You can also set up CloudWatch alarms to monitor your bounce and complaint rates

## Troubleshooting

### Common Issues

1. **"Invalid MAIL FROM address" Error**
   - This happens when you use the SMTP username (AKIA...) as your EMAIL_HOST_USER
   - Fix: Use your verified email address as EMAIL_HOST_USER, not the SMTP username
   - The SMTP username is only used for authentication, not as the sender address

2. **Authentication Failures**
   - Double-check your SMTP username and password
   - Ensure you're using the SMTP credentials, not your regular AWS credentials
   - The SMTP password goes in EMAIL_HOST_PASSWORD

3. **Connection Timeouts**
   - Verify that your firewall allows outbound connections on port 587
   - Try using port 465 with SSL instead of port 587 with TLS

4. **Email Not Delivered**
   - If in sandbox mode, verify both sender and recipient emails
   - Check your sending statistics for bounces or complaints
   - Verify that your sending quota hasn't been exceeded

5. **"Email address is not verified" Error**
   - Ensure both sender and recipient addresses are verified (in sandbox mode)
   - Check the verification status in the SES console

### Checking SES Logs

For more detailed troubleshooting:

1. In the AWS Management Console, navigate to CloudWatch
2. Check the logs for any SES-related errors
3. Set up SNS notifications for bounces and complaints

## Best Practices for Amazon SES

1. **Monitor Your Reputation**
   - Keep bounce and complaint rates below 5%
   - Set up feedback notifications via SNS

2. **Implement SPF and DKIM**
   - If using a custom domain, set up SPF and DKIM for better deliverability

3. **Gradually Increase Sending Volume**
   - Start with low volumes and gradually increase to build a good reputation

4. **Handle Bounces and Complaints**
   - Remove bounced addresses from your recipient list
   - Honor unsubscribe requests promptly

## Additional Resources

- [Amazon SES Developer Guide](https://docs.aws.amazon.com/ses/latest/dg/Welcome.html)
- [Amazon SES SMTP Interface](https://docs.aws.amazon.com/ses/latest/dg/send-email-smtp.html)
- [Amazon SES Best Practices](https://docs.aws.amazon.com/ses/latest/dg/best-practices.html)
