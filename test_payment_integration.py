#!/usr/bin/env python3
"""
Test script for Razorpay payment integration
This script tests all payment-related functionality
"""

import os
import sys
import json
import requests
from datetime import datetime
import logging

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PaymentIntegrationTester:
    """Test suite for payment integration"""
    
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.access_token = None
        self.user_id = None
        
    def register_test_user(self):
        """Register a test user for payment testing"""
        test_email = f"test_payment_{datetime.now().strftime('%Y%m%d_%H%M%S')}@example.com"
        test_username = f"paytest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        register_data = {
            "email": test_email,
            "username": test_username,
            "password": "testpassword123",
            "confirm_password": "testpassword123"
        }
        
        response = self.session.post(
            f"{self.base_url}/api/auth/register",
            json=register_data
        )
        
        if response.status_code == 201:
            data = response.json()
            self.access_token = data.get('access_token')
            self.user_id = data.get('user', {}).get('id')
            
            # Set authorization header for future requests
            self.session.headers.update({
                'Authorization': f'Bearer {self.access_token}'
            })
            
            logger.info(f"✓ Test user registered: {test_username}")
            return True
        else:
            logger.error(f"✗ Failed to register test user: {response.text}")
            return False
    
    def test_get_payment_plans(self):
        """Test getting payment plans"""
        logger.info("\n--- Testing Payment Plans Endpoint ---")
        
        response = self.session.get(f"{self.base_url}/api/payment/plans")
        
        if response.status_code == 200:
            data = response.json()
            if 'plans' in data and data['success']:
                logger.info("✓ Payment plans retrieved successfully")
                for plan_name, plan_details in data['plans'].items():
                    logger.info(f"  - {plan_name}: ₹{plan_details['price']}")
                return True
            else:
                logger.error("✗ Invalid response format for payment plans")
                return False
        else:
            logger.error(f"✗ Failed to get payment plans: {response.text}")
            return False
    
    def test_billing_details(self):
        """Test billing details endpoints"""
        logger.info("\n--- Testing Billing Details ---")
        
        # Test getting billing details (should be empty initially)
        response = self.session.get(f"{self.base_url}/api/user/billing-details")
        if response.status_code == 200:
            logger.info("✓ Get billing details endpoint working")
        else:
            logger.error(f"✗ Failed to get billing details: {response.text}")
            return False
        
        # Test updating billing details
        billing_data = {
            "full_name": "Test Payment User",
            "email": "test@example.com",
            "phone": "+919876543210",
            "address": {
                "street": "123 Test Street",
                "city": "Test City",
                "state": "Test State",
                "country": "India",
                "pincode": "123456"
            }
        }
        
        response = self.session.post(
            f"{self.base_url}/api/user/billing-details",
            json=billing_data
        )
        
        if response.status_code == 200:
            logger.info("✓ Billing details updated successfully")
            return True
        else:
            logger.error(f"✗ Failed to update billing details: {response.text}")
            return False
    
    def test_create_payment_order(self):
        """Test creating a payment order"""
        logger.info("\n--- Testing Payment Order Creation ---")
        
        # First update billing details
        billing_data = {
            "full_name": "Test Payment User",
            "email": "test@example.com",
            "phone": "+919876543210"
        }
        
        order_data = {
            "plan_tier": "BASIC",
            "billing_details": billing_data
        }
        
        response = self.session.post(
            f"{self.base_url}/api/payment/create-order",
            json=order_data
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and 'order_id' in data:
                logger.info("✓ Payment order created successfully")
                logger.info(f"  - Order ID: {data['order_id']}")
                logger.info(f"  - Amount: ₹{data['amount']/100}")
                return data['order_id']
            else:
                logger.error("✗ Invalid response format for payment order")
                return None
        else:
            logger.error(f"✗ Failed to create payment order: {response.text}")
            return None
    
    def test_payment_status(self, order_id):
        """Test getting payment status"""
        logger.info("\n--- Testing Payment Status ---")
        
        response = self.session.get(f"{self.base_url}/api/payment/status/{order_id}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                logger.info("✓ Payment status retrieved successfully")
                logger.info(f"  - Status: {data['status']}")
                logger.info(f"  - Plan: {data['plan_tier']}")
                return True
            else:
                logger.error("✗ Invalid response format for payment status")
                return False
        else:
            logger.error(f"✗ Failed to get payment status: {response.text}")
            return False
    
    def test_payment_history(self):
        """Test getting payment history"""
        logger.info("\n--- Testing Payment History ---")
        
        response = self.session.get(f"{self.base_url}/api/payment/history")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                logger.info("✓ Payment history retrieved successfully")
                logger.info(f"  - Total payments: {data['total_count']}")
                return True
            else:
                logger.error("✗ Invalid response format for payment history")
                return False
        else:
            logger.error(f"✗ Failed to get payment history: {response.text}")
            return False
    
    def test_cancel_payment(self, order_id):
        """Test cancelling a payment order"""
        logger.info("\n--- Testing Payment Cancellation ---")
        
        response = self.session.post(f"{self.base_url}/api/payment/cancel/{order_id}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                logger.info("✓ Payment cancelled successfully")
                return True
            else:
                logger.error("✗ Failed to cancel payment")
                return False
        else:
            logger.error(f"✗ Failed to cancel payment: {response.text}")
            return False
    
    def test_subscription_endpoints(self):
        """Test subscription-related endpoints"""
        logger.info("\n--- Testing Subscription Endpoints ---")
        
        # Test getting subscription details
        response = self.session.get(f"{self.base_url}/api/user/subscription")
        if response.status_code == 200:
            data = response.json()
            logger.info("✓ Subscription details retrieved successfully")
            logger.info(f"  - Current tier: {data.get('tier')}")
        else:
            logger.error(f"✗ Failed to get subscription details: {response.text}")
            return False
        
        # Test getting usage metrics
        response = self.session.get(f"{self.base_url}/api/user/usage")
        if response.status_code == 200:
            data = response.json()
            logger.info("✓ Usage metrics retrieved successfully")
            logger.info(f"  - Daily backtest usage: {data.get('daily_usage', {}).get('backtest_count', 0)}")
        else:
            logger.error(f"✗ Failed to get usage metrics: {response.text}")
            return False
        
        return True
    
    def run_all_tests(self):
        """Run all payment integration tests"""
        logger.info("🚀 Starting Payment Integration Tests")
        logger.info("=" * 50)
        
        test_results = {}
        
        # Test 1: Register test user
        test_results['user_registration'] = self.register_test_user()
        
        if not test_results['user_registration']:
            logger.error("❌ Cannot proceed without user registration")
            return test_results
        
        # Test 2: Get payment plans
        test_results['payment_plans'] = self.test_get_payment_plans()
        
        # Test 3: Billing details
        test_results['billing_details'] = self.test_billing_details()
        
        # Test 4: Create payment order
        order_id = self.test_create_payment_order()
        test_results['create_payment_order'] = order_id is not None
        
        if order_id:
            # Test 5: Get payment status
            test_results['payment_status'] = self.test_payment_status(order_id)
            
            # Test 6: Cancel payment
            test_results['cancel_payment'] = self.test_cancel_payment(order_id)
        
        # Test 7: Payment history
        test_results['payment_history'] = self.test_payment_history()
        
        # Test 8: Subscription endpoints
        test_results['subscription_endpoints'] = self.test_subscription_endpoints()
        
        # Print summary
        logger.info("\n" + "=" * 50)
        logger.info("📊 TEST RESULTS SUMMARY")
        logger.info("=" * 50)
        
        passed = sum(1 for result in test_results.values() if result)
        total = len(test_results)
        
        for test_name, result in test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"{test_name.replace('_', ' ').title()}: {status}")
        
        logger.info(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("🎉 All payment integration tests passed!")
        else:
            logger.warning(f"⚠️  {total - passed} test(s) failed")
        
        return test_results

def main():
    """Main function to run payment integration tests"""
    print("Razorpay Payment Integration Test Suite")
    print("=" * 40)
    
    # Check if server is running
    base_url = "http://localhost:5000"
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print(f"✓ Server is running at {base_url}")
        else:
            print(f"✗ Server returned status {response.status_code}")
            return
    except requests.exceptions.RequestException as e:
        print(f"✗ Cannot connect to server at {base_url}")
        print(f"Error: {e}")
        print("\nPlease ensure the Flask application is running:")
        print("  python app.py")
        return
    
    # Run tests
    tester = PaymentIntegrationTester(base_url)
    results = tester.run_all_tests()
    
    # Return appropriate exit code
    if all(results.values()):
        sys.exit(0)  # All tests passed
    else:
        sys.exit(1)  # Some tests failed

if __name__ == "__main__":
    main()