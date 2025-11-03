"""
Cashfree Payment Service - Handle Cashfree payment gateway integration
Implements order creation, webhook verification, and payment status checking
"""
import requests
import hmac
import hashlib
import base64
import logging
from typing import Dict, Any, Optional, Tuple
from config import get_config
from datetime import datetime

logger = logging.getLogger(__name__)


class CashfreePaymentService:
    """Service for Cashfree payment gateway integration"""

    def __init__(self):
        self.config = get_config()

        # Cashfree API URLs
        if self.config.CASHFREE_ENV == 'production':
            self.base_url = "https://api.cashfree.com/pg"
        else:
            self.base_url = "https://sandbox.cashfree.com/pg"

        # Check if payment gateway is enabled
        self.is_enabled = self.config.IS_PAYMENT_GATEWAY_ENABLED

        if not self.is_enabled:
            logger.warning("Cashfree Payment Gateway is DISABLED")
        else:
            logger.info(f"Cashfree Payment Service initialized (ENV: {self.config.CASHFREE_ENV})")

    def _get_headers(self) -> Dict[str, str]:
        """
        Get headers for Cashfree API requests

        Returns:
            Dict of headers including authentication
        """
        return {
            "Content-Type": "application/json",
            "x-client-id": self.config.CASHFREE_APP_ID,
            "x-client-secret": self.config.CASHFREE_SECRET_KEY,
            "x-api-version": "2023-08-01"
        }

    def create_order(
        self,
        order_id: str,
        amount: float,
        customer_id: str,
        customer_email: str,
        customer_phone: str,
        return_url: str,
        plan_name: str,
        plan_duration: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Create a Cashfree order

        Args:
            order_id: Unique order identifier (from your system)
            amount: Order amount in INR
            customer_id: User ID
            customer_email: User email
            customer_phone: User phone number
            return_url: URL to redirect after payment
            plan_name: Plan being purchased
            plan_duration: Plan duration (weekly/monthly/annual)

        Returns:
            Tuple of (success: bool, response_data: dict)
        """
        if not self.is_enabled:
            return False, {"error": "Payment gateway is disabled"}

        try:
            # Prepare return URL with order_id parameter
            separator = '&' if '?' in return_url else '?'
            return_url_with_order = f"{return_url}{separator}order_id={order_id}"

            logger.info(f"Creating order with return_url: {return_url_with_order}")

            # Prepare order data
            order_data = {
                "order_id": order_id,
                "order_amount": amount,
                "order_currency": "INR",
                "customer_details": {
                    "customer_id": customer_id,
                    "customer_email": customer_email,
                    "customer_phone": customer_phone
                },
                "order_meta": {
                    "return_url": return_url_with_order
                    # notify_url removed - will use webhook configured in Cashfree dashboard
                },
                "order_note": f"{plan_name} - {plan_duration}",
                "order_tags": {
                    "plan": plan_name,
                    "duration": plan_duration
                }
            }

            # Make API request
            response = requests.post(
                f"{self.base_url}/orders",
                json=order_data,
                headers=self._get_headers(),
                timeout=10
            )

            response_data = response.json()

            # Log full Cashfree response for debugging
            logger.info(f"Cashfree API Response: {response_data}")

            if response.status_code == 200 and response_data.get("order_status") == "ACTIVE":
                logger.info(f"Cashfree order created successfully: {order_id}")

                # Get payment_session_id
                payment_session_id = response_data.get("payment_session_id")

                # Cashfree payment URL format (without the #)
                if self.config.CASHFREE_ENV == 'production':
                    payment_link = f"https://payments.cashfree.com/order/{payment_session_id}"
                else:
                    payment_link = f"https://payments-test.cashfree.com/order/{payment_session_id}"

                logger.info(f"Payment link generated: {payment_link}")

                return True, {
                    "order_id": order_id,
                    "payment_session_id": payment_session_id,
                    "order_status": response_data.get("order_status"),
                    "payment_link": payment_link  # Constructed payment link
                }
            else:
                logger.error(f"Cashfree order creation failed: {response_data}")
                return False, {"error": response_data.get("message", "Order creation failed")}

        except requests.RequestException as e:
            logger.error(f"Cashfree API request failed: {e}")
            return False, {"error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error creating Cashfree order: {e}")
            return False, {"error": str(e)}

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        timestamp: str
    ) -> bool:
        """
        Verify Cashfree webhook signature

        Args:
            payload: Raw request body (bytes)
            signature: Signature from x-webhook-signature header
            timestamp: Timestamp from x-webhook-timestamp header

        Returns:
            True if signature is valid, False otherwise
        """
        if not self.config.CASHFREE_SECRET_KEY:
            logger.error("CASHFREE_SECRET_KEY not configured")
            return False

        if not signature or not timestamp:
            logger.error(f"Missing webhook headers: signature={signature}, timestamp={timestamp}")
            return False

        try:
            # Construct the signed payload: timestamp + raw_body
            signed_payload = f"{timestamp}{payload.decode('utf-8')}"

            # Compute HMAC SHA256 and encode to base64 (Cashfree uses base64, not hex)
            expected_signature = base64.b64encode(
                hmac.new(
                    self.config.CASHFREE_SECRET_KEY.encode('utf-8'),
                    signed_payload.encode('utf-8'),
                    hashlib.sha256
                ).digest()
            ).decode('utf-8')

            # Compare signatures
            is_valid = hmac.compare_digest(expected_signature, signature)

            if is_valid:
                logger.info("Webhook signature verified successfully")
            else:
                logger.warning(f"Webhook signature verification failed. Expected: {expected_signature}, Got: {signature}")

            return is_valid

        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False

    def get_order_status(self, order_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Get order status from Cashfree

        Args:
            order_id: Order identifier

        Returns:
            Tuple of (success: bool, order_data: dict)
        """
        if not self.is_enabled:
            return False, {"error": "Payment gateway is disabled"}

        try:
            response = requests.get(
                f"{self.base_url}/orders/{order_id}",
                headers=self._get_headers(),
                timeout=10
            )

            response_data = response.json()

            if response.status_code == 200:
                return True, response_data
            else:
                logger.error(f"Failed to get order status: {response_data}")
                return False, {"error": response_data.get("message", "Failed to get order status")}

        except requests.RequestException as e:
            logger.error(f"Cashfree API request failed: {e}")
            return False, {"error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error getting order status: {e}")
            return False, {"error": str(e)}

    def get_payment_status(self, order_id: str, payment_id: str = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Get payment status for an order

        Args:
            order_id: Order identifier
            payment_id: Optional payment identifier

        Returns:
            Tuple of (success: bool, payment_data: dict)
        """
        if not self.is_enabled:
            return False, {"error": "Payment gateway is disabled"}

        try:
            # If payment_id is provided, get specific payment
            if payment_id:
                url = f"{self.base_url}/orders/{order_id}/payments/{payment_id}"
            else:
                # Get all payments for the order
                url = f"{self.base_url}/orders/{order_id}/payments"

            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=10
            )

            response_data = response.json()

            if response.status_code == 200:
                return True, response_data
            else:
                logger.error(f"Failed to get payment status: {response_data}")
                return False, {"error": response_data.get("message", "Failed to get payment status")}

        except requests.RequestException as e:
            logger.error(f"Cashfree API request failed: {e}")
            return False, {"error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error getting payment status: {e}")
            return False, {"error": str(e)}

    def process_webhook_payment(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process Cashfree webhook payment data

        Args:
            webhook_data: Webhook payload from Cashfree

        Returns:
            Processed payment information
        """
        try:
            event_type = webhook_data.get("type")
            data = webhook_data.get("data", {})

            # Extract payment information
            order = data.get("order", {})
            payment = data.get("payment", {})

            processed_data = {
                "event_type": event_type,
                "order_id": order.get("order_id"),
                "order_amount": order.get("order_amount"),
                "order_status": order.get("order_status"),
                "order_token": order.get("order_token"),
                "payment_id": payment.get("cf_payment_id"),
                "payment_status": payment.get("payment_status"),
                "payment_amount": payment.get("payment_amount"),
                "payment_time": payment.get("payment_time"),
                "payment_method": payment.get("payment_group"),
                "bank_reference": payment.get("bank_reference"),
                "auth_id": payment.get("auth_id"),
                "customer_email": order.get("customer_details", {}).get("customer_email"),
                "customer_phone": order.get("customer_details", {}).get("customer_phone"),
                "order_tags": order.get("order_tags", {})
            }

            return processed_data

        except Exception as e:
            logger.error(f"Error processing webhook payment: {e}")
            return {}

    def is_payment_success(self, webhook_data: Dict[str, Any]) -> bool:
        """
        Check if webhook indicates successful payment

        Args:
            webhook_data: Webhook payload from Cashfree

        Returns:
            True if payment is successful
        """
        try:
            event_type = webhook_data.get("type")
            payment_status = webhook_data.get("data", {}).get("payment", {}).get("payment_status")

            # Check for success event and status
            return (event_type == "PAYMENT_SUCCESS_WEBHOOK" and
                    payment_status == "SUCCESS")

        except Exception as e:
            logger.error(f"Error checking payment success: {e}")
            return False

    def refund_payment(
        self,
        order_id: str,
        refund_amount: float,
        refund_id: str,
        refund_note: str = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Initiate refund for a payment

        Args:
            order_id: Order identifier
            refund_amount: Amount to refund
            refund_id: Unique refund identifier
            refund_note: Optional refund note

        Returns:
            Tuple of (success: bool, refund_data: dict)
        """
        if not self.is_enabled:
            return False, {"error": "Payment gateway is disabled"}

        try:
            refund_data = {
                "refund_id": refund_id,
                "refund_amount": refund_amount,
                "refund_note": refund_note or "Subscription refund"
            }

            response = requests.post(
                f"{self.base_url}/orders/{order_id}/refunds",
                json=refund_data,
                headers=self._get_headers(),
                timeout=10
            )

            response_data = response.json()

            if response.status_code == 200:
                logger.info(f"Refund initiated successfully: {refund_id}")
                return True, response_data
            else:
                logger.error(f"Refund initiation failed: {response_data}")
                return False, {"error": response_data.get("message", "Refund initiation failed")}

        except requests.RequestException as e:
            logger.error(f"Cashfree API request failed: {e}")
            return False, {"error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error initiating refund: {e}")
            return False, {"error": str(e)}


# Create singleton instance
_cashfree_service = None

def get_cashfree_service() -> CashfreePaymentService:
    """Get the singleton CashfreePaymentService instance"""
    global _cashfree_service
    if _cashfree_service is None:
        _cashfree_service = CashfreePaymentService()
    return _cashfree_service
