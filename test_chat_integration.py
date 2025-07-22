#!/usr/bin/env python3
"""
Test script for the free chat / market chat integration
Tests the flow from anonymous chat -> limit reached -> market chat for authenticated users
"""

import json
import requests
import time

# Configuration
BASE_URL = "http://localhost:5000"
CHAT_ENDPOINT = f"{BASE_URL}/api/chat"
MARKET_CHAT_ENDPOINT = f"{BASE_URL}/api/market/chat"

def test_anonymous_chat_session_creation():
    """Test anonymous chat session creation"""
    print("Testing anonymous chat session creation...")
    
    response = requests.post(CHAT_ENDPOINT, json={})
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code == 200:
        data = response.json()
        session_id = data.get('session_id')
        print(f"✅ Session created: {session_id}")
        return session_id
    else:
        print(f"❌ Failed to create session: {response.status_code}")
        return None

def test_anonymous_chat_messages(session_id, num_messages=6):
    """Test sending messages until limit is reached"""
    print(f"\nTesting anonymous chat with {num_messages} messages...")
    
    for i in range(1, num_messages + 1):
        message = f"Test message {i}: What is the current market trend?"
        
        response = requests.post(CHAT_ENDPOINT, json={
            "session_id": session_id,
            "message": message,
            "model": "openrouter"
        })
        
        print(f"\nMessage {i}:")
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Remaining messages: {data.get('remaining_messages', 'N/A')}")
            print(f"Login required: {data.get('login_required', False)}")
            print(f"Response: {data.get('response', 'No response')[:100]}...")
        elif response.status_code == 403:
            data = response.json()
            print(f"❌ Limit reached: {data}")
            print("✅ Anonymous limit working correctly!")
            break
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            break
        
        time.sleep(1)  # Brief pause between requests

def test_market_chat_authenticated():
    """Test market chat endpoint (requires authentication)"""
    print("\nTesting market chat endpoint...")
    
    # This should fail without authentication
    response = requests.post(MARKET_CHAT_ENDPOINT, json={
        "query": "What are the top performing stocks today?",
        "model": "openrouter"
    })
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 401:
        print("✅ Market chat correctly requires authentication")
    else:
        print(f"❌ Expected 401, got {response.status_code}")
        print(f"Response: {response.text}")

def main():
    """Run integration tests"""
    print("=" * 60)
    print("CHAT INTEGRATION TEST")
    print("=" * 60)
    
    # Test 1: Create anonymous session
    session_id = test_anonymous_chat_session_creation()
    
    if session_id:
        # Test 2: Send messages until limit reached
        test_anonymous_chat_messages(session_id)
    
    # Test 3: Verify market chat requires auth
    test_market_chat_authenticated()
    
    print("\n" + "=" * 60)
    print("INTEGRATION TEST COMPLETE")
    print("=" * 60)
    print("\nTo run this test:")
    print("1. Start the Flask server: python run.py")
    print("2. Run this test: python test_chat_integration.py")

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("❌ Connection error: Make sure the Flask server is running on http://localhost:5000")
    except Exception as e:
        print(f"❌ Test error: {e}")