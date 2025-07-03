import unittest
import json
from app import create_app
import os

class StockAPITestCase(unittest.TestCase):
    def setUp(self):
        # Set environment to testing
        os.environ['FLASK_ENV'] = 'testing'
        self.app = create_app()
        self.client = self.app.test_client()

    def test_health_check(self):
        response = self.client.get('/health')
        data = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'healthy')

    def test_validate_ticker_valid(self):
        response = self.client.get('/api/validate?ticker=AAPL')
        data = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['ticker'], 'AAPL')
        self.assertTrue(data['valid'])

    def test_validate_ticker_invalid(self):
        response = self.client.get('/api/validate?ticker=INVALID_TICKER_SYMBOL')
        data = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['ticker'], 'INVALID_TICKER_SYMBOL')
        self.assertFalse(data['valid'])

    def test_historical_data(self):
        response = self.client.get('/api/historical?ticker=AAPL&period=5d&interval=1d')
        data = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['ticker'], 'AAPL')
        self.assertEqual(data['period'], '5d')
        self.assertEqual(data['interval'], '1d')
        self.assertIn('data', data)
        self.assertTrue(len(data['data']) > 0)

    def test_live_data(self):
        response = self.client.get('/api/live?tickers=AAPL')
        data = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertIn('data', data)
        self.assertIn('valid_tickers', data)
        self.assertIn('AAPL', data['valid_tickers'])

if __name__ == '__main__':
    unittest.main() 