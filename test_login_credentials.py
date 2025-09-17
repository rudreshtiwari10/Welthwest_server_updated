import requests
import json

# Test different login combinations
BASE_URL = "http://localhost:8000/api"

test_credentials = [
    {"username_or_email": "test@example.com", "password": "testpass123"},
    {"username_or_email": "testuser", "password": "testpass123"},
    {"username_or_email": "test@example.com", "password": "testpassword123"},
    {"username_or_email": "testuser", "password": "testpassword123"},
    {"username_or_email": "admin@example.com", "password": "testpass123"},
    {"username_or_email": "adminuser", "password": "testpass123"},
    {"username_or_email": "admin@example.com", "password": "testpassword123"},
    {"username_or_email": "adminuser", "password": "testpassword123"},
]

print("Testing login credentials...")
print("=" * 50)

for i, creds in enumerate(test_credentials, 1):
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json=creds,
            headers={"Content-Type": "application/json"}
        )

        print(f"\nTest {i}:")
        print(f"Credentials: {creds['username_or_email']} / {creds['password']}")
        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            print("SUCCESS! LOGIN WORKED!")
            result = response.json()
            print(f"User: {result.get('user', {}).get('username', 'N/A')}")
            print(f"Email: {result.get('user', {}).get('email', 'N/A')}")
            break
        else:
            try:
                error_data = response.json()
                print(f"Error: {error_data.get('error', 'Unknown error')}")
            except:
                print(f"Error: HTTP {response.status_code}")

    except Exception as e:
        print(f"Connection Error: {str(e)}")

print("\n" + "=" * 50)
print("Test completed.")