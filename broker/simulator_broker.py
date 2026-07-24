import uuid
from datetime import datetime
from typing import Dict, Any, List
from broker.base_broker import BaseBroker

class SimulatorBroker(BaseBroker):
    """
    A simulated, in-memory broker client for dry runs and testing.
    Tracks cash, positions, and logs all submitted orders.
    """

    def __init__(self, initial_cash: float = 100000.0, commission_pct: float = 0.001, min_commission: float = 1.00, state_file: str = None):
        self.state_file = state_file
        self.commission_pct = commission_pct
        self.min_commission = min_commission
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders: List[Dict[str, Any]] = []
        self.cash = initial_cash
        
        if self.state_file:
            self._load_state()
        
    def _load_state(self):
        import os
        import json
        if not self.state_file or not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                self.cash = state.get('cash', self.cash)
                self.positions = state.get('positions', {})
                self.orders = state.get('orders', [])
        except Exception as e:
            import logging
            logging.getLogger("robTrader.SimulatorBroker").error(f"Failed to load simulator state: {e}")

    def _save_state(self):
        if not self.state_file:
            return
        try:
            import os
            import json
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'cash': self.cash,
                    'positions': self.positions,
                    'orders': self.orders
                }, f, indent=4)
        except Exception as e:
            import logging
            logging.getLogger("robTrader.SimulatorBroker").error(f"Failed to save simulator state: {e}")

    def get_cash(self) -> float:
        return round(self.cash, 2)

    def update_prices(self, prices: Dict[str, float]):
        """
        Updates current prices of active positions to reflect portfolio value accurately.
        """
        changed = False
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol]['current_price'] = price
                changed = True
        if changed:
            self._save_state()

    def get_portfolio_value(self) -> float:
        positions_value = 0.0
        for symbol, pos in self.positions.items():
            positions_value += pos['qty'] * pos['current_price']
        return round(self.cash + positions_value, 2)

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        return self.positions.copy()

    def get_orders(self) -> List[Dict[str, Any]]:
        return self.orders

    def submit_order(self, symbol: str, qty: float, side: str, price: float, order_type: str = 'market') -> Dict[str, Any]:
        """
        Simulates execution of an order and appends it to order history.
        """
        side = side.lower()
        order_id = str(uuid.uuid4())[:8]
        created_at = datetime.now().isoformat()
        
        if side not in ['buy', 'sell']:
            res = {'status': 'rejected', 'reason': f'Invalid side: {side}'}
            self.orders.append({
                'order_id': order_id, 'symbol': symbol, 'side': side, 'qty': qty, 'price': price,
                'status': 'rejected', 'created_at': created_at
            })
            self._save_state()
            return res
            
        if qty <= 0:
            res = {'status': 'rejected', 'reason': f'Invalid qty: {qty}'}
            self.orders.append({
                'order_id': order_id, 'symbol': symbol, 'side': side, 'qty': qty, 'price': price,
                'status': 'rejected', 'created_at': created_at
            })
            self._save_state()
            return res

        trade_value = qty * price
        commission = max(self.min_commission, trade_value * self.commission_pct)
        commission = round(commission, 2)

        if side == 'buy':
            total_cost = trade_value + commission
            if self.cash < total_cost:
                res = {
                    'status': 'rejected',
                    'reason': f'Insufficient funds. Cost: {total_cost:.2f}, Cash: {self.cash:.2f}'
                }
                self.orders.append({
                    'order_id': order_id, 'symbol': symbol, 'side': 'buy', 'qty': qty, 'price': price,
                    'status': 'rejected', 'created_at': created_at
                })
                self._save_state()
                return res
            
            # Deduct cash
            self.cash -= total_cost
            
            # Update positions
            if symbol in self.positions:
                existing = self.positions[symbol]
                new_qty = existing['qty'] + qty
                new_avg = ((existing['qty'] * existing['avg_entry_price']) + trade_value) / new_qty
                
                self.positions[symbol] = {
                    'qty': round(new_qty, 8),
                    'avg_entry_price': round(new_avg, 8),
                    'current_price': price
                }
            else:
                self.positions[symbol] = {
                    'qty': round(qty, 8),
                    'avg_entry_price': round(price, 8),
                    'current_price': price
                }
                
            res = {
                'status': 'filled',
                'order_id': order_id,
                'symbol': symbol,
                'side': 'buy',
                'filled_qty': qty,
                'filled_price': price,
                'commission': commission,
                'cash_after': round(self.cash, 2)
            }
            self.orders.append({
                'order_id': order_id, 'symbol': symbol, 'side': 'buy', 'qty': qty, 'price': price,
                'status': 'filled', 'created_at': created_at
            })
            self._save_state()
            return res

        elif side == 'sell':
            if symbol not in self.positions or self.positions[symbol]['qty'] < qty:
                available = self.positions[symbol]['qty'] if symbol in self.positions else 0.0
                res = {
                    'status': 'rejected',
                    'reason': f'Insufficient shares. Selling: {qty}, Available: {available}'
                }
                self.orders.append({
                    'order_id': order_id, 'symbol': symbol, 'side': 'sell', 'qty': qty, 'price': price,
                    'status': 'rejected', 'created_at': created_at
                })
                self._save_state()
                return res
                
            # Add proceeds minus commission
            proceeds = trade_value - commission
            self.cash += proceeds
            
            # Update positions
            existing = self.positions[symbol]
            new_qty = existing['qty'] - qty
            
            if new_qty <= 0.0001:  # Close position completely
                self.positions.pop(symbol)
            else:
                self.positions[symbol] = {
                    'qty': round(new_qty, 8),
                    'avg_entry_price': existing['avg_entry_price'],
                    'current_price': price
                }
                
            res = {
                'status': 'filled',
                'order_id': order_id,
                'symbol': symbol,
                'side': 'sell',
                'filled_qty': qty,
                'filled_price': price,
                'commission': commission,
                'cash_after': round(self.cash, 2)
            }
            self.orders.append({
                'order_id': order_id, 'symbol': symbol, 'side': 'sell', 'qty': qty, 'price': price,
                'status': 'filled', 'created_at': created_at
            })
            self._save_state()
            return res
            
        self._save_state()
        return {'status': 'rejected', 'reason': 'Unknown error'}

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancels a simulated order if it is in pending state.
        """
        for order in self.orders:
            if order['order_id'] == order_id:
                if order['status'] in ['submitted', 'accepted', 'new', 'open']:
                    order['status'] = 'canceled'
                    self._save_state()
                    return True
        return False

    def get_filled_orders(self) -> List[Dict[str, Any]]:
        """
        Returns historically completed/filled orders.
        """
        filled_list = []
        for o in self.orders:
            status_lower = o['status'].lower()
            qty = float(o.get('filled_qty', o['qty'])) if status_lower == 'filled' else float(o.get('filled_qty', 0.0))
            if status_lower == 'filled' or (status_lower in ['canceled', 'cancelled', 'expired'] and qty > 0):
                filled_list.append({
                    'order_id': o['order_id'],
                    'symbol': o['symbol'],
                    'qty': qty,
                    'side': o['side'],
                    'price': o.get('filled_price', o['price']),
                    'commission': o.get('commission', 0.0),
                    'status': status_lower,
                    'timestamp': o.get('filled_at') or o.get('updated_at') or o['created_at']
                })
        return filled_list

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Returns active/open orders in the simulator.
        """
        open_list = []
        for o in self.orders:
            status_lower = o['status'].lower()
            if status_lower in ['submitted', 'accepted', 'new', 'partially_filled', 'open']:
                open_list.append({
                    'order_id': o['order_id'],
                    'symbol': o['symbol'],
                    'qty': float(o['qty']),
                    'filled_qty': float(o.get('filled_qty', 0.0)),
                    'side': o['side'],
                    'price': o.get('filled_price', o['price']),
                    'status': status_lower,
                    'created_at': o.get('filled_at') or o.get('updated_at') or o['created_at']
                })
        return open_list

    def get_tradable_assets(self) -> List[str]:
        """
        Returns ['*'] indicating that all symbols are supported in simulation.
        """
        return ['*']
