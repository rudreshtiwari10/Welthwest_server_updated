#!/usr/bin/env python3
"""
Test script for password reset functionality
"""
import requests
import json
import time

# Configuration
BASE_URL = "http://localhost:5000"
TEST_EMAIL = "test@example.com"
TEST_USERNAME = "testuser"

def test_forgot_password():
    """Test the forgot password endpoint"""
    print("Testing forgot password endpoint...")
    
    url = f"{BASE_URL}/api/auth/forgot-password"
    data = {
        "username_or_email": TEST_EMAIL
    }
    
    try:
        response = requests.post(url, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print("✅ Forgot password endpoint working!")
            return True
        else:
            print("❌ Forgot password endpoint failed!")
            return False
            
    except Exception as e:
        print(f"❌ Error testing forgot password: {str(e)}")
        return False

def test_verify_otp():
    """Test the OTP verification endpoint"""
    print("\nTesting OTP verification endpoint...")
    
    # This would require a valid OTP from the previous step
    otp = input("Enter the OTP received in email (or press Enter to skip): ").strip()
    
    if not otp:
        print("⏭️ Skipping OTP verification test")
        return True
    
    url = f"{BASE_URL}/api/auth/verify-reset-otp"
    data = {
        "username_or_email": TEST_EMAIL,
        "otp": otp
    }
    
    try:
        response = requests.post(url, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print("✅ OTP verification endpoint working!")
            return response.json().get('user_id')
        else:
            print("❌ OTP verification endpoint failed!")
            return False
            
    except Exception as e:
        print(f"❌ Error testing OTP verification: {str(e)}")
        return False

def test_reset_password(user_id, otp):
    """Test the password reset endpoint"""
    print("\nTesting password reset endpoint...")
    
    if not user_id or not otp:
        print("⏭️ Skipping password reset test (missing user_id or otp)")
        return True
    
    url = f"{BASE_URL}/api/auth/reset-password"
    data = {
        "user_id": user_id,
        "new_password": "newpassword123",
        "otp": otp
    }
    
    try:
        response = requests.post(url, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print("✅ Password reset endpoint working!")
            return True
        else:
            print("❌ Password reset endpoint failed!")
            return False
            
    except Exception as e:
        print(f"❌ Error testing password reset: {str(e)}")
        return False

def main():
    """Run all password reset tests"""
    print("🧪 Testing Password Reset Flow")
    print("=" * 40)
    
    # Test 1: Forgot password
    forgot_success = test_forgot_password()
    
    # Test 2: Verify OTP
    user_id = test_verify_otp() if forgot_success else False
    
    # Test 3: Reset password
    if user_id:
        otp = input("Enter the same OTP for password reset (or press Enter to skip): ").strip()
        test_reset_password(user_id, otp)
    
    print("\n" + "=" * 40)
    print("🏁 Password reset flow tests completed!")
    
    print("\n📋 API Endpoints Summary:")
    print("1. POST /api/auth/forgot-password")
    print("   - Input: {username_or_email}")
    print("   - Output: {message, email_sent}")
    
    print("\n2. POST /api/auth/verify-reset-otp")  
    print("   - Input: {username_or_email, otp}")
    print("   - Output: {message, user_id, otp_verified}")
    
    print("\n3. POST /api/auth/reset-password")
    print("   - Input: {user_id, new_password, otp}")
    print("   - Output: {message, password_reset}")

if __name__ == "__main__":
    main()