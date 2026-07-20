import os
import csv
from datetime import datetime
import yfinance as yf
from typing import Dict, Any

class TradeLogger:
    """
    Logs all execution trades and dividend distributions to CSV files.
    Calculates USD to EUR conversion rates using yfinance for Spanish tax tracking.
    """

    def __init__(self, log_dir: str = "data_logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Calculate dynamic suffix based on active API key
        import hashlib
        import dotenv
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        
        self.trades_file = os.path.join(self.log_dir, f"trades_log_{suffix}.csv")
        self.dividends_file = os.path.join(self.log_dir, f"dividends_log_{suffix}.csv")
        
        self._init_files()

    def _init_files(self):
        # Initialize Trades CSV
        if not os.path.exists(self.trades_file):
            with open(self.trades_file, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "order_id", "symbol", "side", "qty", 
                    "price_usd", "commission_usd", "exchange_rate_eur_usd", 
                    "price_eur", "commission_eur", "total_eur"
                ])
                
        # Initialize Dividends CSV
        if not os.path.exists(self.dividends_file):
            with open(self.dividends_file, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "date", "symbol", "amount_usd", "withholding_tax_usd", 
                    "exchange_rate_eur_usd", "amount_eur", "withholding_tax_eur"
                ])

    def get_usd_eur_rate(self, date_str: str) -> float:
        """
        Fetches the USD/EUR exchange rate for a given date from yfinance.
        If fetching fails, defaults to a stable standard estimate (0.92 EUR per USD).
        """
        try:
            # Parse the date to get yyyy-mm-dd
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_formatted = dt.strftime("%Y-%m-%d")
            
            # yfinance ticker for USD/EUR exchange rate
            ticker = yf.Ticker("USDEUR=X")
            # Fetch historical data for that day
            history = ticker.history(start=date_formatted, end=date_formatted)
            
            if not history.empty:
                rate = float(history['Close'].iloc[0])
                return round(rate, 4)
                
            # If historical exact day is empty (e.g. weekend), fetch last 5 days and take latest
            history_recent = ticker.history(period="5d")
            if not history_recent.empty:
                return round(float(history_recent['Close'].iloc[-1]), 4)
                
        except Exception:
            pass
            
        return 0.9200  # Default standard exchange rate fallback

    def log_trade(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Logs a completed trade, translating values into EUR.
        Expected keys in trade_data:
        - 'timestamp': str (ISO format)
        - 'order_id': str
        - 'symbol': str
        - 'side': str ('buy' or 'sell')
        - 'filled_qty': float
        - 'filled_price': float
        - 'commission': float
        """
        timestamp = trade_data.get('timestamp') or datetime.now().isoformat()
        order_id = trade_data.get('order_id', 'unknown')
        symbol = trade_data.get('symbol')
        side = trade_data.get('side', '').lower()
        qty = float(trade_data.get('filled_qty', 0.0))
        if qty <= 0.0:
            return {}
            
        raw_price = float(trade_data.get('filled_price', 0.0))
        raw_commission = float(trade_data.get('commission', 0.0))
        
        # Get Exchange Rate (USD to EUR rate, e.g. 0.92 means 1 USD = 0.92 EUR)
        rate = self.get_usd_eur_rate(timestamp)
        
        # Determine if asset is denominated in EUR (e.g. Spanish market .MC suffix)
        is_eur_asset = symbol.upper().endswith('.MC') if symbol else False
        
        if is_eur_asset:
            # Price and commission from the broker/simulator are already in EUR
            price_eur = raw_price
            commission_eur = raw_commission
            # Back-calculate USD values for the CSV log structure
            price_usd = round(price_eur / rate, 4) if rate > 0 else price_eur
            commission_usd = round(commission_eur / rate, 4) if rate > 0 else commission_eur
        else:
            # Asset is in USD: convert to EUR
            price_usd = raw_price
            commission_usd = raw_commission
            price_eur = round(price_usd * rate, 4)
            commission_eur = round(commission_usd * rate, 4)
        
        trade_value_eur = qty * price_eur
        if side == 'buy':
            total_eur = round(trade_value_eur + commission_eur, 4)
        else: # sell
            total_eur = round(trade_value_eur - commission_eur, 4)
            
        # Log to file
        with open(self.trades_file, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp, order_id, symbol, side, qty, 
                price_usd, commission_usd, rate, 
                price_eur, commission_eur, total_eur
            ])
            
        return {
            'timestamp': timestamp,
            'symbol': symbol,
            'side': side,
            'qty': qty,
            'price_eur': price_eur,
            'commission_eur': commission_eur,
            'total_eur': total_eur,
            'rate': rate
        }

    def log_dividend(self, symbol: str, amount_usd: float, withholding_tax_usd: float = 0.0, date_str: str = None) -> Dict[str, Any]:
        """
        Logs a dividend payment received.
        """
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        rate = self.get_usd_eur_rate(date_str)
        
        # Determine if asset is denominated in EUR
        is_eur_asset = symbol.upper().endswith('.MC') if symbol else False
        
        if is_eur_asset:
            # Amounts received are already in EUR
            amount_eur = amount_usd
            tax_eur = withholding_tax_usd
            # Back-calculate USD equivalent
            amount_usd = round(amount_eur / rate, 4) if rate > 0 else amount_eur
            withholding_tax_usd = round(tax_eur / rate, 4) if rate > 0 else tax_eur
        else:
            amount_eur = round(amount_usd * rate, 4)
            tax_eur = round(withholding_tax_usd * rate, 4)
        
        with open(self.dividends_file, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                date_str, symbol, amount_usd, withholding_tax_usd,
                rate, amount_eur, tax_eur
            ])
            
        return {
            'date': date_str,
            'symbol': symbol,
            'amount_eur': amount_eur,
            'tax_eur': tax_eur,
            'rate': rate
        }
