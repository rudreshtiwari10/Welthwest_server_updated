#!/usr/bin/env python3
"""
Test endpoint to simulate and debug Razorpay payment verification
This helps test the exact flow without going through the full payment process
"""

import sys
import os
import json
import requests
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_payment_verification_endpoint():
    """Test the payment verification endpoint with sample data"""
    
    print("Testing Payment Verification Endpoint")
    print("=" * 40)
    
    base_url = "http://localhost:8000"
    
    # Test data (you would get these from actual Razorpay payment)
    test_data = {
        "razorpay_order_id": "order_test123456789",
        "razorpay_payment_id": "pay_test123456789", 
        "razorpay_signature": "test_signature_here"  # This would be actual signature from Razorpay
    }
    
    print("1. Testing without authentication (should fail):")
    response = requests.post(f"{base_url}/api/payment/verify", json=test_data)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    print("\n2. Register test user and get token:")
    # Register a test user
    test_email = f"test_payment_{datetime.now().strftime('%Y%m%d_%H%M%S')}@example.com"
    test_username = f"paytest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    register_data = {
        "email": test_email,
        "username": test_username,
        "password": "testpassword123",
        "confirm_password": "testpassword123"
    }
    
    response = requests.post(f"{base_url}/api/auth/register", json=register_data)
    if response.status_code == 201:
        auth_data = response.json()
        access_token = auth_data.get('access_token')
        print(f"   User registered successfully: {test_username}")
        print(f"   Access token: {access_token[:20]}...")
    else:
        print(f"   Registration failed: {response.text}")
        return
    
    print("\n3. Create a real payment order:")
    headers = {'Authorization': f'Bearer {access_token}'}
    
    order_data = {
        "plan_tier": "BASIC",
        "billing_details": {
            "full_name": "Test User",
            "email": test_email,
            "phone": "+919876543210"
        }
    }
    
    response = requests.post(f"{base_url}/api/payment/create-order", json=order_data, headers=headers)
    if response.status_code == 200:
        order_response = response.json()
        real_order_id = order_response.get('order_id')
        print(f"   Order created successfully: {real_order_id}")
        
        # Test with real order ID but fake payment data
        print("\n4. Test verification with real order ID but test payment data:")
        test_data_real = {
            "razorpay_order_id": real_order_id,
            "razorpay_payment_id": "pay_test123456789",
            "razorpay_signature": "invalid_signature_for_testing"
        }
        
        response = requests.post(f"{base_url}/api/payment/verify", json=test_data_real, headers=headers)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        
    else:
        print(f"   Order creation failed: {response.text}")
    
    print("\n" + "=" * 40)
    print("Test completed. Check the server logs for detailed debugging information.")
    print("\nTo test with real Razorpay data:")
    print("1. Complete a real payment using test cards")
    print("2. Use the debug_razorpay.py script with actual order_id, payment_id, and signature")

if __name__ == "__main__":
    # Check if server is running
    try:
        response = requests.get("http://localhost:5000/health", timeout=5)
        if response.status_code == 200:
            print("Server is running. Starting test...")
            test_payment_verification_endpoint()
        else:
            print(f"Server returned status {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Cannot connect to server: {e}")
        print("Please ensure the Flask application is running:")
        print("  python app.py")