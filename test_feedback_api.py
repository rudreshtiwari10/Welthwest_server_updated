import requests
import json
from datetime import datetime

# Test configuration
BASE_URL = "http://localhost:8000"
FEEDBACK_ENDPOINT = f"{BASE_URL}/api/feedback/submit"

def test_feedback_submission():
    """Test the feedback API endpoint"""
    
    # Sample WealthWest feedback data with 4 specific questions
    test_feedback = {
        "user_info": {
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "+1234567890"
        },
        "trading_learning": "Yes, WealthWest has been very helpful for learning trading. The educational resources and tutorials are comprehensive. I would love to see more advanced options strategies and risk management guides.",
        "ai_features": "The AI features are quite effective. The backtesting tool helped me validate my strategies before going live. The sentiment analysis provides good market insights. I'd suggest improving the signal accuracy and adding more technical indicators.",
        "interface_usability": "The interface is generally user-friendly. The dashboards are clean and informative. The strategy builder is intuitive. However, the mobile app could be more responsive, and some features take time to load.",
        "value_recommendation": "WealthWest provides good value for money. I'm currently on the Pro tier (Rs 999) and find it worth the investment. I would definitely recommend it to other traders. The Enterprise tier features look promising but might be expensive for individual traders."
    }
    
    print("Testing feedback API submission...")
    print(f"Endpoint: {FEEDBACK_ENDPOINT}")
    print(f"Test data: {json.dumps(test_feedback, indent=2)}")
    
    try:
        # Send POST request
        response = requests.post(
            FEEDBACK_ENDPOINT,
            json=test_feedback,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"\nResponse Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success! Feedback submitted successfully")
            print(f"Submission ID: {result.get('submission_id')}")
            print(f"Message: {result.get('message')}")
        else:
            print(f"❌ Error: {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error details: {error_data}")
            except:
                print(f"Error response: {response.text}")
                
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Make sure the server is running on localhost:8000")
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")

def test_invalid_feedback_submission():
    """Test feedback API with invalid data"""
    
    print("\n" + "="*50)
    print("Testing feedback API with invalid data...")
    
    # Test cases with invalid data
    test_cases = [
        {
            "name": "Missing user email",
            "data": {
                "user_info": {"name": "John Doe"},
                "trading_learning": "Great platform for learning"
            }
        },
        {
            "name": "Missing user name",
            "data": {
                "user_info": {"email": "test@example.com"},
                "trading_learning": "Great platform for learning"
            }
        },
        {
            "name": "No feedback responses",
            "data": {
                "user_info": {"name": "John Doe", "email": "test@example.com"}
            }
        },
        {
            "name": "Empty feedback responses",
            "data": {
                "user_info": {"name": "John Doe", "email": "test@example.com"},
                "trading_learning": "",
                "ai_features": "",
                "interface_usability": "",
                "value_recommendation": ""
            }
        }
    ]
    
    for test_case in test_cases:
        print(f"\nTesting: {test_case['name']}")
        
        try:
            response = requests.post(
                FEEDBACK_ENDPOINT,
                json=test_case['data'],
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 400:
                error_data = response.json()
                print(f"✅ Expected error: {error_data.get('error')}")
            else:
                print(f"❌ Unexpected response: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print("❌ Connection Error: Make sure the server is running")
        except Exception as e:
            print(f"❌ Test failed: {str(e)}")

if __name__ == "__main__":
    print("🧪 Feedback API Test Suite")
    print("="*50)
    
    # Test valid submission
    test_feedback_submission()
    
    # Test invalid submissions
    test_invalid_feedback_submission()
    
    print("\n" + "="*50)
    print("🏁 Test suite completed!")
    print("\nTo test admin endpoints, you'll need:")
    print("1. A JWT token from a user with admin role")
    print("2. Use endpoints like:")
    print(f"   GET {BASE_URL}/api/feedback/list")
    print(f"   GET {BASE_URL}/api/feedback/statistics")
    print(f"   GET {BASE_URL}/api/feedback/<submission_id>")