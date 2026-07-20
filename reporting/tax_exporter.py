import os
import csv
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any

class TaxExporter:
    """
    Applies the FIFO (First-In, First-Out) method to calculate capital gains and losses 
    in EUR for Spanish tax compliance (IRPF).
    """

    def __init__(self, log_dir: str = "data_logs"):
        self.log_dir = log_dir
        
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
        self.report_file = os.path.join(self.log_dir, f"spanish_tax_report_{suffix}.csv")

    def generate_tax_report(self) -> Dict[str, Any]:
        """
        Reads the trades log, applies FIFO, and writes a detailed tax statement.
        """
        if not os.path.exists(self.trades_file):
            return {'status': 'error', 'message': 'No trades log file found.'}

        # Read trade history
        df = pd.read_csv(self.trades_file)
        if df.empty:
            return {'status': 'empty', 'message': 'Trades log is empty.'}

        # Sort trades by timestamp to ensure chronological order
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)

        # FIFO queues per symbol
        # Format: symbol -> list of dicts: {'timestamp', 'qty', 'price_eur', 'commission_eur', 'original_qty'}
        buy_queues: Dict[str, List[Dict[str, Any]]] = {}
        tax_events: List[Dict[str, Any]] = []
        
        total_gains = 0.0
        total_losses = 0.0

        for _, row in df.iterrows():
            symbol = row['symbol']
            side = row['side'].lower()
            qty = float(row['qty'])
            price_eur = float(row['price_eur'])
            commission_eur = float(row['commission_eur'])
            timestamp = row['timestamp']

            if side == 'buy':
                if symbol not in buy_queues:
                    buy_queues[symbol] = []
                buy_queues[symbol].append({
                    'timestamp': timestamp,
                    'qty': qty,
                    'original_qty': qty,
                    'price_eur': price_eur,
                    'commission_eur': commission_eur
                })
            elif side == 'sell':
                # Process sale FIFO matching
                sell_qty_remaining = qty
                sell_commission = commission_eur

                if symbol not in buy_queues or not buy_queues[symbol]:
                    # Short selling or data inconsistency
                    continue

                while sell_qty_remaining > 0 and buy_queues[symbol]:
                    earliest_buy = buy_queues[symbol][0]
                    buy_qty_available = earliest_buy['qty']

                    # Determine how many shares we match from this lot
                    matched_qty = min(sell_qty_remaining, buy_qty_available)

                    # Proportional buy commission for this matched qty
                    prop_buy_comm = (matched_qty / earliest_buy['original_qty']) * earliest_buy['commission_eur']
                    # Proportional sell commission for this matched qty
                    prop_sell_comm = (matched_qty / qty) * sell_commission

                    # Cost base (Acquisition Value in EUR) = matched_qty * purchase_price + proportional_buy_fee
                    acquisition_value = (matched_qty * earliest_buy['price_eur']) + prop_buy_comm
                    
                    # Sale value (Sale Proceeds in EUR) = matched_qty * sale_price - proportional_sell_fee
                    sale_value = (matched_qty * price_eur) - prop_sell_comm
                    
                    gain_loss = sale_value - acquisition_value
                    
                    if gain_loss >= 0:
                        total_gains += gain_loss
                    else:
                        total_losses += gain_loss

                    tax_events.append({
                        'symbol': symbol,
                        'purchase_date': earliest_buy['timestamp'].strftime('%Y-%m-%d'),
                        'sale_date': timestamp.strftime('%Y-%m-%d'),
                        'qty': matched_qty,
                        'purchase_price_eur': earliest_buy['price_eur'],
                        'sale_price_eur': price_eur,
                        'acquisition_value_eur': round(acquisition_value, 2),
                        'sale_value_eur': round(sale_value, 2),
                        'gain_loss_eur': round(gain_loss, 2)
                    })

                    # Deduct from the buy lot
                    earliest_buy['qty'] -= matched_qty
                    sell_qty_remaining -= matched_qty

                    # If this buy lot is fully sold, remove it from queue
                    if earliest_buy['qty'] <= 0.0001:
                        buy_queues[symbol].pop(0)

        # Write tax report CSV
        with open(self.report_file, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Elemento (Symbol)", "Fecha Adquisicion", "Fecha Transmision", 
                "Cantidad", "Valor Adquisicion (EUR)", "Valor Transmision (EUR)", "Ganancia/Perdida (EUR)"
            ])
            for ev in tax_events:
                writer.writerow([
                    ev['symbol'], ev['purchase_date'], ev['sale_date'],
                    ev['qty'], ev['acquisition_value_eur'], ev['sale_value_eur'], ev['gain_loss_eur']
                ])

        # Read dividends for summary
        dividend_summary = []
        total_dividends_eur = 0.0
        total_withholding_tax_eur = 0.0
        
        if os.path.exists(self.dividends_file):
            div_df = pd.read_csv(self.dividends_file)
            if not div_df.empty:
                total_dividends_eur = float(div_df['amount_eur'].sum())
                total_withholding_tax_eur = float(div_df['withholding_tax_eur'].sum())
                for _, row in div_df.iterrows():
                    dividend_summary.append({
                        'symbol': row['symbol'],
                        'date': row['date'],
                        'amount_eur': row['amount_eur'],
                        'tax_eur': row['withholding_tax_eur']
                    })

        return {
            'status': 'success',
            'report_path': self.report_file,
            'summary': {
                'total_capital_gains_eur': round(total_gains, 2),
                'total_capital_losses_eur': round(total_losses, 2),
                'net_capital_gain_loss_eur': round(total_gains + total_losses, 2),
                'total_dividends_received_eur': round(total_dividends_eur, 2),
                'total_withholding_tax_paid_eur': round(total_withholding_tax_eur, 2)
            },
            'taxable_trades_count': len(tax_events),
            'dividend_records_count': len(dividend_summary)
        }
