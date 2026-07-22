import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add project root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from data.yahoo_provider import YahooProvider
from data.alpaca_provider import AlpacaProvider
from strategy.composite_strategy import CompositeStrategy
from broker.simulator_broker import SimulatorBroker
from broker.alpaca_broker import AlpacaBroker
from reporting.trade_logger import TradeLogger
from reporting.tax_exporter import TaxExporter

# Set up logging format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("robTrader.Scheduler")

def sanitize_nan(val):
    import math
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
    elif isinstance(val, dict):
        return {k: sanitize_nan(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [sanitize_nan(x) for x in val]
    return val

class TradingScheduler:
    """
    Main orchestrator that schedules and runs the trading cycle.
    """

    def __init__(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(root_dir, '.env'))
        
        # 1. Config parameters
        self.dynamic_scan = os.getenv("DYNAMIC_SCAN", "False").lower() == "true"
        self.dynamic_scan_index = os.getenv("DYNAMIC_SCAN_INDEX", "SP500").upper()
        self.dynamic_stock_limit = int(os.getenv("DYNAMIC_STOCK_LIMIT", "15"))
        self.portfolio_refresh_secs = int(os.getenv("PORTFOLIO_REFRESH_SECS", "15"))
        self.reanalyze_interval_mins = int(os.getenv("REANALYZE_INTERVAL_MINS", "60"))
        self.order_type = os.getenv("ORDER_TYPE", "market").lower()
        
        # Calculate dynamic suffix based on active API key
        import hashlib
        import dotenv
        env_path = os.path.join(root_dir, ".env")
        key = "default"
        if os.path.exists(env_path):
            config = dotenv.dotenv_values(env_path)
            key = config.get("ALPACA_API_KEY_ID", "default") or "default"
        is_sim = (key == "default" or not key.strip())
        prefix = "sim" if is_sim else "alpaca"
        key_clean = "simulator" if is_sim else key.strip()
        h = hashlib.md5(key_clean.encode()).hexdigest()[:8]
        suffix = f"{prefix}_{h}"
        
        self.portfolio_state_file = os.path.join(root_dir, "data_logs", f"portfolio_state_{suffix}.json")
        self.analysis_state_file = os.path.join(root_dir, "data_logs", f"analysis_state_{suffix}.json")
        self.portfolio_history_file = os.path.join(root_dir, "data_logs", f"portfolio_history_{suffix}.csv")
        
        if self.dynamic_scan:
            logger.info(f"Dynamic scan enabled. Initializing empty symbols list; symbols will be scraped dynamically during run_cycle().")
            self.symbols = []
        else:
            self.symbols = [s.strip() for s in os.getenv("DEFAULT_TRADING_SYMBOLS", "AAPL,MSFT,GOOGL,AMZN,TSLA").split(",")]
            
        self.max_pos_pct = float(os.getenv("MAX_POSITION_SIZE_PCT", "0.10"))
        self.daily_loss_limit = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.02"))
        self.historical_days = int(os.getenv("HISTORICAL_DAYS", "120"))
        
        # 2. Select and initialize components
        self.use_alpaca = bool(os.getenv("ALPACA_API_KEY_ID") and os.getenv("ALPACA_SECRET_KEY"))
        
        if self.use_alpaca:
            logger.info("Alpaca credentials found. Initializing Alpaca data provider and broker.")
            self.data_provider = AlpacaProvider()
            self.broker = AlpacaBroker()
        else:
            logger.warning("No Alpaca credentials found in .env. Falling back to Yahoo Finance data and Simulator Broker.")
            self.data_provider = YahooProvider()
            self.broker = SimulatorBroker(initial_cash=10000.0) # start simulator with 10k EUR/USD
            
        self.strategy = CompositeStrategy()
        self.trade_logger = TradeLogger()
        self.tax_exporter = TaxExporter()
        
        # Store portfolio starting value for daily loss check (recover from history if exists to survive restarts)
        self.last_check_date = datetime.now().date()
        self.start_day_portfolio_value = self.get_start_day_portfolio_value()

    def get_start_day_portfolio_value(self) -> float:
        """
        Reads portfolio_history.csv to retrieve the first recorded portfolio value 
        for the current calendar day. Falls back to current broker value if none found.
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        if os.path.exists(self.portfolio_history_file):
            try:
                import csv
                with open(self.portfolio_history_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader, None)  # skip header
                    for row in reader:
                        if row and len(row) >= 2:
                            # Timestamp matches current date? (e.g. "2026-07-20T12:00:00")
                            log_date = row[0].split('T')[0]
                            if log_date == today_str:
                                val = float(row[1])
                                logger.info(f"Recovered daily start portfolio value from history: {val:.2f} (Date: {log_date})")
                                return val
            except Exception as e:
                logger.error(f"Error reading portfolio history for daily start value: {e}")
        
        # Fallback
        try:
            val = self.broker.get_portfolio_value()
            logger.info(f"No history found for today. Set daily start portfolio value to current broker value: {val:.2f}")
            return val
        except Exception:
            return 100000.0

    def calculate_available_cash(self, open_orders: list = None) -> float:
        """
        Calculates available cash by subtracting the value of all pending/active buy orders
        from the raw broker cash. Reuses pre-fetched open orders if provided.
        """
        try:
            broker_cash = self.broker.get_cash()
            if open_orders is None:
                open_orders = self.broker.get_open_orders()
            pending_buys = [
                o for o in open_orders 
                if o['side'].lower() == 'buy'
            ]
            reserved_cash = sum(
                (float(o['qty']) - float(o.get('filled_qty', 0.0))) * float(o['price']) 
                for o in pending_buys
            )
            available_cash = max(0.0, broker_cash - reserved_cash)
            return round(available_cash, 2)
        except Exception as e:
            logger.error(f"Failed to calculate available cash: {e}")
            try:
                return self.broker.get_cash()
            except Exception:
                return 0.0

    def refresh_portfolio(self, override_cash: float = None):
        """
        Queries current portfolio stats (cash, value, positions) and exports them 
        to data_logs/portfolio_state.json for the web dashboard.
        """
        try:
            if override_cash is not None:
                cash = override_cash
            else:
                cash = self.calculate_available_cash()
            value = self.broker.get_portfolio_value()
            positions = self.broker.get_positions()
            
            now = datetime.now()
            # If calendar day changed during runtime, reset the daily start portfolio value
            if now.date() != self.last_check_date:
                self.start_day_portfolio_value = value
                self.last_check_date = now.date()
                logger.info(f"New calendar day detected during runtime. Resetting daily start portfolio value to {value:.2f}")

            # Enrich positions with names
            name_cache = {}
            for sym, pos_data in positions.items():
                if sym not in name_cache:
                    try:
                        fundamentals = self.data_provider.get_fundamentals(sym)
                        name_cache[sym] = fundamentals.get('name') or sym
                    except Exception:
                        name_cache[sym] = sym
                pos_data['name'] = name_cache[sym]

            state = sanitize_nan({
                'timestamp': now.isoformat(),
                'status': 'active',
                'cash': cash,
                'portfolio_value': value,
                'start_day_portfolio_value': self.start_day_portfolio_value,
                'positions': positions
            })
            
            # Ensure log directory exists
            os.makedirs(os.path.dirname(self.portfolio_state_file), exist_ok=True)
            
            with open(self.portfolio_state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=4)
                
            # Log to portfolio_history.csv for history tracking
            import csv
            file_exists = os.path.exists(self.portfolio_history_file)
            with open(self.portfolio_history_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['timestamp', 'portfolio_value', 'cash'])
                writer.writerow([now.isoformat(), value, cash])
                
            logger.info(f"Refreshed portfolio: Cash = {cash:.2f} | Total Value = {value:.2f}")
            
            # Reconcile filled orders from broker to the local trades CSV log
            self.reconcile_filled_orders()
        except Exception as e:
            logger.error(f"Failed to refresh and export portfolio state: {e}")

    def reconcile_filled_orders(self):
        """
        Polls completed/filled orders from the broker and ensures they are recorded 
        in the local trades log. Prevent duplicates using unique order IDs.
        """
        try:
            filled_orders = self.broker.get_filled_orders()
            if not filled_orders:
                return
                
            # Load existing logged order IDs to prevent double logging
            existing_ids = set()
            if os.path.exists(self.trade_logger.trades_file):
                with open(self.trade_logger.trades_file, 'r', encoding='utf-8') as f:
                    import csv
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('order_id'):
                            existing_ids.add(row['order_id'])
                            
            for o in filled_orders:
                if o['order_id'] not in existing_ids:
                    logger.info(f"Reconciling filled order {o['order_id']} for {o['symbol']} ({o['qty']} shares @ {o['price']}) to local trades log...")
                    trade_data = {
                        'timestamp': o['timestamp'],
                        'order_id': o['order_id'],
                        'symbol': o['symbol'],
                        'side': o['side'],
                        'filled_qty': o['qty'],
                        'filled_price': o['price'],
                        'commission': o.get('commission', 0.0)
                    }
                    self.trade_logger.log_trade(trade_data)
        except Exception as e:
            logger.error(f"Failed to reconcile filled orders: {e}", exc_info=True)

    def run_cycle(self):
        """
        Executes a single cycle of: Data fetch -> Analysis -> Strategy -> Broker Execution -> Tax reporting.
        """
        logger.info("------ Starting Trading Cycle ------")
        buy_threshold = float(os.getenv("BUY_THRESHOLD", "0.25"))
        sell_threshold = float(os.getenv("SELL_THRESHOLD", "-0.25"))
        logger.info(f"Signal Thresholds: BUY >= {buy_threshold} | SELL <= {sell_threshold}")
        
        if self.dynamic_scan:
            try:
                from analysis.market_scanner import get_dynamic_market_symbols
                self.symbols = get_dynamic_market_symbols(
                    max_stocks=self.dynamic_stock_limit, 
                    include_crypto=True, 
                    index_name=self.dynamic_scan_index
                )
                logger.info(f"Dynamically scanned market. Raw target symbols: {self.symbols}")
            except Exception as e:
                logger.error(f"Failed to scan market dynamically: {e}")
                
        # Validate/Map symbols dynamically against broker active assets to resolve special characters
        try:
            tradable_symbols = self.broker.get_tradable_assets()
            if tradable_symbols and tradable_symbols != ['*']:
                logger.info("Normalizing and validating target symbols against broker's active assets...")
                alpaca_lookup = {}
                for ts in tradable_symbols:
                    norm = ts.replace('.', '').replace('-', '').replace('/', '').upper()
                    alpaca_lookup[norm] = ts
                
                validated_symbols = []
                for sym in self.symbols:
                    norm_sym = sym.replace('.', '').replace('-', '').replace('/', '').upper()
                    if norm_sym in alpaca_lookup:
                        # Map to broker's official symbol representation (e.g. BRK.B)
                        validated_symbols.append(alpaca_lookup[norm_sym])
                    else:
                        logger.warning(f"Symbol {sym} is not supported or active on the broker. Skipping.")
                self.symbols = validated_symbols
                logger.info(f"Validated target symbols for this cycle: {self.symbols}")
        except Exception as e:
            logger.error(f"Failed to validate symbols against broker: {e}")
                
        now = datetime.now()
        
        # 1. Safety Checks (Daily Loss Limit)
        try:
            current_portfolio_value = self.broker.get_portfolio_value()
            broker_cash = self.broker.get_cash()
            active_positions = self.broker.get_positions()
            
            # Fetch open orders once at start of cycle to prevent rate-limiting (HTTP 429)
            all_open_orders = self.broker.get_open_orders()
            
            # Automatically append open positions to target symbols for monitoring
            for pos_symbol in active_positions.keys():
                if pos_symbol not in self.symbols:
                    self.symbols.append(pos_symbol)
                    logger.info(f"Added open position symbol {pos_symbol} to target symbols for monitoring/evaluation.")
            
            # Calculate available cash at the beginning of the cycle reusing open orders
            cash = self.calculate_available_cash(open_orders=all_open_orders)
            logger.info(f"Broker Cash: {broker_cash:.2f} | Estimated Available Cash: {cash:.2f}")
        except Exception as e:
            logger.error(f"Failed to fetch account info from broker: {e}")
            return

        loss = self.start_day_portfolio_value - current_portfolio_value
        max_allowed_loss = self.start_day_portfolio_value * self.daily_loss_limit
        if loss > max_allowed_loss:
            logger.critical(f"Daily loss limit reached! Current Portfolio Value: {current_portfolio_value:.2f}, Daily Loss: {loss:.2f}. Suspending executions for safety.")
            return

        logger.info(f"Portfolio Value: {current_portfolio_value:.2f} | Cash: {cash:.2f} | Open Positions: {list(active_positions.keys())}")

        # Fetch latest prices to update simulator if applicable
        current_prices = {}
        evaluations = {}
        
        # 2. Evaluate each symbol
        for symbol in self.symbols:
            logger.info(f"Analyzing {symbol}...")
            try:
                # Get historical prices (last X days to calculate technical indicators)
                end_date = now.strftime("%Y-%m-%d")
                start_date = (now - timedelta(days=self.historical_days)).strftime("%Y-%m-%d")
                
                prices_df = self.data_provider.get_historical_data(symbol, start_date, end_date, timeframe="1Day")
                if prices_df.empty:
                    logger.warning(f"No price data retrieved for {symbol}. Skipping.")
                    continue
                
                # Retrieve news articles and run sentiment evaluation
                news = self.data_provider.get_news(symbol, limit=8)
                from analysis.sentiment_analysis import get_news_sentiment
                sentiment = get_news_sentiment(news)
                
                # Fetch company fundamentals
                fundamentals = self.data_provider.get_fundamentals(symbol)
                
                # Evaluate strategy
                evaluation = self.strategy.evaluate(symbol, prices_df, fundamentals, sentiment)
                action = evaluation['action']
                score = evaluation['score']
                
                latest_price = float(prices_df.iloc[-1]['close'])
                current_prices[symbol] = latest_price
                
                logger.info(f"Strategy recommendation for {symbol}: {action} (Score: {score}) | Price: {latest_price:.2f}")
                
                # Save evaluation for metrics report
                evaluations[symbol] = {
                    'name': fundamentals.get('name') or symbol,
                    'score': score,
                    'action': action,
                    'latest_price': latest_price,
                    'details': evaluation.get('details', {})
                }
                
                # Update simulator broker price
                if isinstance(self.broker, SimulatorBroker):
                    self.broker.update_prices({symbol: latest_price})

                # 3. Decision Logic & Execution
                pos_qty = active_positions.get(symbol, {}).get('qty', 0.0)
                pos_value = pos_qty * latest_price
                
                # Check for active pending orders to prevent duplicate execution
                pending_orders = []
                try:
                    norm_sym = symbol.replace('/', '').replace('-', '').upper()
                    pending_orders = [
                        o for o in all_open_orders 
                        if o['symbol'].replace('/', '').replace('-', '').upper() == norm_sym
                    ]
                    
                    # If we have pending orders, check if they are stale and should be canceled
                    if len(pending_orders) > 0:
                        for pending_order in list(pending_orders):
                            pending_side = pending_order['side'].upper()
                            if pending_side == 'BUY' and action != 'BUY':
                                logger.info(f"New strategy evaluation for {symbol} is {action} (Score: {score}), but found active pending BUY order. Canceling stale order {pending_order['order_id']}...")
                                self.broker.cancel_order(pending_order['order_id'])
                                pending_orders = [po for po in pending_orders if po['order_id'] != pending_order['order_id']]
                                all_open_orders = [po for po in all_open_orders if po['order_id'] != pending_order['order_id']]
                            elif pending_side == 'SELL' and action != 'SELL':
                                logger.info(f"New strategy evaluation for {symbol} is {action} (Score: {score}), but found active pending SELL order. Canceling stale order {pending_order['order_id']}...")
                                self.broker.cancel_order(pending_order['order_id'])
                                pending_orders = [po for po in pending_orders if po['order_id'] != pending_order['order_id']]
                                all_open_orders = [po for po in all_open_orders if po['order_id'] != pending_order['order_id']]
                            elif pending_side == action:
                                # Check if price drifted
                                pending_price = pending_order.get('limit_price') or pending_order.get('price')
                                if pending_price is not None:
                                    price_diff_pct = abs(latest_price - pending_price) / pending_price
                                    if price_diff_pct > 0.0005:  # 0.05% threshold
                                        logger.info(f"Price drifted for {symbol} ({pending_price:.2f} -> {latest_price:.2f}) while action is still {action}. Canceling stale order {pending_order['order_id']} to replace it.")
                                        self.broker.cancel_order(pending_order['order_id'])
                                        pending_orders = [po for po in pending_orders if po['order_id'] != pending_order['order_id']]
                                        all_open_orders = [po for po in all_open_orders if po['order_id'] != pending_order['order_id']]
                except Exception as e:
                    logger.error(f"Failed to process pending orders for {symbol}: {e}")
                
                if action == "BUY":
                    if len(pending_orders) > 0:
                        logger.info(f"Skipping BUY order for {symbol}: Already has {len(pending_orders)} pending order(s) active in broker.")
                    else:
                        # Target value = MAX_POSITION_SIZE_PCT * total_portfolio
                        target_pos_val = current_portfolio_value * self.max_pos_pct
                        if pos_value < target_pos_val:
                            cash_to_spend = target_pos_val - pos_value
                            # Leave safety margin for cash (minimum $100 cash remaining)
                            cash_available = max(0.0, cash - 100.0)
                            cash_to_spend = min(cash_to_spend, cash_available)
                            
                            qty_to_buy = cash_to_spend / latest_price
                            
                            # Round down to integer for stocks (non-crypto assets)
                            is_crypto = any(c in symbol.upper() for c in ['USD', '/'])
                            if not is_crypto:
                                qty_to_buy = int(qty_to_buy)
                            
                            if qty_to_buy > 0.001:  # Buy minimum fraction
                                log_qty = f"{qty_to_buy:.4f}" if is_crypto else str(qty_to_buy)
                                logger.info(f"Submitting {self.order_type.upper()} BUY order for {symbol}: {log_qty} shares at {latest_price:.2f}")
                                order_res = self.broker.submit_order(symbol, qty_to_buy, 'buy', latest_price, order_type=self.order_type)
                                
                                if order_res.get('status') != 'rejected':
                                    logger.info(f"BUY Order Placed! Order ID: {order_res.get('order_id')} | Status: {order_res.get('status')}")
                                    # Add timestamp for trade logs
                                    order_res['timestamp'] = now.isoformat()
                                    self.trade_logger.log_trade(order_res)
                                    
                                    # Deduct estimated cost from local cash immediately to prevent double spending in the same cycle
                                    cost = qty_to_buy * latest_price
                                    commission_estimate = max(1.0, cost * 0.001)  # standard estimate
                                    cash = max(0.0, cash - (cost + commission_estimate))
                                    logger.info(f"Updated local available cash after BUY order: {cash:.2f}")
                                    self.refresh_portfolio(override_cash=cash)
                                else:
                                    logger.warning(f"BUY Order Rejected: {order_res.get('reason')}")
                        else:
                            logger.info(f"Position size for {symbol} already at or above maximum target size.")
                            
                elif action == "SELL":
                    if len(pending_orders) > 0:
                        logger.info(f"Skipping SELL order for {symbol}: Already has {len(pending_orders)} pending order(s) active in broker.")
                    else:
                        if pos_qty > 0:
                            logger.info(f"Submitting {self.order_type.upper()} SELL order to CLOSE position in {symbol}: {pos_qty:.4f} shares at {latest_price:.2f}")
                            order_res = self.broker.submit_order(symbol, pos_qty, 'sell', latest_price, order_type=self.order_type)
                            
                            if order_res.get('status') != 'rejected':
                                logger.info(f"SELL Order Placed! Order ID: {order_res.get('order_id')} | Status: {order_res.get('status')}")
                                order_res['timestamp'] = now.isoformat()
                                self.trade_logger.log_trade(order_res)
                                
                                # For sell orders, check if they are executed/filled immediately
                                if order_res.get('status').lower() == 'filled':
                                    proceeds = pos_qty * latest_price - order_res.get('commission', 0.0)
                                    cash = cash + proceeds
                                    logger.info(f"Updated local available cash after filled SELL order: {cash:.2f}")
                                    self.refresh_portfolio(override_cash=cash)
                            else:
                                logger.warning(f"SELL Order Rejected: {order_res.get('reason')}")
                        else:
                            logger.info(f"No active position to sell in {symbol}.")
                
                else: # HOLD
                    logger.info(f"Holding current position for {symbol}.")
                    
            except Exception as e:
                logger.error(f"Error executing cycle for {symbol}: {e}", exc_info=True)
            
            # Throttle delay to prevent resource spike and rate limiting
            throttle_delay = float(os.getenv("ANALYSIS_THROTTLE_DELAY_SECS", "1.5"))
            if throttle_delay > 0:
                time.sleep(throttle_delay)

        # 4. Save dynamic analysis state
        try:
            analysis_state = sanitize_nan({
                'timestamp': datetime.now().isoformat(),
                'buy_threshold': float(os.getenv("BUY_THRESHOLD", "0.25")),
                'sell_threshold': float(os.getenv("SELL_THRESHOLD", "-0.25")),
                'evaluations': evaluations
            })
            with open(self.analysis_state_file, 'w', encoding='utf-8') as f:
                json.dump(analysis_state, f, indent=4)
            logger.info(f"Saved analysis metrics for {len(evaluations)} symbols to {self.analysis_state_file}")
        except Exception as e:
            logger.error(f"Failed to save analysis state: {e}")

        # 5. Generate Spanish tax logs
        try:
            tax_res = self.tax_exporter.generate_tax_report()
            if tax_res.get('status') == 'success':
                logger.info(f"Spanish Tax Report generated successfully at: {tax_res.get('report_path')}")
                logger.info(f"Net gains/losses: {tax_res['summary']['net_capital_gain_loss_eur']} EUR")
        except Exception as e:
            logger.error(f"Error compiling tax report: {e}")

        logger.info("------ Trading Cycle Finished ------")

    def start_loop(self):
        """
        Runs the scheduler loop using separate timers for portfolio updates 
        and market re-analysis cycles.
        """
        logger.info("Starting execution loop.")
        logger.info(f"- Portfolio Refresh Interval: {self.portfolio_refresh_secs} seconds")
        logger.info(f"- Market Re-Analysis Interval: {self.reanalyze_interval_mins} minutes")
        
        last_refresh = 0.0
        last_analysis = 0.0
        
        while True:
            try:
                now = time.time()
                
                # 1. Trigger portfolio refresh
                if now - last_refresh >= self.portfolio_refresh_secs:
                    self.refresh_portfolio()
                    last_refresh = now
                    
                # 2. Trigger strategy re-analysis
                if now - last_analysis >= self.reanalyze_interval_mins * 60:
                    self.run_cycle()
                    last_analysis = now
                    
            except Exception as e:
                logger.error(f"Exception in scheduler loop: {e}")
                
            time.sleep(1)

if __name__ == "__main__":
    scheduler = TradingScheduler()
    # If run directly as a script, execute a single cycle for verification
    scheduler.run_cycle()
