"""
Risk Calculator Phase 1 - Test Script

This script tests all endpoints of the Risk Calculator Phase 1 API.
Run this after starting the Flask server to verify everything works.

Usage:
    python test_risk_calculator.py

Requirements:
    pip install requests colorama
"""

import requests
import json
import sys
from datetime import datetime
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Configuration
BASE_URL = "http://localhost:8000"
TEST_USER = {
    "email": "test@welthwest.com",
    "password": "Test@123"
}

# Test results
test_results = []


def print_header(text):
    """Print a formatted header"""
    print(f"\n{Fore.CYAN}{'=' * 70}")
    print(f"{Fore.CYAN}{text}")
    print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")


def print_test(test_name, passed, message=""):
    """Print test result"""
    status = f"{Fore.GREEN}✓ PASS" if passed else f"{Fore.RED}✗ FAIL"
    print(f"{status}{Style.RESET_ALL} - {test_name}")
    if message:
        print(f"  {Fore.YELLOW}{message}{Style.RESET_ALL}")
    test_results.append({"test": test_name, "passed": passed, "message": message})


def print_response(response_data, indent=2):
    """Print formatted JSON response"""
    print(f"{Fore.WHITE}{json.dumps(response_data, indent=indent)}{Style.RESET_ALL}")


def test_health_check():
    """Test 1: Health Check Endpoint"""
    print_header("Test 1: Health Check")

    try:
        response = requests.get(f"{BASE_URL}/api/risk-calculator/health", timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('status') == 'operational':
                print_test("Health Check", True, "Service is operational")
                print_response(data)
                return True
            else:
                print_test("Health Check", False, "Unexpected response format")
                return False
        else:
            print_test("Health Check", False, f"Status code: {response.status_code}")
            return False

    except Exception as e:
        print_test("Health Check", False, f"Error: {str(e)}")
        return False


def get_jwt_token():
    """Login and get JWT token"""
    print_header("Getting JWT Token")

    try:
        # First try to register (in case user doesn't exist)
        # This might fail if user exists, which is fine
        try:
            requests.post(
                f"{BASE_URL}/api/auth/register",
                json=TEST_USER,
                timeout=5
            )
        except:
            pass

        # Now login
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_USER,
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token')
            if token:
                print_test("JWT Token Retrieval", True, "Successfully obtained token")
                return token
            else:
                print_test("JWT Token Retrieval", False, "No access_token in response")
                return None
        else:
            print_test("JWT Token Retrieval", False, f"Login failed: {response.status_code}")
            print(f"{Fore.YELLOW}Note: Update TEST_USER credentials in script if needed{Style.RESET_ALL}")
            return None

    except Exception as e:
        print_test("JWT Token Retrieval", False, f"Error: {str(e)}")
        return None


def test_calculate_position(jwt_token):
    """Test 2: Calculate Position & Costs"""
    print_header("Test 2: Calculate Position & Costs (Delivery)")

    if not jwt_token:
        print_test("Calculate Position", False, "No JWT token available")
        return False

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "symbol": "RELIANCE",
        "trade_type": "delivery",
        "buy_price": 2500,
        "stop_loss_price": 2450,
        "target_price": 2600,
        "capital_available": 100000,
        "max_risk_per_trade": 2,
        "max_risk_type": "percentage",
        "broker": "zerodha"
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/risk-calculator/calculate",
            headers=headers,
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()

            if data.get('success'):
                result = data.get('data', {})

                # Validate key fields
                position_sizing = result.get('position_sizing', {})
                risk_analysis = result.get('risk_analysis', {})

                max_qty = position_sizing.get('max_quantity')
                risk_amount = risk_analysis.get('risk_amount')

                if max_qty and risk_amount:
                    print_test("Calculate Position", True,
                              f"Max Quantity: {max_qty}, Risk: ₹{risk_amount}")

                    # Print key results
                    print(f"\n{Fore.GREEN}Key Results:{Style.RESET_ALL}")
                    print(f"  Symbol: {result.get('symbol')}")
                    print(f"  Max Quantity: {max_qty} shares")
                    print(f"  Position Value: ₹{position_sizing.get('position_value'):,.2f}")
                    print(f"  Risk Amount: ₹{risk_amount:,.2f}")
                    print(f"  Risk:Reward: {result.get('risk_reward', {}).get('ratio_text')}")

                    costs = result.get('cost_breakdown', {}).get('estimated_costs_at_entry', {})
                    print(f"  Total Costs: ₹{costs.get('total_cost', 0):.2f}")
                    print(f"  Breakeven: ₹{result.get('scenario_analysis', {}).get('breakeven_price')}")

                    return True
                else:
                    print_test("Calculate Position", False, "Missing key fields in response")
                    return False
            else:
                print_test("Calculate Position", False, data.get('error', 'Unknown error'))
                return False
        else:
            print_test("Calculate Position", False, f"Status code: {response.status_code}")
            print_response(response.json() if response.text else {})
            return False

    except Exception as e:
        print_test("Calculate Position", False, f"Error: {str(e)}")
        return False


def test_intraday_calculation(jwt_token):
    """Test 3: Intraday Trade Calculation"""
    print_header("Test 3: Intraday Trade Calculation")

    if not jwt_token:
        print_test("Intraday Calculation", False, "No JWT token available")
        return False

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "symbol": "TCS",
        "trade_type": "intraday",
        "buy_price": 3500,
        "stop_loss_price": 3475,
        "target_price": 3550,
        "capital_available": 50000,
        "max_risk_per_trade": 1000,
        "max_risk_type": "rupees",
        "broker": "zerodha"
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/risk-calculator/calculate",
            headers=headers,
            json=payload,
            timeout=10
        )

        if response.status_code == 200 and response.json().get('success'):
            data = response.json()['data']
            print_test("Intraday Calculation", True,
                      f"Calculated for {data['symbol']} - {data['trade_type']}")

            # Verify intraday-specific costs
            costs = data['cost_breakdown']['estimated_costs_at_entry']
            print(f"  STT (intraday): ₹{costs.get('stt_ctt', 0):.2f}")
            return True
        else:
            print_test("Intraday Calculation", False, "Request failed")
            return False

    except Exception as e:
        print_test("Intraday Calculation", False, f"Error: {str(e)}")
        return False


def test_fno_calculation(jwt_token):
    """Test 4: F&O Trade Calculation"""
    print_header("Test 4: F&O Trade Calculation")

    if not jwt_token:
        print_test("F&O Calculation", False, "No JWT token available")
        return False

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "symbol": "NIFTY",
        "trade_type": "fno",
        "buy_price": 21500,
        "stop_loss_price": 21400,
        "target_price": 21700,
        "capital_available": 200000,
        "max_risk_per_trade": 3,
        "max_risk_type": "percentage",
        "broker": "upstox"
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/risk-calculator/calculate",
            headers=headers,
            json=payload,
            timeout=10
        )

        if response.status_code == 200 and response.json().get('success'):
            data = response.json()['data']
            print_test("F&O Calculation", True,
                      f"Calculated for {data['symbol']} F&O")

            # Verify F&O flat brokerage
            costs = data['cost_breakdown']['estimated_costs_at_entry']
            print(f"  Brokerage (F&O): ₹{costs.get('brokerage', 0):.2f}")
            return True
        else:
            print_test("F&O Calculation", False, "Request failed")
            return False

    except Exception as e:
        print_test("F&O Calculation", False, f"Error: {str(e)}")
        return False


def test_get_brokers(jwt_token):
    """Test 5: Get Available Brokers"""
    print_header("Test 5: Get Available Brokers")

    if not jwt_token:
        print_test("Get Brokers", False, "No JWT token available")
        return False

    headers = {"Authorization": f"Bearer {jwt_token}"}

    try:
        response = requests.get(
            f"{BASE_URL}/api/risk-calculator/brokers",
            headers=headers,
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('brokers'):
                brokers = data['brokers']
                print_test("Get Brokers", True, f"Found {len(brokers)} brokers")

                for broker in brokers:
                    print(f"  - {broker['name']}")

                return True
            else:
                print_test("Get Brokers", False, "Invalid response")
                return False
        else:
            print_test("Get Brokers", False, f"Status code: {response.status_code}")
            return False

    except Exception as e:
        print_test("Get Brokers", False, f"Error: {str(e)}")
        return False


def test_validate_trade(jwt_token):
    """Test 6: Validate Trade Parameters"""
    print_header("Test 6: Validate Trade Parameters")

    if not jwt_token:
        print_test("Validate Trade", False, "No JWT token available")
        return False

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "buy_price": 2500,
        "stop_loss_price": 2450,
        "target_price": 2600,
        "capital_available": 100000,
        "max_risk_per_trade": 2,
        "max_risk_type": "percentage"
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/risk-calculator/validate-trade",
            headers=headers,
            json=payload,
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                validation = data.get('validation', {})
                is_valid = validation.get('is_valid')

                print_test("Validate Trade", True,
                          f"Valid: {is_valid}, Errors: {len(validation.get('errors', []))}")

                if validation.get('quick_estimate'):
                    est = validation['quick_estimate']
                    print(f"  Estimated Quantity: {est['estimated_quantity']}")

                return True
            else:
                print_test("Validate Trade", False, "Invalid response")
                return False
        else:
            print_test("Validate Trade", False, f"Status code: {response.status_code}")
            return False

    except Exception as e:
        print_test("Validate Trade", False, f"Error: {str(e)}")
        return False


def test_cost_breakdown(jwt_token):
    """Test 7: Get Cost Breakdown"""
    print_header("Test 7: Get Cost Breakdown")

    if not jwt_token:
        print_test("Cost Breakdown", False, "No JWT token available")
        return False

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "trade_type": "delivery",
        "broker": "zerodha",
        "buy_price": 2500,
        "sell_price": 2600,
        "quantity": 10
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/risk-calculator/cost-breakdown",
            headers=headers,
            json=payload,
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                costs = data['data']['cost_breakdown']
                pl = data['data']['profit_loss']

                print_test("Cost Breakdown", True,
                          f"Total Cost: ₹{costs['total_cost']:.2f}, Net P&L: ₹{pl['net_pl']:.2f}")

                print(f"  Brokerage: ₹{costs.get('brokerage', 0):.2f}")
                print(f"  STT: ₹{costs.get('stt_ctt', 0):.2f}")
                print(f"  Exchange Charge: ₹{costs.get('exchange_txn_charge', 0):.2f}")
                print(f"  GST: ₹{costs.get('gst', 0):.2f}")
                print(f"  Breakeven: ₹{data['data']['breakeven_price']}")

                return True
            else:
                print_test("Cost Breakdown", False, "Invalid response")
                return False
        else:
            print_test("Cost Breakdown", False, f"Status code: {response.status_code}")
            return False

    except Exception as e:
        print_test("Cost Breakdown", False, f"Error: {str(e)}")
        return False


def test_error_handling(jwt_token):
    """Test 8: Error Handling"""
    print_header("Test 8: Error Handling")

    if not jwt_token:
        print_test("Error Handling", False, "No JWT token available")
        return False

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    # Test with invalid stop loss (above buy price)
    payload = {
        "symbol": "TEST",
        "trade_type": "delivery",
        "buy_price": 2500,
        "stop_loss_price": 2600,  # Invalid: SL > Buy
        "capital_available": 100000,
        "max_risk_per_trade": 2,
        "max_risk_type": "percentage",
        "broker": "zerodha"
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/risk-calculator/calculate",
            headers=headers,
            json=payload,
            timeout=5
        )

        # Should get 400 error
        if response.status_code == 400:
            data = response.json()
            error = data.get('error', '')

            if 'stop loss' in error.lower():
                print_test("Error Handling", True, "Correctly caught invalid stop loss")
                print(f"  Error message: {error}")
                return True
            else:
                print_test("Error Handling", False, "Wrong error message")
                return False
        else:
            print_test("Error Handling", False,
                      f"Expected 400, got {response.status_code}")
            return False

    except Exception as e:
        print_test("Error Handling", False, f"Error: {str(e)}")
        return False


def print_summary():
    """Print test summary"""
    print_header("Test Summary")

    total = len(test_results)
    passed = sum(1 for r in test_results if r['passed'])
    failed = total - passed

    print(f"\n{Fore.WHITE}Total Tests: {total}")
    print(f"{Fore.GREEN}Passed: {passed}")
    print(f"{Fore.RED}Failed: {failed}")

    if failed > 0:
        print(f"\n{Fore.RED}Failed Tests:{Style.RESET_ALL}")
        for result in test_results:
            if not result['passed']:
                print(f"  - {result['test']}: {result['message']}")

    success_rate = (passed / total * 100) if total > 0 else 0
    print(f"\n{Fore.CYAN}Success Rate: {success_rate:.1f}%{Style.RESET_ALL}")

    if success_rate == 100:
        print(f"\n{Fore.GREEN}🎉 All tests passed! Risk Calculator Phase 1 is working correctly.{Style.RESET_ALL}")
    elif success_rate >= 80:
        print(f"\n{Fore.YELLOW}⚠️  Most tests passed, but some issues need attention.{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.RED}❌ Many tests failed. Please check the server and configuration.{Style.RESET_ALL}")


def main():
    """Run all tests"""
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}")
    print("=" * 70)
    print("  RISK CALCULATOR PHASE 1 - TEST SUITE")
    print("  WelthWest Backend API Testing")
    print("=" * 70)
    print(f"{Style.RESET_ALL}")
    print(f"Base URL: {BASE_URL}")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Run tests
    test_health_check()
    jwt_token = get_jwt_token()

    if jwt_token:
        test_calculate_position(jwt_token)
        test_intraday_calculation(jwt_token)
        test_fno_calculation(jwt_token)
        test_get_brokers(jwt_token)
        test_validate_trade(jwt_token)
        test_cost_breakdown(jwt_token)
        test_error_handling(jwt_token)
    else:
        print(f"\n{Fore.RED}Cannot proceed with tests - JWT token unavailable{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Please ensure:")
        print("  1. Server is running")
        print("  2. MongoDB is connected")
        print("  3. User registration/login is working")
        print(f"  4. Update TEST_USER credentials if needed{Style.RESET_ALL}")

    # Print summary
    print_summary()

    print(f"\n{Fore.CYAN}End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}Tests interrupted by user{Style.RESET_ALL}\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n{Fore.RED}Unexpected error: {str(e)}{Style.RESET_ALL}\n")
        sys.exit(1)
