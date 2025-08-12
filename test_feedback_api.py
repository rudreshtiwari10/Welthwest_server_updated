import requests
import json
from datetime import datetime

# Test configuration
BASE_URL = "http://localhost:8000"
FEEDBACK_ENDPOINT = f"{BASE_URL}/api/feedback/submit"

def test_feedback_submission():
    """Test the feedback API endpoint"""
    
    # Sample feedback data with dynamic questions and answers
    test_feedback = {
        "user_info": {
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "+1234567890"
        },
        "form_type": "Product Feedback",
        "responses": [
            {
                "question": "How would you rate our service overall?",
                "answer": "Excellent",
                "question_type": "rating",
                "options": ["Poor", "Fair", "Good", "Very Good", "Excellent"]
            },
            {
                "question": "What features do you like most?",
                "answer": "The AI analysis and backtesting tools are fantastic!",
                "question_type": "text"
            },
            {
                "question": "Which plan are you currently using?",
                "answer": "Pro Plan",
                "question_type": "single_choice",
                "options": ["Free", "Basic", "Pro", "Enterprise"]
            },
            {
                "question": "What improvements would you suggest?",
                "answer": "More technical indicators and better mobile experience",
                "question_type": "textarea"
            },
            {
                "question": "Would you recommend us to others?",
                "answer": "Yes",
                "question_type": "boolean",
                "options": ["Yes", "No"]
            }
        ],
        "form_metadata": {
            "version": "1.0",
            "created_by": "feedback_form_builder",
            "form_title": "Product Experience Survey"
        }
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
                "responses": [{"question": "Test?", "answer": "Yes"}]
            }
        },
        {
            "name": "Missing user name",
            "data": {
                "user_info": {"email": "test@example.com"},
                "responses": [{"question": "Test?", "answer": "Yes"}]
            }
        },
        {
            "name": "Empty responses",
            "data": {
                "user_info": {"name": "John Doe", "email": "test@example.com"},
                "responses": []
            }
        },
        {
            "name": "Invalid responses format",
            "data": {
                "user_info": {"name": "John Doe", "email": "test@example.com"},
                "responses": "invalid_format"
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