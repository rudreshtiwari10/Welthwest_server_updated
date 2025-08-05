#!/usr/bin/env python3
"""
Debug script to test Razorpay signature verification
This will help identify the exact issue with payment verification
"""

import os
import sys
import hmac
import hashlib
import razorpay
from config import get_config

def test_razorpay_configuration():
    """Test Razorpay configuration and signature verification"""
    print("Debugging Razorpay Configuration")
    print("=" * 50)
    
    config = get_config()
    
    # Check configuration
    print("1. Configuration Check:")
    print(f"   RAZORPAY_KEY_ID: {'OK Set' if config.RAZORPAY_KEY_ID else 'X Missing'}")
    print(f"   RAZORPAY_KEY_SECRET: {'OK Set' if config.RAZORPAY_KEY_SECRET else 'X Missing'}")
    print(f"   RAZORPAY_WEBHOOK_SECRET: {'OK Set' if config.RAZORPAY_WEBHOOK_SECRET else 'X Missing'}")
    
    if not config.RAZORPAY_KEY_ID or not config.RAZORPAY_KEY_SECRET:
        print("\nError: Razorpay credentials not configured properly")
        print("Please check your .env file and ensure RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are set")
        return False
    
    print(f"   Key ID starts with: {config.RAZORPAY_KEY_ID[:10]}...")
    print(f"   Environment: {config.RAZORPAY_ENVIRONMENT}")
    print(f"   Currency: {config.RAZORPAY_CURRENCY}")
    
    # Test Razorpay client initialization
    print("\n2. Client Initialization:")
    try:
        client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))
        print("   OK Razorpay client initialized successfully")
    except Exception as e:
        print(f"   X Failed to initialize Razorpay client: {e}")
        return False
    
    # Test signature verification with sample data
    print("\n3. Signature Verification Test:")
    
    # Sample test data (these would be from a real payment)
    test_order_id = "order_test123456789"
    test_payment_id = "pay_test123456789"
    
    # Create a test signature using the webhook secret
    if config.RAZORPAY_KEY_SECRET:
        # Create expected signature
        payload = f"{test_order_id}|{test_payment_id}"
        expected_signature = hmac.new(
            config.RAZORPAY_KEY_SECRET.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        print(f"   Test payload: {payload}")
        print(f"   Expected signature: {expected_signature[:20]}...")
        
        # Test with Razorpay's utility
        params_dict = {
            'razorpay_order_id': test_order_id,
            'razorpay_payment_id': test_payment_id,
            'razorpay_signature': expected_signature
        }
        
        try:
            client.utility.verify_payment_signature(params_dict)
            print("   OK Signature verification test passed")
        except razorpay.errors.SignatureVerificationError as e:
            print(f"   X Signature verification failed: {e}")
            return False
        except Exception as e:
            print(f"   X Unexpected error during signature verification: {e}")
            return False
    
    print("\nOK All Razorpay configuration tests passed!")
    print("\nIf you're still getting signature verification errors, the issue might be:")
    print("1. The signature from frontend is being modified during transmission")
    print("2. The order_id or payment_id don't match what was originally created")
    print("3. The Razorpay test environment vs production environment mismatch")
    print("4. Network issues or request encoding problems")
    
    return True

def test_manual_signature_verification(order_id, payment_id, signature):
    """Test signature verification with actual payment data"""
    print(f"\nManual Signature Verification Test")
    print("=" * 50)
    
    config = get_config()
    
    if not config.RAZORPAY_KEY_SECRET:
        print("X RAZORPAY_KEY_SECRET not configured")
        return False
    
    # Manual signature calculation
    payload = f"{order_id}|{payment_id}"
    expected_signature = hmac.new(
        config.RAZORPAY_KEY_SECRET.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    print(f"Order ID: {order_id}")
    print(f"Payment ID: {payment_id}")
    print(f"Payload: {payload}")
    print(f"Provided signature: {signature}")
    print(f"Expected signature: {expected_signature}")
    print(f"Signatures match: {signature == expected_signature}")
    
    # Test with Razorpay utility
    client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))
    params_dict = {
        'razorpay_order_id': order_id,
        'razorpay_payment_id': payment_id,
        'razorpay_signature': signature
    }
    
    try:
        client.utility.verify_payment_signature(params_dict)
        print("OK Razorpay utility verification: PASSED")
        return True
    except razorpay.errors.SignatureVerificationError as e:
        print(f"X Razorpay utility verification: FAILED - {e}")
        return False
    except Exception as e:
        print(f"X Unexpected error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) == 4:
        # Manual test with provided order_id, payment_id, signature
        order_id = sys.argv[1]
        payment_id = sys.argv[2]
        signature = sys.argv[3]
        test_manual_signature_verification(order_id, payment_id, signature)
    else:
        # Run configuration test
        test_razorpay_configuration()
        
    print(f"\nUsage for manual testing:")
    print(f"python debug_razorpay.py <order_id> <payment_id> <signature>")