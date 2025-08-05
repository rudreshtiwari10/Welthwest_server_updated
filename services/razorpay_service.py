import razorpay
import hmac
import hashlib
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from bson.objectid import ObjectId
from pymongo import MongoClient, ASCENDING
from config import get_config

logger = logging.getLogger(__name__)

class RazorpayPaymentService:
    """Service for handling Razorpay payment integration"""
    
    def __init__(self):
        self.config = get_config()
        self.db = MongoClient(self.config.MONGODB_URI)[self.config.DB_NAME]
        
        # Initialize collections
        self.payments = self.db.payments
        self.orders = self.db.orders
        self.users = self.db.users
        
        # Create indexes for performance
        self._create_indexes()
        
        # Initialize Razorpay client
        self.client = razorpay.Client(auth=(
            self.config.RAZORPAY_KEY_ID, 
            self.config.RAZORPAY_KEY_SECRET
        ))
        
        self.webhook_secret = self.config.RAZORPAY_WEBHOOK_SECRET
        self.currency = self.config.RAZORPAY_CURRENCY
        
        # Plan pricing mapping
        self.plan_prices = {
            'BASIC': 39900,    # ₹399 in paise
            'PRO': 99900,      # ₹999 in paise  
            'ENTERPRISE': 299900  # ₹2999 in paise
        }
        
    def _create_indexes(self):
        """Create database indexes for performance"""
        try:
            # Payments collection indexes
            self.payments.create_index([("user_id", ASCENDING)])
            self.payments.create_index([("razorpay_order_id", ASCENDING)], unique=True)
            self.payments.create_index([("razorpay_payment_id", ASCENDING)])
            self.payments.create_index([("payment_status", ASCENDING)])
            self.payments.create_index([("created_at", ASCENDING)])
            
            # Orders collection indexes
            self.orders.create_index([("user_id", ASCENDING)])
            self.orders.create_index([("razorpay_order_id", ASCENDING)], unique=True)
            self.orders.create_index([("status", ASCENDING)])
            self.orders.create_index([("expires_at", ASCENDING)])
            
            logger.info("Payment service indexes created successfully")
        except Exception as e:
            logger.error(f"Error creating payment indexes: {str(e)}")
    
    def create_payment_order(self, user_id: str, plan_tier: str, billing_details: dict) -> Dict[str, Any]:
        """Create a new payment order for subscription upgrade"""
        try:
            # Validate plan tier
            if plan_tier not in self.plan_prices:
                return {
                    "success": False,
                    "error": "Invalid plan tier",
                    "message": f"Plan {plan_tier} is not available"
                }
            
            # Validate billing details
            required_fields = ['full_name', 'email', 'phone']
            missing_fields = [field for field in required_fields if field not in billing_details]
            if missing_fields:
                return {
                    "success": False,
                    "error": "Missing billing information",
                    "message": f"Required fields missing: {', '.join(missing_fields)}"
                }
            
            # Get user data
            user = self.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return {
                    "success": False,
                    "error": "User not found",
                    "message": "Invalid user ID"
                }
            
            amount = self.plan_prices[plan_tier]
            
            # Create Razorpay order
            order_data = {
                "amount": amount,
                "currency": self.currency,
                "notes": {
                    "user_id": user_id,
                    "plan_tier": plan_tier,
                    "user_email": billing_details['email'],
                    "user_name": billing_details['full_name']
                }
            }
            
            razorpay_order = self.client.order.create(order_data)
            
            # Calculate expiry time (30 minutes from now)
            expires_at = datetime.utcnow() + timedelta(minutes=30)
            
            # Store order in database
            order_doc = {
                "user_id": ObjectId(user_id),
                "razorpay_order_id": razorpay_order['id'],
                "plan_tier": plan_tier,
                "amount": amount / 100,  # Store in rupees
                "currency": self.currency,
                "status": "created",
                "billing_details": billing_details,
                "created_at": datetime.utcnow(),
                "expires_at": expires_at
            }
            
            order_result = self.orders.insert_one(order_doc)
            
            # Create initial payment record
            payment_doc = {
                "user_id": ObjectId(user_id),
                "razorpay_order_id": razorpay_order['id'],
                "razorpay_payment_id": None,
                "razorpay_signature": None,
                "amount": amount / 100,  # Store in rupees
                "currency": self.currency,
                "plan_tier": plan_tier,
                "billing_details": billing_details,
                "payment_status": "created",
                "razorpay_response": {},
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "expires_at": expires_at
            }
            
            payment_result = self.payments.insert_one(payment_doc)
            
            logger.info(f"Created payment order for user {user_id}, plan {plan_tier}, amount ₹{amount/100}")
            
            return {
                "success": True,
                "order_id": razorpay_order['id'],
                "amount": amount,
                "currency": self.currency,
                "key_id": self.config.RAZORPAY_KEY_ID,
                "name": "WelthWest",
                "description": f"{plan_tier} Subscription Plan",
                "prefill": {
                    "name": billing_details['full_name'],
                    "email": billing_details['email'],
                    "contact": billing_details['phone']
                },
                "theme": {
                    "color": "#3399cc"
                },
                "expires_at": int(expires_at.timestamp())
            }
            
        except Exception as e:
            logger.error(f"Error creating payment order: {str(e)}")
            return {
                "success": False,
                "error": "Payment order creation failed",
                "message": str(e)
            }
    
    def verify_payment_signature(self, razorpay_payment_id: str, razorpay_order_id: str, razorpay_signature: str) -> Dict[str, Any]:
        """Verify payment signature and process successful payment"""
        try:
            logger.info(f"Starting payment verification for order {razorpay_order_id}")
            logger.info(f"Payment ID: {razorpay_payment_id}")
            logger.info(f"Signature provided: {razorpay_signature[:20]}...")  # Log only first 20 chars for security
            
            # Check if Razorpay is properly configured
            if not self.config.RAZORPAY_KEY_ID or not self.config.RAZORPAY_KEY_SECRET:
                logger.error("Razorpay credentials not configured properly")
                return {
                    "success": False,
                    "error": "Configuration error",
                    "message": "Payment gateway not configured properly"
                }
            
            # Check if order exists in database
            order_record = self.orders.find_one({"razorpay_order_id": razorpay_order_id})
            if not order_record:
                logger.error(f"Order {razorpay_order_id} not found in database")
                return {
                    "success": False,
                    "error": "Order not found",
                    "message": "Invalid order ID"
                }
            
            # Use Razorpay's official utility method for signature verification
            params_dict = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            }
            
            logger.info(f"Verifying signature with Key ID: {self.config.RAZORPAY_KEY_ID[:10]}...")
            
            # Handle debug mode case
            if razorpay_signature == 'debug_mode_no_signature':
                logger.warning("Debug mode: Skipping signature verification")
                if not self.config.DEBUG:
                    return {
                        "success": False,
                        "error": "Invalid signature",
                        "message": "Debug signature used in production mode"
                    }
                # In debug mode, we'll skip signature verification
                logger.info("Debug mode: Payment signature verification skipped")
            else:
                try:
                    # Verify signature using Razorpay's official method
                    self.client.utility.verify_payment_signature(params_dict)
                    logger.info(f"Payment signature verified successfully for order {razorpay_order_id}")
                except razorpay.errors.SignatureVerificationError as e:
                    logger.warning(f"Invalid payment signature for order {razorpay_order_id}: {str(e)}")
                    
                    # Additional debugging information
                    expected_payload = f"{razorpay_order_id}|{razorpay_payment_id}"
                    logger.info(f"Expected payload for signature: {expected_payload}")
                    logger.info(f"Received signature length: {len(razorpay_signature)}")
                    logger.info(f"Signature format appears valid: {razorpay_signature.isalnum()}")
                    
                    # Manual signature verification for debugging
                    try:
                        import hmac
                        import hashlib
                        expected_signature = hmac.new(
                            self.config.RAZORPAY_KEY_SECRET.encode('utf-8'),
                            expected_payload.encode('utf-8'),
                            hashlib.sha256
                        ).hexdigest()
                        logger.info(f"Manual signature calculation - Expected: {expected_signature[:20]}...")
                        logger.info(f"Manual signature calculation - Received: {razorpay_signature[:20]}...")
                        logger.info(f"Manual verification result: {expected_signature == razorpay_signature}")
                    except Exception as manual_e:
                        logger.error(f"Manual signature calculation failed: {manual_e}")
                    
                    return {
                        "success": False,
                        "error": "Invalid signature",
                        "message": "Payment verification failed - signature mismatch. Please ensure you're using the correct Razorpay credentials and the payment was made in the correct environment."
                    }
                except Exception as e:
                    logger.error(f"Error during signature verification for order {razorpay_order_id}: {str(e)}")
                    logger.error(f"Exception type: {type(e).__name__}")
                    return {
                        "success": False,
                        "error": "Signature verification error",
                        "message": f"Payment verification failed: {str(e)}"
                    }
            
            # Get payment details from Razorpay
            try:
                payment_details = self.client.payment.fetch(razorpay_payment_id)
            except Exception as e:
                logger.error(f"Error fetching payment details: {str(e)}")
                return {
                    "success": False,
                    "error": "Payment verification failed",
                    "message": "Could not verify payment with Razorpay"
                }
            
            # Update payment record
            payment_update = {
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
                "payment_status": "paid",
                "razorpay_response": payment_details,
                "updated_at": datetime.utcnow()
            }
            
            payment_result = self.payments.update_one(
                {"razorpay_order_id": razorpay_order_id},
                {"$set": payment_update}
            )
            
            if payment_result.modified_count == 0:
                logger.error(f"Payment record not found for order {razorpay_order_id}")
                return {
                    "success": False,
                    "error": "Payment record not found",
                    "message": "Could not update payment status"
                }
            
            # Get payment record to activate subscription
            payment_record = self.payments.find_one({"razorpay_order_id": razorpay_order_id})
            if not payment_record:
                return {
                    "success": False,
                    "error": "Payment record not found",
                    "message": "Could not retrieve payment details"
                }
            
            # Activate subscription
            activation_result = self._activate_subscription(
                str(payment_record['user_id']),
                payment_record['plan_tier']
            )
            
            if not activation_result['success']:
                logger.error(f"Failed to activate subscription for user {payment_record['user_id']}")
                return {
                    "success": False,
                    "error": "Subscription activation failed",
                    "message": activation_result['message']
                }
            
            # Update order status
            self.orders.update_one(
                {"razorpay_order_id": razorpay_order_id},
                {"$set": {"status": "paid"}}
            )
            
            logger.info(f"Payment verified and subscription activated for order {razorpay_order_id}")
            
            # Send payment confirmation email
            try:
                from services.email_service import email_service
                from services.user_service import UserService
                
                user_service = UserService()
                user_data = user_service.get_user_by_id(str(payment_record['user_id']))
                
                if user_data:
                    # Prepare plan details
                    plan_details = {
                        'name': payment_record.get('plan_tier', 'Unknown Plan').title(),
                        'price': payment_record.get('amount', 0) / 100,
                        'billing_cycle': payment_record.get('billing_cycle', 'monthly'),
                        'amount': payment_record.get('amount', 0),
                        'features': self._get_plan_features(payment_record.get('plan_tier'))
                    }
                    
                    # Prepare payment details for email
                    payment_details_email = {
                        'razorpay_payment_id': razorpay_payment_id,
                        'razorpay_order_id': razorpay_order_id
                    }
                    
                    # Send email
                    email_sent = email_service.send_payment_confirmation_email(
                        user_email=user_data['email'],
                        user_name=user_data.get('username', 'User'),
                        plan_details=plan_details,
                        payment_details=payment_details_email
                    )
                    
                    if email_sent:
                        logger.info(f"Payment confirmation email sent to {user_data['email']}")
                    else:
                        logger.warning(f"Failed to send payment confirmation email to {user_data['email']}")
                        
            except Exception as email_error:
                logger.error(f"Error sending payment confirmation email: {str(email_error)}")
                # Don't fail the payment verification if email fails
            
            return {
                "success": True,
                "payment_id": razorpay_payment_id,
                "order_id": razorpay_order_id,
                "amount": payment_details.get('amount', 0) / 100,
                "currency": payment_details.get('currency', self.currency),
                "status": payment_details.get('status'),
                "method": payment_details.get('method'),
                "subscription_activated": True
            }
            
        except Exception as e:
            logger.error(f"Error verifying payment signature: {str(e)}")
            return {
                "success": False,
                "error": "Payment verification failed",
                "message": str(e)
            }
    
    def _activate_subscription(self, user_id: str, plan_tier: str) -> Dict[str, Any]:
        """Activate subscription for user after successful payment"""
        try:
            # Import subscription service to avoid circular imports
            from services.subscription_service import SubscriptionService
            subscription_service = SubscriptionService()
            
            # Upgrade subscription with payment verification
            success, message = subscription_service.upgrade_subscription(user_id, plan_tier, payment_verified=True)
            
            return {
                "success": success,
                "message": message
            }
            
        except Exception as e:
            logger.error(f"Error activating subscription: {str(e)}")
            return {
                "success": False,
                "message": f"Subscription activation failed: {str(e)}"
            }
    
    def process_webhook(self, webhook_data: dict, webhook_signature: str) -> Dict[str, Any]:
        """Process Razorpay webhook events"""
        try:
            # Verify webhook signature
            if not self._verify_webhook_signature(json.dumps(webhook_data), webhook_signature):
                logger.warning("Invalid webhook signature received")
                return {
                    "success": False,
                    "error": "Invalid webhook signature"
                }
            
            event = webhook_data.get('event')
            payload = webhook_data.get('payload', {})
            
            logger.info(f"Processing webhook event: {event}")
            
            if event == 'payment.captured':
                return self._handle_payment_captured(payload)
            elif event == 'payment.failed':
                return self._handle_payment_failed(payload)
            elif event == 'order.paid':
                return self._handle_order_paid(payload)
            else:
                logger.info(f"Unhandled webhook event: {event}")
                return {"success": True, "message": f"Event {event} acknowledged"}
            
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            return {
                "success": False,
                "error": "Webhook processing failed",
                "message": str(e)
            }
    
    def _verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """Verify webhook signature"""
        try:
            expected_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected_signature, signature)
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False
    
    def _handle_payment_captured(self, payload: dict) -> Dict[str, Any]:
        """Handle payment.captured webhook event"""
        try:
            payment_entity = payload.get('payment', {}).get('entity', {})
            order_id = payment_entity.get('order_id')
            payment_id = payment_entity.get('id')
            
            if not order_id or not payment_id:
                return {"success": False, "error": "Missing order_id or payment_id"}
            
            # Update payment status
            update_result = self.payments.update_one(
                {"razorpay_order_id": order_id},
                {
                    "$set": {
                        "payment_status": "captured",
                        "razorpay_payment_id": payment_id,
                        "razorpay_response": payment_entity,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if update_result.modified_count > 0:
                logger.info(f"Payment captured webhook processed for order {order_id}")
                return {"success": True, "message": "Payment captured"}
            else:
                logger.warning(f"No payment record found for order {order_id}")
                return {"success": False, "error": "Payment record not found"}
                
        except Exception as e:
            logger.error(f"Error handling payment captured webhook: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _handle_payment_failed(self, payload: dict) -> Dict[str, Any]:
        """Handle payment.failed webhook event"""
        try:
            payment_entity = payload.get('payment', {}).get('entity', {})
            order_id = payment_entity.get('order_id')
            payment_id = payment_entity.get('id')
            
            if not order_id:
                return {"success": False, "error": "Missing order_id"}
            
            # Update payment status
            update_result = self.payments.update_one(
                {"razorpay_order_id": order_id},
                {
                    "$set": {
                        "payment_status": "failed",
                        "razorpay_payment_id": payment_id,
                        "razorpay_response": payment_entity,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            # Update order status
            self.orders.update_one(
                {"razorpay_order_id": order_id},
                {"$set": {"status": "failed"}}
            )
            
            if update_result.modified_count > 0:
                logger.info(f"Payment failed webhook processed for order {order_id}")
                return {"success": True, "message": "Payment failure recorded"}
            else:
                logger.warning(f"No payment record found for order {order_id}")
                return {"success": False, "error": "Payment record not found"}
                
        except Exception as e:
            logger.error(f"Error handling payment failed webhook: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _handle_order_paid(self, payload: dict) -> Dict[str, Any]:
        """Handle order.paid webhook event"""
        try:
            order_entity = payload.get('order', {}).get('entity', {})
            order_id = order_entity.get('id')
            
            if not order_id:
                return {"success": False, "error": "Missing order_id"}
            
            # Update order status
            update_result = self.orders.update_one(
                {"razorpay_order_id": order_id},
                {"$set": {"status": "paid"}}
            )
            
            if update_result.modified_count > 0:
                logger.info(f"Order paid webhook processed for order {order_id}")
                return {"success": True, "message": "Order marked as paid"}
            else:
                logger.warning(f"No order record found for order {order_id}")
                return {"success": False, "error": "Order record not found"}
                
        except Exception as e:
            logger.error(f"Error handling order paid webhook: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def get_payment_status(self, razorpay_order_id: str) -> Dict[str, Any]:
        """Get payment status from database and Razorpay"""
        try:
            # Get payment from database
            payment = self.payments.find_one({"razorpay_order_id": razorpay_order_id})
            if not payment:
                return {
                    "success": False,
                    "error": "Payment not found",
                    "message": "No payment record found for this order"
                }
            
            # Get latest status from Razorpay if payment ID exists
            if payment.get('razorpay_payment_id'):
                try:
                    razorpay_payment = self.client.payment.fetch(payment['razorpay_payment_id'])
                    
                    # Update local record if status changed
                    if razorpay_payment['status'] != payment['payment_status']:
                        self.payments.update_one(
                            {"razorpay_order_id": razorpay_order_id},
                            {
                                "$set": {
                                    "payment_status": razorpay_payment['status'],
                                    "razorpay_response": razorpay_payment,
                                    "updated_at": datetime.utcnow()
                                }
                            }
                        )
                        payment['payment_status'] = razorpay_payment['status']
                        
                except Exception as e:
                    logger.warning(f"Could not fetch payment status from Razorpay: {str(e)}")
            
            return {
                "success": True,
                "order_id": razorpay_order_id,
                "payment_id": payment.get('razorpay_payment_id'),
                "status": payment['payment_status'],
                "amount": payment['amount'],
                "currency": payment['currency'],
                "plan_tier": payment['plan_tier'],
                "created_at": payment['created_at'].isoformat(),
                "updated_at": payment['updated_at'].isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting payment status: {str(e)}")
            return {
                "success": False,
                "error": "Failed to get payment status",
                "message": str(e)
            }
    
    def cancel_payment(self, razorpay_order_id: str) -> Dict[str, Any]:
        """Cancel a payment order"""
        try:
            # Update payment status
            payment_result = self.payments.update_one(
                {"razorpay_order_id": razorpay_order_id, "payment_status": {"$in": ["created", "attempted"]}},
                {
                    "$set": {
                        "payment_status": "cancelled",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            # Update order status
            order_result = self.orders.update_one(
                {"razorpay_order_id": razorpay_order_id, "status": {"$in": ["created"]}},
                {"$set": {"status": "cancelled"}}
            )
            
            if payment_result.modified_count > 0:
                logger.info(f"Payment cancelled for order {razorpay_order_id}")
                return {
                    "success": True,
                    "message": "Payment cancelled successfully"
                }
            else:
                return {
                    "success": False,
                    "error": "Cannot cancel payment",
                    "message": "Payment may already be processed or cancelled"
                }
                
        except Exception as e:
            logger.error(f"Error cancelling payment: {str(e)}")
            return {
                "success": False,
                "error": "Failed to cancel payment",
                "message": str(e)
            }
    
    def get_payment_history(self, user_id: str, limit: int = 20, skip: int = 0) -> Dict[str, Any]:
        """Get payment history for a user"""
        try:
            # Get payments with pagination
            payments_cursor = self.payments.find(
                {"user_id": ObjectId(user_id)},
                {
                    "razorpay_order_id": 1,
                    "razorpay_payment_id": 1,
                    "amount": 1,
                    "currency": 1,
                    "plan_tier": 1,
                    "payment_status": 1,
                    "created_at": 1,
                    "updated_at": 1
                }
            ).sort("created_at", -1).limit(limit).skip(skip)
            
            payments = list(payments_cursor)
            
            # Get total count
            total_count = self.payments.count_documents({"user_id": ObjectId(user_id)})
            
            # Format payments for response
            formatted_payments = []
            for payment in payments:
                formatted_payments.append({
                    "order_id": payment['razorpay_order_id'],
                    "payment_id": payment.get('razorpay_payment_id'),
                    "amount": payment['amount'],
                    "currency": payment['currency'],
                    "plan_tier": payment['plan_tier'],
                    "status": payment['payment_status'],
                    "created_at": payment['created_at'].isoformat(),
                    "updated_at": payment['updated_at'].isoformat()
                })
            
            return {
                "success": True,
                "payments": formatted_payments,
                "total_count": total_count,
                "limit": limit,
                "skip": skip,
                "has_more": (skip + limit) < total_count
            }
            
        except Exception as e:
            logger.error(f"Error getting payment history: {str(e)}")
            return {
                "success": False,
                "error": "Failed to get payment history",
                "message": str(e)
            }
    
    def get_plan_pricing(self) -> Dict[str, Any]:
        """Get available subscription plans with pricing"""
        try:
            plans = {}
            for tier, price_paise in self.plan_prices.items():
                tier_config = self.config.SUBSCRIPTION_TIERS.get(tier, {})
                plans[tier] = {
                    "name": tier,
                    "price": price_paise / 100,  # Convert paise to rupees
                    "currency": self.currency,
                    "description": tier_config.get('description', ''),
                    "features": {
                        "backtest_daily_limit": tier_config.get('backtest_daily_limit', 0),
                        "llm_daily_limit": tier_config.get('llm_daily_limit', 0),
                        "market_data_delay": tier_config.get('market_data_delay', 'delayed')
                    }
                }
            
            return {
                "success": True,
                "plans": plans
            }
            
        except Exception as e:
            logger.error(f"Error getting plan pricing: {str(e)}")
            return {
                "success": False,
                "error": "Failed to get plan pricing",
                "message": str(e)
            }
    
    def cleanup_expired_orders(self) -> Dict[str, Any]:
        """Cleanup expired orders and payments"""
        try:
            current_time = datetime.utcnow()
            
            # Update expired orders
            expired_orders = self.orders.update_many(
                {
                    "expires_at": {"$lt": current_time},
                    "status": "created"
                },
                {"$set": {"status": "expired"}}
            )
            
            # Update expired payments
            expired_payments = self.payments.update_many(
                {
                    "expires_at": {"$lt": current_time},
                    "payment_status": "created"
                },
                {
                    "$set": {
                        "payment_status": "expired",
                        "updated_at": current_time
                    }
                }
            )
            
            logger.info(f"Cleaned up {expired_orders.modified_count} expired orders and {expired_payments.modified_count} expired payments")
            
            return {
                "success": True,
                "expired_orders": expired_orders.modified_count,
                "expired_payments": expired_payments.modified_count
            }
            
        except Exception as e:
            logger.error(f"Error cleaning up expired orders: {str(e)}")
            return {
                "success": False,
                "error": "Cleanup failed",
                "message": str(e)
            }
    
    def _get_plan_features(self, plan_tier: str) -> List[str]:
        """Get features list for a plan tier"""
        features_map = {
            'FREE': [
                'Basic stock analysis',
                '3 backtests per day',
                '10 AI queries per day',
                'Delayed market data (15 min)'
            ],
            'BASIC': [
                'Advanced stock analysis',
                '25 backtests per day',
                '50 AI queries per day',
                'Real-time market data',
                'Technical indicators',
                'Email support'
            ],
            'PRO': [
                'Premium stock analysis',
                '100 backtests per day',
                '200 AI queries per day',
                'Real-time market data',
                'Advanced technical indicators',
                'Portfolio management',
                'Custom strategies',
                'Priority email support'
            ],
            'ENTERPRISE': [
                'Enterprise stock analysis',
                'Unlimited backtests',
                'Unlimited AI queries',
                'Real-time market data',
                'All technical indicators',
                'Advanced portfolio management',
                'Custom strategies & alerts',
                'API access',
                'Dedicated support'
            ]
        }
        
        return features_map.get(plan_tier, [])