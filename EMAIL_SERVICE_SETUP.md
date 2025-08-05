# Email Service Setup and Configuration

## Overview
The WealthWest email service provides automated email notifications for payment confirmations, subscription upgrades, and general communication. It uses Flask-Mail with customizable HTML templates.

## Environment Variables Required

Add these environment variables to your `.env` file or deployment configuration:

```env
# Email Configuration
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USE_SSL=false
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
SUPPORT_EMAIL=support@wealthwest.com
```

## Gmail Setup (Recommended)

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate App Password:**
   - Go to Gmail Settings → Security
   - Generate App Password for "Mail"
   - Use this password in `MAIL_PASSWORD` environment variable

## Features Implemented

### 1. Fixed Infinite API Calls Issue
- **Problem:** `/api/user/subscription` was being called infinitely due to improper useEffect dependencies and refresh loops
- **Solution:** 
  - Optimized `SubscriptionContext.tsx` useEffect dependencies
  - Implemented local state updates in increment functions to prevent unnecessary API calls
  - Added proper CORS configuration with OPTIONS method support

### 2. Payment Confirmation Emails
- **Trigger:** Automatically sent after successful payment verification
- **Content:** Invoice details, plan features, payment confirmation
- **Template:** Professional HTML template with plan details and invoice

### 3. Subscription Upgrade Emails
- **Trigger:** When user upgrades subscription tier
- **Content:** Old vs new plan comparison, upgrade date
- **Template:** Clean upgrade notification template

### 4. Welcome Emails
- **Trigger:** Can be sent manually or automated for new users
- **Content:** Welcome message, platform features, support contact

## API Endpoints

### 1. Send Custom Email (Admin Only)
```http
POST /api/email/send
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "to": "user@example.com",
  "subject": "Custom Subject",
  "template": "<html>Custom HTML template with {{variables}}</html>",
  "context": {
    "variables": "values"
  },
  "attachments": [
    {
      "filename": "document.pdf",
      "content_type": "application/pdf",
      "data": "base64_encoded_data"
    }
  ]
}
```

### 2. Send Welcome Email
```http
POST /api/email/send-welcome
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "user_id": "optional_target_user_id"
}
```

### 3. Send Subscription Upgrade Email
```http
POST /api/email/send-subscription-upgrade
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "old_plan": "BASIC",
  "new_plan": "PRO"
}
```

## Automatic Email Triggers

### Payment Confirmation
- **When:** After successful payment verification in `RazorpayPaymentService.verify_payment_signature()`
- **Recipients:** User who made the payment
- **Content:** 
  - Invoice details (invoice number, amount, payment ID)
  - Plan features
  - Thank you message
  - Support contact

### Subscription Upgrade
- **When:** After successful subscription upgrade
- **Recipients:** User who upgraded
- **Content:**
  - Previous and new plan details
  - Upgrade date
  - Feature changes

## Template Customization

Email templates are defined in `services/email_service.py`. Key templates:

1. **`_get_payment_confirmation_template()`** - Payment success email
2. **`_get_subscription_upgrade_template()`** - Plan upgrade notification
3. **`_get_welcome_template()`** - Welcome email for new users

### Template Variables Available:

#### Payment Confirmation:
- `user_name`: User's display name
- `plan_name`: Subscription plan name
- `plan_price`: Plan price in currency
- `billing_cycle`: monthly/annual
- `payment_id`: Razorpay payment ID
- `order_id`: Razorpay order ID
- `payment_date`: Formatted payment date
- `invoice_data`: Complete invoice details
- `features`: List of plan features

#### Subscription Upgrade:
- `user_name`: User's display name
- `old_plan`: Previous plan name
- `new_plan`: New plan name
- `upgrade_date`: Formatted upgrade date

#### Welcome Email:
- `user_name`: User's display name
- `support_email`: Support contact email

## Error Handling

- Email failures don't break payment processing
- All email errors are logged with detailed information
- Failed emails return appropriate HTTP status codes
- Email service gracefully handles missing configuration

## Testing

### Development Testing:
1. Use a test Gmail account
2. Set up App Password
3. Test with `/api/email/send-welcome` endpoint
4. Check server logs for email sending status

### Email Templates Testing:
1. Use the custom email endpoint with admin access
2. Test different template variables
3. Verify HTML rendering in email clients

## Security Considerations

1. **Admin-only endpoints:** Custom email sending restricted to admin users
2. **Environment variables:** Sensitive email credentials stored in environment variables
3. **Template injection:** Templates use Jinja2 with proper escaping
4. **Rate limiting:** Consider implementing rate limiting for email endpoints
5. **Email validation:** Recipient email addresses are validated

## Troubleshooting

### Common Issues:

1. **"Authentication failed"**
   - Check Gmail App Password
   - Verify 2FA is enabled
   - Ensure correct username/password

2. **"Connection refused"**
   - Check MAIL_SERVER and MAIL_PORT
   - Verify TLS/SSL settings
   - Check firewall/network restrictions

3. **"Template errors"**
   - Verify template syntax
   - Check template variables
   - Review Jinja2 template format

4. **"Email not received"**
   - Check spam folder
   - Verify recipient email address
   - Check server logs for sending status

### Debug Mode:
Enable Flask debug mode to see detailed email error messages:
```python
app.config['DEBUG'] = True
```

## Plan Features Mapping

The email service includes predefined features for each subscription tier:

- **FREE:** Basic analysis, 3 backtests/day, 10 AI queries/day, delayed data
- **BASIC:** Advanced analysis, 25 backtests/day, 50 AI queries/day, real-time data
- **PRO:** Premium analysis, 100 backtests/day, 200 AI queries/day, portfolio management
- **ENTERPRISE:** Enterprise features, unlimited usage, API access, dedicated support