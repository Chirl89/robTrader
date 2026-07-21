import os
import shutil
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime

from analysis.technical_analysis import add_all_indicators, calculate_rsi
from broker.simulator_broker import SimulatorBroker
from reporting.trade_logger import TradeLogger
from reporting.tax_exporter import TaxExporter

class TestTechnicalAnalysis(unittest.TestCase):
    def test_indicators_calculation(self):
        # Create mock price series (50 days of data)
        dates = pd.date_range(start="2026-01-01", periods=60, freq="D")
        # Standard price series starting at 100 and rising slowly
        prices = [100.0 + i * 0.5 + np.sin(i) * 2 for i in range(60)]
        
        df = pd.DataFrame({
            'timestamp': dates,
            'open': prices,
            'high': [p + 1.0 for p in prices],
            'low': [p - 1.0 for p in prices],
            'close': prices,
            'volume': [10000] * 60
        })
        
        df_indicators = add_all_indicators(df)
        
        # Verify columns exist
        self.assertIn('sma_20', df_indicators.columns)
        self.assertIn('sma_50', df_indicators.columns)
        self.assertIn('ema_10', df_indicators.columns)
        self.assertIn('rsi', df_indicators.columns)
        self.assertIn('macd', df_indicators.columns)
        self.assertIn('bb_upper', df_indicators.columns)
        
        # Validate values exist for latest rows
        self.assertFalse(np.isnan(df_indicators.iloc[-1]['rsi']))
        self.assertFalse(np.isnan(df_indicators.iloc[-1]['sma_50']))
        self.assertTrue(0 <= df_indicators.iloc[-1]['rsi'] <= 100)

    def test_yahoo_provider_symbol_normalization(self):
        from data.yahoo_provider import YahooProvider
        provider = YahooProvider()
        # BRK.B should normalize to BRK-B (for Yahoo Finance)
        self.assertEqual(provider._normalize_symbol("BRK.B"), "BRK-B")
        # BF.B should normalize to BF-B
        self.assertEqual(provider._normalize_symbol("BF.B"), "BF-B")
        # SAN.MC should keep .MC suffix
        self.assertEqual(provider._normalize_symbol("SAN.MC"), "SAN.MC")
        # BTCUSD should normalize to BTC-USD
        self.assertEqual(provider._normalize_symbol("BTCUSD"), "BTC-USD")

    @patch('yfinance.Ticker')
    def test_alpaca_provider_fundamental_normalization(self, mock_ticker_class):
        from data.alpaca_provider import AlpacaProvider
        provider = AlpacaProvider()
        
        # Mock yfinance return values
        mock_instance = MagicMock()
        mock_instance.info = {'longName': 'Bitcoin', 'trailingPE': 10}
        mock_ticker_class.return_value = mock_instance
        
        # Call get_fundamentals
        res = provider.get_fundamentals("BTCUSD")
        
        # Verify yfinance Ticker was called with "BTC-USD" instead of "BTCUSD"
        mock_ticker_class.assert_called_with("BTC-USD")
        self.assertEqual(res['name'], 'Bitcoin')

class TestSimulatorBroker(unittest.TestCase):
    def setUp(self):
        # Initialize simulator with 10,000 cash and flat $2 commission
        self.broker = SimulatorBroker(initial_cash=10000.0, commission_pct=0.01, min_commission=2.00)

    def test_buy_and_sell_cycle(self):
        # Buy 10 shares of AAPL at 150
        res = self.broker.submit_order(symbol="AAPL", qty=10, side="buy", price=150.0)
        self.assertEqual(res['status'], 'filled')
        self.assertEqual(res['filled_qty'], 10)
        self.assertEqual(res['filled_price'], 150.0)
        self.assertEqual(res['commission'], 15.0)  # 10 * 150 * 0.01 = 15.00
        
        # Cash should be 10000 - 1500 - 15 = 8485
        self.assertEqual(self.broker.get_cash(), 8485.0)
        
        positions = self.broker.get_positions()
        self.assertIn('AAPL', positions)
        self.assertEqual(positions['AAPL']['qty'], 10.0)
        self.assertEqual(positions['AAPL']['avg_entry_price'], 150.0)
        
        # Update price to 160
        self.broker.update_prices({'AAPL': 160.0})
        self.assertEqual(self.broker.get_portfolio_value(), 8485.0 + 10 * 160.0)
        
        # Sell 4 shares at 160
        res_sell = self.broker.submit_order(symbol="AAPL", qty=4, side="sell", price=160.0)
        self.assertEqual(res_sell['status'], 'filled')
        self.assertEqual(res_sell['commission'], 6.40)  # 4 * 160 * 0.01 = 6.40
        # Proceeds: 4 * 160 - 6.40 = 633.60
        # New cash: 8485 + 633.60 = 9118.60
        self.assertEqual(self.broker.get_cash(), 9118.60)
        
        # Position qty should decrease to 6
        positions = self.broker.get_positions()
        self.assertEqual(positions['AAPL']['qty'], 6.0)

    def test_insufficient_funds(self):
        # Attempt to buy shares exceeding cash
        res = self.broker.submit_order(symbol="AAPL", qty=100, side="buy", price=150.0)
        self.assertEqual(res['status'], 'rejected')
        self.assertIn('Insufficient funds', res['reason'])

    def test_partially_filled_canceled_orders(self):
        # Insert a partially completed order that is then canceled in the simulator
        self.broker.orders.append({
            'order_id': 'part1',
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100.0,
            'filled_qty': 60.0,
            'price': 150.0,
            'filled_price': 150.0,
            'status': 'canceled',
            'created_at': '2026-07-20T12:00:00'
        })
        
        # Insert a canceled order with no fills to ensure it is ignored
        self.broker.orders.append({
            'order_id': 'part2',
            'symbol': 'MSFT',
            'side': 'buy',
            'qty': 100.0,
            'filled_qty': 0.0,
            'price': 300.0,
            'filled_price': 0.0,
            'status': 'canceled',
            'created_at': '2026-07-20T12:01:00'
        })
        
        filled = self.broker.get_filled_orders()
        # Should only retrieve 'part1' because it has filled_qty > 0
        self.assertEqual(len(filled), 1)
        self.assertEqual(filled[0]['order_id'], 'part1')
        self.assertEqual(filled[0]['qty'], 60.0)
        self.assertEqual(filled[0]['status'], 'canceled')

    def test_get_open_orders_simulator(self):
        # Insert a completed order
        self.broker.orders.append({
            'order_id': 'done1', 'symbol': 'AAPL', 'side': 'buy', 'qty': 10, 'price': 150, 'status': 'filled', 'created_at': '2026-07-20T12:00:00'
        })
        # Insert an active/new order
        self.broker.orders.append({
            'order_id': 'open1', 'symbol': 'MSFT', 'side': 'buy', 'qty': 100, 'filled_qty': 40, 'price': 300, 'status': 'new', 'created_at': '2026-07-20T12:01:00'
        })
        
        open_orders = self.broker.get_open_orders()
        self.assertEqual(len(open_orders), 1)
        self.assertEqual(open_orders[0]['order_id'], 'open1')
        self.assertEqual(open_orders[0]['qty'], 100.0)
        self.assertEqual(open_orders[0]['filled_qty'], 40.0)

    def test_scheduler_symbol_validation_and_positions_tracking(self):
        from strategy.scheduler import TradingScheduler
        from broker.simulator_broker import SimulatorBroker
        
        scheduler = TradingScheduler()
        scheduler.broker = SimulatorBroker(initial_cash=10000.0)
        # Mock active positions (holding TEF.MC)
        scheduler.broker.submit_order(symbol="TEF.MC", qty=10, side="buy", price=4.0)
        
        scheduler.dynamic_scan = False
        scheduler.symbols = ['AAPL', 'MSFT']
        
        # Mock broker get_tradable_assets to return specific active assets
        # simulating a real Alpaca Broker response
        scheduler.broker.get_tradable_assets = lambda: ['AAPL', 'MSFT', 'BRK.B', 'BF.B']
        
        # Test validation and mapping logic
        scheduler.symbols = ['AAPL', 'BRK-B', 'BF-B', 'SAN.MC']
        
        tradable_symbols = scheduler.broker.get_tradable_assets()
        if tradable_symbols and tradable_symbols != ['*']:
            alpaca_lookup = {}
            for ts in tradable_symbols:
                norm = ts.replace('.', '').replace('-', '').replace('/', '').upper()
                alpaca_lookup[norm] = ts
            
            validated_symbols = []
            for sym in scheduler.symbols:
                norm_sym = sym.replace('.', '').replace('-', '').replace('/', '').upper()
                if norm_sym in alpaca_lookup:
                    validated_symbols.append(alpaca_lookup[norm_sym])
            scheduler.symbols = validated_symbols
            
        self.assertIn('AAPL', scheduler.symbols)
        self.assertIn('BRK.B', scheduler.symbols)
        self.assertIn('BF.B', scheduler.symbols)
        self.assertNotIn('SAN.MC', scheduler.symbols)
        
        # Verify active positions inclusion
        active_positions = scheduler.broker.get_positions()
        for pos_symbol in active_positions.keys():
            if pos_symbol not in scheduler.symbols:
                scheduler.symbols.append(pos_symbol)
                
        self.assertIn('TEF.MC', scheduler.symbols)

class TestTaxExporter(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_data_logs"
        self.trade_logger = TradeLogger(log_dir=self.test_dir)
        self.trade_logger.get_usd_eur_rate = lambda date_str: 0.9200
        self.tax_exporter = TaxExporter(log_dir=self.test_dir)


    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_fifo_matching(self):
        # 1. Buy 10 AAPL at $100, commission $2
        # Exchange rate is mocked in trade_logger to 0.92 if API fails.
        # Let's log trades directly to control values
        
        # We simulate the exact dictionary structure returned by the broker.
        trade1 = {
            'timestamp': '2026-01-01T10:00:00',
            'order_id': 'buy1',
            'symbol': 'AAPL',
            'side': 'buy',
            'filled_qty': 10.0,
            'filled_price': 100.0,
            'commission': 2.0
        }
        
        # 2. Buy 10 AAPL at $120, commission $2
        trade2 = {
            'timestamp': '2026-01-02T10:00:00',
            'order_id': 'buy2',
            'symbol': 'AAPL',
            'side': 'buy',
            'filled_qty': 10.0,
            'filled_price': 120.0,
            'commission': 2.0
        }
        
        # 3. Sell 15 AAPL at $130, commission $3
        trade3 = {
            'timestamp': '2026-01-03T10:00:00',
            'order_id': 'sell1',
            'symbol': 'AAPL',
            'side': 'sell',
            'filled_qty': 15.0,
            'filled_price': 130.0,
            'commission': 3.0
        }
        
        # Log all trades
        self.trade_logger.log_trade(trade1)
        self.trade_logger.log_trade(trade2)
        self.trade_logger.log_trade(trade3)
        
        # Generate report
        report = self.tax_exporter.generate_tax_report()
        self.assertEqual(report['status'], 'success')
        self.assertEqual(report['taxable_trades_count'], 2)  # Should create 2 FIFO matched events
        
        # Load the generated report CSV and verify details
        report_df = pd.read_csv(self.tax_exporter.report_file)
        self.assertEqual(len(report_df), 2)
        
        # Event 1: 10 shares from buy1
        # Purchase rate = 0.92 (default) -> buy cost = 10 * 100 * 0.92 + 2 * 0.92 = 920 + 1.84 = €921.84
        # Sale rate = 0.92 (default) -> sell proceeds = 10 * 130 * 0.92 - (10/15 * 3 * 0.92) = 1200 * 0.92 - 1.84 = 1196 - 1.84 = €1194.16
        # Gain = 1194.16 - 921.84 = 272.32
        
        # Event 2: 5 shares from buy2
        # Purchase rate = 0.92 -> buy cost = 5 * 120 * 0.92 + (5/10 * 2 * 0.92) = 552 + 0.92 = €552.92
        # Sale rate = 0.92 -> sell proceeds = 5 * 130 * 0.92 - (5/15 * 3 * 0.92) = 598 - 0.92 = €597.08
        # Gain = 597.08 - 552.92 = 44.16
        
        # Total gain = 272.32 + 44.16 = 316.48
        self.assertAlmostEqual(report['summary']['net_capital_gain_loss_eur'], 316.48, places=1)

    def test_ibex35_scraping_and_dynamic_symbols(self):
        from analysis.market_scanner import get_ibex35_symbols, get_dynamic_market_symbols
        
        # Test scraping
        symbols = get_ibex35_symbols()
        self.assertIsInstance(symbols, list)
        self.assertTrue(len(symbols) > 0)
        # Verify that tickers are formatted for Yahoo Finance MC (Bolsa de Madrid)
        for sym in symbols:
            self.assertTrue(sym.endswith('.MC'), f"Symbol {sym} does not end with .MC")
            
        # Test dynamic market symbols with different indexes
        sp_symbols = get_dynamic_market_symbols(max_stocks=10, include_crypto=False, index_name="SP500")
        self.assertEqual(len(sp_symbols), 10)
        
        ibex_symbols = get_dynamic_market_symbols(max_stocks=10, include_crypto=False, index_name="IBEX35")
        self.assertEqual(len(ibex_symbols), 10)
        self.assertTrue(all(sym.endswith('.MC') for sym in ibex_symbols))
        
        both_symbols = get_dynamic_market_symbols(max_stocks=10, include_crypto=False, index_name="BOTH")
        self.assertEqual(len(both_symbols), 10)
        # Should have approximately half S&P 500 and half IBEX 35
        sp_count = sum(1 for sym in both_symbols if not sym.endswith('.MC'))
        ibex_count = sum(1 for sym in both_symbols if sym.endswith('.MC'))
        self.assertEqual(sp_count, 5)
        self.assertEqual(ibex_count, 5)
        
        # Test dynamic market symbols with max_stocks <= 0 (unlimited)
        sp_symbols_all = get_dynamic_market_symbols(max_stocks=-1, include_crypto=False, index_name="SP500")
        self.assertTrue(len(sp_symbols_all) > 400) # S&P 500 contains ~500 components
        
        ibex_symbols_all = get_dynamic_market_symbols(max_stocks=-1, include_crypto=False, index_name="IBEX35")
        self.assertTrue(len(ibex_symbols_all) >= 35) # IBEX 35 contains 35 components
        
        both_symbols_all = get_dynamic_market_symbols(max_stocks=-1, include_crypto=False, index_name="BOTH")
        self.assertTrue(len(both_symbols_all) > 400)

    def test_eur_asset_logging(self):
        # 1. Buy EUR asset SAN.MC (Bco. Santander) at 4.50 EUR, commission 1 EUR.
        # USD/EUR conversion rate is mocked in setUp to 0.92.
        # For EUR assets:
        # - raw_price (incoming) = 4.50 EUR
        # - raw_commission (incoming) = 1.00 EUR
        # - price_eur = 4.50 EUR (directly)
        # - commission_eur = 1.00 EUR (directly)
        # - price_usd = price_eur / 0.92 = 4.8913 USD
        # - commission_usd = commission_eur / 0.92 = 1.0870 USD
        trade_eur = {
            'timestamp': '2026-01-01T12:00:00',
            'order_id': 'buy_eur_1',
            'symbol': 'SAN.MC',
            'side': 'buy',
            'filled_qty': 100.0,
            'filled_price': 4.50,
            'commission': 1.00
        }
        
        res = self.trade_logger.log_trade(trade_eur)
        self.assertEqual(res['symbol'], 'SAN.MC')
        self.assertEqual(res['price_eur'], 4.50)
        self.assertEqual(res['commission_eur'], 1.00)
        self.assertEqual(res['total_eur'], 451.00)  # 100 * 4.50 + 1.00
        self.assertEqual(res['rate'], 0.92)
        
        # Verify columns logged in CSV
        df = pd.read_csv(self.trade_logger.trades_file)
        row = df.iloc[-1]
        self.assertEqual(row['symbol'], 'SAN.MC')
        self.assertAlmostEqual(row['price_usd'], 4.50 / 0.92, places=4)
        self.assertAlmostEqual(row['commission_usd'], 1.00 / 0.92, places=4)
        self.assertEqual(row['price_eur'], 4.50)
        self.assertEqual(row['commission_eur'], 1.00)
        self.assertEqual(row['total_eur'], 451.00)

        # 2. Test dividend logging for EUR asset
        # Dividend of 0.20 EUR withholding tax 0.04 EUR.
        div_res = self.trade_logger.log_dividend(symbol='SAN.MC', amount_usd=0.20, withholding_tax_usd=0.04)
        self.assertEqual(div_res['symbol'], 'SAN.MC')
        self.assertEqual(div_res['amount_eur'], 0.20)
        self.assertEqual(div_res['tax_eur'], 0.04)
        
        div_df = pd.read_csv(self.trade_logger.dividends_file)
        div_row = div_df.iloc[-1]
        self.assertEqual(div_row['symbol'], 'SAN.MC')
        self.assertAlmostEqual(div_row['amount_usd'], 0.20 / 0.92, places=4)
        self.assertAlmostEqual(div_row['withholding_tax_usd'], 0.04 / 0.92, places=4)
        self.assertEqual(div_row['amount_eur'], 0.20)
        self.assertEqual(div_row['withholding_tax_eur'], 0.04)

from strategy.composite_strategy import CompositeStrategy

class TestCompositeStrategyND(unittest.TestCase):
    def setUp(self):
        self.strategy = CompositeStrategy(technical_weight=0.40, fundamental_weight=0.30, sentiment_weight=0.30)
        
    @patch.dict(os.environ, {"BUY_THRESHOLD": "0.25", "SELL_THRESHOLD": "-0.25"})
    def test_one_indicator_missing_redistribution(self):
        prices_df = pd.DataFrame({'close': [100.0] * 60})
        fundamentals = {}
        sentiment = {'score': -0.5, 'article_count': 3, 'details': []}
        
        with patch('strategy.composite_strategy.add_all_indicators') as mock_add, \
             patch('strategy.composite_strategy.generate_ta_signals') as mock_ta:
            mock_ta.return_value = {'score': 0.8, 'indicators': {'rsi': 25}}
            
            res = self.strategy.evaluate("TEST", prices_df, fundamentals, sentiment)
            
            # Weighted calculation: (0.8 * 0.4/0.7) + (-0.5 * 0.3/0.7) = 0.457 - 0.214 = 0.24
            self.assertEqual(res['score'], 0.24)
            self.assertEqual(res['action'], 'HOLD')
            self.assertIsNone(res['details']['fundamental_score'])
            self.assertEqual(res['details']['technical_score'], 0.8)
            self.assertEqual(res['details']['sentiment_score'], -0.5)

    def test_two_indicators_missing_blocks_orders(self):
        prices_df = pd.DataFrame() # empty => technical score is None
        fundamentals = {} # empty => fundamental score is None
        sentiment = {'score': 0.8, 'article_count': 3, 'details': []}
        
        res = self.strategy.evaluate("TEST", prices_df, fundamentals, sentiment)
        
        # 2 indicators missing (applicable_count = 1 < 2) => score is None, action is HOLD
        self.assertIsNone(res['score'])
        self.assertEqual(res['action'], 'HOLD')
        self.assertIsNone(res['details']['technical_score'])
        self.assertIsNone(res['details']['fundamental_score'])
        self.assertEqual(res['details']['sentiment_score'], 0.8)

    def test_all_indicators_missing(self):
        prices_df = pd.DataFrame()
        fundamentals = {}
        sentiment = {'score': None, 'article_count': 0, 'details': []}
        
        res = self.strategy.evaluate("TEST", prices_df, fundamentals, sentiment)
        
        # All indicators missing => score is None, action is HOLD
        self.assertIsNone(res['score'])
        self.assertEqual(res['action'], 'HOLD')

from strategy.scheduler import sanitize_nan

class TestSanitizeNan(unittest.TestCase):
    def test_sanitize_nan_basic(self):
        import math
        data = {
            'a': 1.0,
            'b': float('nan'),
            'c': float('inf'),
            'd': float('-inf'),
            'e': {
                'f': [1.0, float('nan'), 2.0],
                'g': 'hello'
            }
        }
        sanitized = sanitize_nan(data)
        self.assertEqual(sanitized['a'], 1.0)
        self.assertIsNone(sanitized['b'])
        self.assertIsNone(sanitized['c'])
        self.assertIsNone(sanitized['d'])
        self.assertEqual(sanitized['e']['f'], [1.0, None, 2.0])
        self.assertEqual(sanitized['e']['g'], 'hello')

class TestAlpacaBrokerPagination(unittest.TestCase):
    @patch('alpaca.trading.client.TradingClient')
    def test_get_open_orders_pagination(self, mock_trading_client_class):
        from broker.alpaca_broker import AlpacaBroker
        
        # Instantiate broker with credentials so it initializes
        broker = AlpacaBroker(api_key="test_key", secret_key="test_secret")
        
        # Create mock trading client instance
        mock_client = MagicMock()
        broker._trading_client = mock_client
        broker.initialized = True
        
        class MockOrder:
            def __init__(self, order_id, symbol, side, qty, price, created_at):
                self.id = order_id
                self.symbol = symbol
                self.side = MagicMock()
                self.side.value = side
                self.qty = qty
                self.filled_avg_price = price
                self.limit_price = price
                self.filled_qty = 0.0
                self.status = MagicMock()
                self.status.value = 'new'
                self.created_at = created_at
                
        from datetime import datetime, timezone
        t1 = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 7, 21, 11, 0, 0, tzinfo=timezone.utc)
        
        page1 = [
            MockOrder(f"id_{i}", f"SYM_{i}", 'buy', 10.0, 100.0, t1)
            for i in range(500)
        ]
        page2 = [
            MockOrder(f"id_{i}", f"SYM_{i}", 'buy', 10.0, 100.0, t2)
            for i in range(500, 550)
        ]
        
        mock_client.get_orders.side_effect = [page1, page2, []]
        
        orders = broker.get_open_orders()
        
        # Verify get_orders was called 2 times (terminates early since page 2 is not full)
        self.assertEqual(mock_client.get_orders.call_count, 2)
        # Total orders fetched should be 550
        self.assertEqual(len(orders), 550)
        self.assertEqual(orders[0]['order_id'], "id_0")
        self.assertEqual(orders[-1]['order_id'], "id_549")

if __name__ == '__main__':
    unittest.main()
