import os
import json
import unittest
from unittest.mock import patch, MagicMock
from app import app, get_bot_status, cleanup_bot_process

class TestWebDashboard(unittest.TestCase):
    def setUp(self):
        # Configure app for testing
        app.config['TESTING'] = True
        self.client = app.test_client()
        
        # Backup env if exists
        self.env_backup_path = ".env.test_backup"
        if os.path.exists(".env"):
            os.rename(".env", self.env_backup_path)

    def tearDown(self):
        # Restore env if backup exists
        if os.path.exists(".env"):
            os.remove(".env")
        if os.path.exists(self.env_backup_path):
            os.rename(self.env_backup_path, ".env")
            
        # Ensure cleanup is run
        cleanup_bot_process()

    def test_dashboard_homepage(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        # Check that it loads HTML content
        self.assertIn(b'<!DOCTYPE html>', response.data)
        self.assertIn(b'robTrader', response.data)

    def test_api_status(self):
        response = self.client.get('/api/status')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('bot_status', data)
        self.assertIn('portfolio', data)
        self.assertEqual(data['bot_status'], 'stopped')

    def test_api_config_get_and_post(self):
        # 1. Test POST config saving
        test_config = {
            'ALPACA_API_KEY_ID': 'TEST_KEY',
            'ALPACA_SECRET_KEY': 'TEST_SECRET',
            'ALPACA_ENV': 'paper',
            'DEFAULT_TRADING_SYMBOLS': 'AAPL,BTCUSD',
            'DYNAMIC_SCAN': 'True',
            'DYNAMIC_STOCK_LIMIT': '10',
            'BUY_THRESHOLD': '0.10',
            'SELL_THRESHOLD': '-0.10',
            'PORTFOLIO_REFRESH_SECS': '20',
            'REANALYZE_INTERVAL_MINS': '30',
            'MAX_POSITION_SIZE_PCT': '0.05',
            'DAILY_LOSS_LIMIT_PCT': '0.03'
        }
        
        response_post = self.client.post(
            '/api/config',
            data=json.dumps(test_config),
            content_type='application/json'
        )
        self.assertEqual(response_post.status_code, 200)
        res_data = json.loads(response_post.data)
        self.assertEqual(res_data['status'], 'success')
        
        # 2. Test GET config retrieving
        response_get = self.client.get('/api/config')
        self.assertEqual(response_get.status_code, 200)
        config_retrieved = json.loads(response_get.data)
        
        self.assertEqual(config_retrieved['ALPACA_API_KEY_ID'], 'TEST_KEY')
        self.assertEqual(config_retrieved['DEFAULT_TRADING_SYMBOLS'], 'AAPL,BTCUSD')
        self.assertEqual(config_retrieved['DYNAMIC_SCAN'], 'True')
        self.assertEqual(config_retrieved['BUY_THRESHOLD'], '0.10')

    @patch('subprocess.Popen')
    def test_api_control_start_stop(self, mock_popen):
        # Mock subprocess spawn
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # None indicates process is running
        mock_popen.return_value = mock_proc
        
        # 1. Start Bot
        response_start = self.client.post(
            '/api/control',
            data=json.dumps({'action': 'start'}),
            content_type='application/json'
        )
        self.assertEqual(response_start.status_code, 200)
        self.assertEqual(get_bot_status(), 'running')
        
        # 2. Try starting again (should reject)
        response_start_again = self.client.post(
            '/api/control',
            data=json.dumps({'action': 'start'}),
            content_type='application/json'
        )
        self.assertEqual(response_start_again.status_code, 400)
        
        # 3. Stop Bot
        response_stop = self.client.post(
            '/api/control',
            data=json.dumps({'action': 'stop'}),
            content_type='application/json'
        )
        self.assertEqual(response_stop.status_code, 200)
        self.assertEqual(get_bot_status(), 'stopped')

    def test_api_trades(self):
        response = self.client.get('/api/trades')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(json.loads(response.data), list)

    def test_api_logs(self):
        response = self.client.get('/api/logs')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(json.loads(response.data), list)

    def test_api_alpaca_orders(self):
        response = self.client.get('/api/alpaca_orders')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(json.loads(response.data), list)

    def test_api_analysis(self):
        response = self.client.get('/api/analysis')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('buy_threshold', data)
        self.assertIn('sell_threshold', data)
        self.assertIn('evaluations', data)

    def test_api_portfolio_history(self):
        response = self.client.get('/api/portfolio_history')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('history', data)
        self.assertIn('daily', data)
        self.assertIn('global', data)
        self.assertIn('difference', data['daily'])
        self.assertIn('percentage', data['daily'])
        self.assertIn('difference', data['global'])
        self.assertIn('percentage', data['global'])

    def test_api_tax_download(self):
        response = self.client.get('/api/tax/download')
        self.assertIn(response.status_code, [200, 404])

    def test_api_trades_download(self):
        response = self.client.get('/api/trades/download')
        self.assertIn(response.status_code, [200, 404])

if __name__ == '__main__':
    unittest.main()
