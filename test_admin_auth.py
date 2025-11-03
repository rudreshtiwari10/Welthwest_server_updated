"""
Test script to verify admin authentication
Usage: python3 test_admin_auth.py
"""
import requests
import json

BASE_URL = "http://localhost:5000"

def test_admin_flow():
    print("=" * 60)
    print("Testing Admin Authentication & Manual Credit")
    print("=" * 60)
    print()

    # Step 1: Login
    print("Step 1: Logging in as admin...")
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "username_or_email": "test1112@email.com",
            "password": input("Enter password for test1112@email.com: ")
        }
    )

    if login_response.status_code != 200:
        print(f"❌ Login failed: {login_response.status_code}")
        print(f"Response: {login_response.text}")
        return

    login_data = login_response.json()
    access_token = login_data.get('access_token')

    if not access_token:
        print("❌ No access token in response")
        return

    print(f"✅ Login successful!")
    print(f"Token (first 20 chars): {access_token[:20]}...")
    print()

    # Step 2: Check current subscription
    print("Step 2: Checking current subscription...")
    headers = {"Authorization": f"Bearer {access_token}"}

    sub_response = requests.get(
        f"{BASE_URL}/api/premium/user/subscription",
        headers=headers
    )

    if sub_response.status_code == 200:
        sub_data = sub_response.json()
        print(f"✅ Current Plan: {sub_data['subscription']['plan']}")
        print(f"   Limits: {sub_data['subscription']['limits']}")
    else:
        print(f"⚠️  Could not fetch subscription: {sub_response.status_code}")
    print()

    # Step 3: Test admin manual credit
    print("Step 3: Testing admin manual credit...")
    user_id = login_data.get('user', {}).get('id') or login_data.get('user_id')

    if not user_id:
        print("⚠️  Could not get user_id from login response")
        print(f"Login response: {json.dumps(login_data, indent=2)}")
        user_id = input("Enter user_id manually: ")

    print(f"Using user_id: {user_id}")

    credit_response = requests.post(
        f"{BASE_URL}/api/admin/manual-credit",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json={
            "user_id": user_id,
            "plan": "PRO",
            "duration": "monthly",
            "note": "Testing admin credit"
        }
    )

    print(f"Response Status: {credit_response.status_code}")
    print(f"Response Body: {json.dumps(credit_response.json(), indent=2)}")
    print()

    if credit_response.status_code == 200:
        print("✅ Manual credit successful!")
        print()

        # Step 4: Verify upgrade
        print("Step 4: Verifying upgrade...")
        sub_response2 = requests.get(
            f"{BASE_URL}/api/premium/user/subscription",
            headers=headers
        )

        if sub_response2.status_code == 200:
            sub_data2 = sub_response2.json()
            print(f"✅ Updated Plan: {sub_data2['subscription']['plan']}")
            print(f"   New Limits: {sub_data2['subscription']['limits']}")
        print()
        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)

    elif credit_response.status_code == 403:
        print("❌ FORBIDDEN - Not recognized as admin!")
        print()
        print("Debugging steps:")
        print("1. Check server logs for: 'Admin check for user_id: XXX'")
        print("2. Check server logs for: 'User XXX has role: YYY'")
        print(f"3. Verify in MongoDB:")
        print(f"   mongo")
        print(f"   use welthwest")
        print(f"   db.users.findOne({{_id: ObjectId('{user_id}')}}, {{role: 1}})")
        print()
        print("If role is 'admin', the issue might be with JWT token format.")
        print("Check server logs for detailed error messages.")

    else:
        print(f"❌ Unexpected response: {credit_response.status_code}")
        print("Check server logs for errors")

if __name__ == "__main__":
    test_admin_flow()
