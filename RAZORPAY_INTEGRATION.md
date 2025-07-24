# Razorpay Payment Integration

This document provides comprehensive information about the Razorpay payment integration implemented for the WelthWest subscription system.

## Overview

The Razorpay integration enables secure payment processing for subscription upgrades with the following features:

- **Complete Payment Flow**: Order creation → Payment → Verification → Subscription activation
- **Webhook Support**: Real-time payment status updates
- **Security**: Signature verification for all payment transactions
- **Error Handling**: Comprehensive error handling and retry mechanisms
- **Payment History**: Complete transaction tracking and history
- **Billing Management**: User billing details storage and management

## Architecture

### Components

1. **RazorpayPaymentService** (`services/razorpay_service.py`)
   - Core payment processing logic
   - Order creation and management
   - Payment verification
   - Webhook handling
   - Payment history tracking

2. **Payment API Endpoints** (`app.py`)
   - `/api/payment/create-order` - Create payment orders
   - `/api/payment/verify` - Verify payment signatures
   - `/api/payment/status/<order_id>` - Get payment status
   - `/api/payment/cancel/<order_id>` - Cancel payments
   - `/api/payment/history` - Get payment history
   - `/api/payment/webhook` - Handle Razorpay webhooks
   - `/api/payment/plans` - Get subscription plans
   - `/api/user/billing-details` - Manage billing details

3. **Database Collections**
   - `payments` - Payment transaction records
   - `orders` - Payment order records
   - `users` - User and subscription data

## Configuration

### Environment Variables

Add the following to your `.env` file:

```bash
# Razorpay Configuration
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_key_secret
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret
RAZORPAY_ENVIRONMENT=test
RAZORPAY_CURRENCY=INR
```

### Subscription Tiers & Pricing

- **FREE**: ₹0 (2 backtests/day, 5 LLM queries/day)
- **BASIC**: ₹399/month (10 backtests/day, 20 LLM queries/day)
- **PRO**: ₹999/month (30 backtests/day, 50 LLM queries/day)
- **ENTERPRISE**: ₹2999/month (unlimited usage)

## Payment Flow

### 1. Order Creation

```javascript
POST /api/payment/create-order
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "plan_tier": "BASIC",
  "billing_details": {
    "full_name": "John Doe",
    "email": "john@example.com",
    "phone": "+919876543210",
    "address": {
      "street": "123 Main St",
      "city": "Mumbai",
      "state": "Maharashtra",
      "country": "India",
      "pincode": "400001"
    }
  }
}
```

**Response:**
```javascript
{
  "success": true,
  "order_id": "order_xxx",
  "amount": 39900,
  "currency": "INR",
  "key_id": "rzp_test_xxx",
  "name": "WelthWest",
  "description": "BASIC Subscription Plan",
  "prefill": {
    "name": "John Doe",
    "email": "john@example.com",
    "contact": "+919876543210"
  },
  "theme": {
    "color": "#3399cc"
  },
  "expires_at": 1640995200
}
```

### 2. Frontend Payment Processing

Use the Razorpay Checkout integration:

```javascript
const options = {
  key: response.key_id,
  amount: response.amount,
  currency: response.currency,
  name: response.name,
  description: response.description,
  order_id: response.order_id,
  prefill: response.prefill,
  theme: response.theme,
  handler: function(razorpayResponse) {
    // Send payment verification to backend
    verifyPayment(razorpayResponse);
  }
};

const rzp = new Razorpay(options);
rzp.open();
```

### 3. Payment Verification

```javascript
POST /api/payment/verify
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "razorpay_payment_id": "pay_xxx",
  "razorpay_order_id": "order_xxx",
  "razorpay_signature": "signature_xxx"
}
```

**Response:**
```javascript
{
  "success": true,
  "payment_id": "pay_xxx",
  "order_id": "order_xxx",
  "amount": 399,
  "currency": "INR",
  "status": "captured",
  "method": "card",
  "subscription_activated": true
}
```

## Webhook Configuration

### Setup Webhook URL

In your Razorpay Dashboard:
1. Go to Settings → Webhooks
2. Add webhook URL: `https://yourdomain.com/api/payment/webhook`
3. Select events: `payment.captured`, `payment.failed`, `order.paid`
4. Set webhook secret in environment variables

### Supported Events

- **payment.captured**: Payment successfully captured
- **payment.failed**: Payment failed
- **order.paid**: Order marked as paid

## API Endpoints

### Payment Endpoints

#### Create Payment Order
- **URL**: `POST /api/payment/create-order`
- **Auth**: Required (JWT)
- **Purpose**: Create a new payment order for subscription upgrade

#### Verify Payment
- **URL**: `POST /api/payment/verify`
- **Auth**: Required (JWT)
- **Purpose**: Verify payment signature and activate subscription

#### Get Payment Status
- **URL**: `GET /api/payment/status/<order_id>`
- **Auth**: Required (JWT)
- **Purpose**: Get current payment status

#### Cancel Payment
- **URL**: `POST /api/payment/cancel/<order_id>`
- **Auth**: Required (JWT)
- **Purpose**: Cancel a pending payment order

#### Payment History
- **URL**: `GET /api/payment/history?limit=20&skip=0`
- **Auth**: Required (JWT)
- **Purpose**: Get user's payment history with pagination

#### Payment Webhook
- **URL**: `POST /api/payment/webhook`
- **Auth**: None (verified via signature)
- **Purpose**: Handle Razorpay webhook events

#### Get Plans
- **URL**: `GET /api/payment/plans`
- **Auth**: None
- **Purpose**: Get available subscription plans with pricing

### Billing Endpoints

#### Get Billing Details
- **URL**: `GET /api/user/billing-details`
- **Auth**: Required (JWT)
- **Purpose**: Get user's stored billing information

#### Update Billing Details
- **URL**: `POST|PUT /api/user/billing-details`
- **Auth**: Required (JWT)
- **Purpose**: Update user's billing information

## Security Features

### Payment Signature Verification

All payments are verified using HMAC-SHA256 signature:

```python
def verify_payment_signature(razorpay_payment_id, razorpay_order_id, razorpay_signature):
    payload = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, razorpay_signature)
```

### Webhook Signature Verification

Webhooks are verified to ensure they're from Razorpay:

```python
def verify_webhook_signature(payload, signature):
    expected_signature = hmac.new(
        WEBHOOK_SECRET.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)
```

## Database Schema

### Payments Collection

```javascript
{
  _id: ObjectId,
  user_id: ObjectId,
  razorpay_order_id: String,
  razorpay_payment_id: String,
  razorpay_signature: String,
  amount: Number, // in rupees
  currency: String,
  plan_tier: String,
  billing_details: {
    full_name: String,
    email: String,
    phone: String,
    address: {
      street: String,
      city: String,
      state: String,
      country: String,
      pincode: String
    }
  },
  payment_status: String, // created, attempted, paid, failed, cancelled
  razorpay_response: Object,
  created_at: Date,
  updated_at: Date,
  expires_at: Date
}
```

### Orders Collection

```javascript
{
  _id: ObjectId,
  user_id: ObjectId,
  razorpay_order_id: String,
  plan_tier: String,
  amount: Number, // in rupees
  currency: String,
  status: String, // created, paid, expired, cancelled
  billing_details: Object,
  created_at: Date,
  expires_at: Date
}
```

## Error Handling

### Common Error Scenarios

1. **Invalid Plan Tier**
   - Status: 400
   - Message: "Invalid plan tier"

2. **Missing Billing Details**
   - Status: 400
   - Message: "Missing billing field: <field_name>"

3. **Payment Verification Failed**
   - Status: 400
   - Message: "Payment verification failed"

4. **Order Not Found**
   - Status: 404
   - Message: "Payment record not found"

5. **Subscription Activation Failed**
   - Status: 500
   - Message: "Subscription activation failed"

### Retry Mechanisms

- **Payment Creation**: Automatic retry on network failures
- **Webhook Processing**: Razorpay automatically retries failed webhooks
- **Subscription Activation**: Manual retry available via admin endpoints

## Testing

### Test Script

Run the comprehensive test suite:

```bash
python test_payment_integration.py
```

The test script covers:
- User registration
- Payment plan retrieval
- Billing details management
- Payment order creation
- Payment status checking
- Payment cancellation
- Payment history
- Subscription endpoints

### Test Credentials

For testing in Razorpay test mode:
- Use test API keys from Razorpay Dashboard
- Use test card numbers provided by Razorpay
- Webhooks can be tested using ngrok for local development

## Deployment Considerations

### Environment Setup

1. **Production vs Test Environment**
   - Use `RAZORPAY_ENVIRONMENT=live` for production
   - Use live API keys for production
   - Configure production webhook URLs

2. **SSL Certificate**
   - Ensure HTTPS is enabled for webhook endpoints
   - Razorpay requires SSL for production webhooks

3. **Database Indexes**
   - Indexes are automatically created by the service
   - Monitor query performance in production

### Monitoring

1. **Payment Success Rate**
   - Monitor failed payments
   - Set up alerts for payment failures

2. **Webhook Processing**
   - Monitor webhook delivery success
   - Log all webhook events for auditing

3. **Subscription Activations**
   - Monitor subscription upgrade success rates
   - Alert on activation failures

## Troubleshooting

### Common Issues

1. **Webhook Not Received**
   - Check webhook URL configuration
   - Verify SSL certificate
   - Check firewall settings

2. **Payment Verification Failed**
   - Verify API keys are correct
   - Check signature calculation
   - Ensure order exists in database

3. **Subscription Not Activated**
   - Check payment verification logs
   - Verify subscription service is working
   - Check user permissions

### Debug Mode

Enable debug logging by setting:
```bash
LOG_LEVEL=DEBUG
```

This will provide detailed logs for:
- Payment processing steps
- Webhook events
- Database operations
- API calls

## Security Best Practices

1. **Never Log Sensitive Data**
   - API keys and secrets are never logged
   - Payment details are sanitized in logs

2. **Signature Verification**
   - All payments verified before processing
   - Webhooks verified before processing

3. **Database Security**
   - Payment data encrypted at rest
   - Sensitive fields properly indexed

4. **Rate Limiting**
   - Payment endpoints have rate limits
   - Webhook endpoints protected against abuse

## Support

For issues related to:
- **Razorpay Integration**: Check Razorpay documentation and support
- **Backend Implementation**: Review service logs and error messages
- **Database Issues**: Check MongoDB connection and indexes
- **Webhook Problems**: Verify webhook configuration and SSL setup