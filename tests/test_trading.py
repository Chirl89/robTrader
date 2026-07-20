import os
import shutil
import unittest
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

if __name__ == '__main__':
    unittest.main()
