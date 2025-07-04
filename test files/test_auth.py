import requests
import json
import time

# Base URL for API
BASE_URL = "http://localhost:8000/api"

def test_register():
    """Test user registration"""
    print("\n--- Testing User Registration ---")
    
    # Generate unique username using timestamp
    timestamp = int(time.time())
    username = f"testuser{timestamp}"
    email = f"test{timestamp}@example.com"
    
    # Test data
    data = {
        "username": username,
        "email": email,
        "password": "Password123!",
        "confirm_password": "Password123!"
    }
    
    # Make request
    response = requests.post(f"{BASE_URL}/auth/register", json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    # Check if successful
    assert response.status_code == 201
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()
    
    # Return tokens and user data for further tests
    return response.json()

def test_login(username_or_email, password="Password123!"):
    """Test user login"""
    print("\n--- Testing User Login ---")
    
    # Test data
    data = {
        "username_or_email": username_or_email,
        "password": password
    }
    
    # Make request
    response = requests.post(f"{BASE_URL}/auth/login", json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    # Check if successful
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()
    
    # Return tokens and user data
    return response.json()

def test_get_current_user(access_token):
    """Test getting current user data"""
    print("\n--- Testing Get Current User ---")
    
    # Set headers with access token
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    # Make request
    response = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    # Check if successful
    assert response.status_code == 200
    assert "user" in response.json()
    
    return response.json()

def test_update_profile(access_token):
    """Test updating user profile"""
    print("\n--- Testing Update Profile ---")
    
    # Test data
    data = {
        "first_name": "Test",
        "last_name": "User"
    }
    
    # Set headers with access token
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    # Make request
    response = requests.put(f"{BASE_URL}/auth/profile", json=data, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    # Check if successful
    assert response.status_code == 200
    assert response.json()["user"]["first_name"] == "Test"
    assert response.json()["user"]["last_name"] == "User"
    
    return response.json()

def test_refresh_token(refresh_token):
    """Test refreshing access token"""
    print("\n--- Testing Refresh Token ---")
    
    # Test data
    data = {
        "refresh_token": refresh_token
    }
    
    # Make request
    response = requests.post(f"{BASE_URL}/auth/refresh", json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    # Check if successful
    assert response.status_code == 200
    assert "access_token" in response.json()
    
    return response.json()

def test_logout(refresh_token):
    """Test user logout"""
    print("\n--- Testing Logout ---")
    
    # Test data
    data = {
        "refresh_token": refresh_token
    }
    
    # Make request
    response = requests.post(f"{BASE_URL}/auth/logout", json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    # Check if successful
    assert response.status_code == 200
    
    return response.json()

if __name__ == "__main__":
    # Run tests
    try:
        # Register a new user
        register_data = test_register()
        
        # Login with the new user
        login_data = test_login(register_data["user"]["username"])
        
        # Get current user data
        user_data = test_get_current_user(login_data["access_token"])
        
        # Update profile
        profile_data = test_update_profile(login_data["access_token"])
        
        # Refresh token
        refresh_data = test_refresh_token(login_data["refresh_token"])
        
        # Logout
        logout_data = test_logout(login_data["refresh_token"])
        
        print("\nAll tests passed successfully!")
    except Exception as e:
        print(f"\nTest failed: {str(e)}") 