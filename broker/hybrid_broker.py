import os
import logging
from typing import Dict, Any, List
from broker.base_broker import BaseBroker
from broker.alpaca_broker import AlpacaBroker
from broker.simulator_broker import SimulatorBroker

logger = logging.getLogger("robTrader.HybridBroker")

class HybridBroker(BaseBroker):
    """
    A broker that routes US stocks and Cryptos to Alpaca and fallback assets (like IBEX) to SimulatorBroker.
    """
    def __init__(self, alpaca_broker: AlpacaBroker, simulator_broker: SimulatorBroker):
        self.alpaca_broker = alpaca_broker
        self.simulator_broker = simulator_broker
        self._alpaca_assets = None

    def _is_alpaca_asset(self, symbol: str) -> bool:
        sym_upper = symbol.upper()
        # Non-US exchanges like Madrid (.MC) are not supported by Alpaca
        if '.MC' in sym_upper:
            return False
            
        if self._alpaca_assets is None:
            try:
                logger.info("Fetching Alpaca tradable assets to build routing table...")
                assets = self.alpaca_broker.get_tradable_assets()
                self._alpaca_assets = {a.upper() for a in assets}
                logger.info(f"Loaded {len(self._alpaca_assets)} Alpaca tradable assets.")
            except Exception as e:
                logger.error(f"Failed to load Alpaca tradable assets: {e}. Falling back to suffix rule.")
                return '.MC' not in sym_upper
                
        norm_sym = sym_upper.replace('/', '').replace('-', '')
        return norm_sym in {a.replace('/', '').replace('-', '') for a in self._alpaca_assets}

    def get_cash(self) -> float:
        # Sum both cash values to show the total cash in dashboard
        try:
            alpaca_cash = self.alpaca_broker.get_cash()
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca cash: {e}")
            alpaca_cash = 0.0
        return round(alpaca_cash + self.simulator_broker.get_cash(), 2)

    def get_portfolio_value(self) -> float:
        try:
            alpaca_val = self.alpaca_broker.get_portfolio_value()
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca portfolio value: {e}")
            alpaca_val = 0.0
        return round(alpaca_val + self.simulator_broker.get_portfolio_value(), 2)

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        try:
            positions = self.alpaca_broker.get_positions()
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca positions: {e}")
            positions = {}
            
        sim_positions = self.simulator_broker.get_positions()
        # Merge positions
        for sym, pos in sim_positions.items():
            positions[sym] = pos
        return positions

    def submit_order(self, symbol: str, qty: float, side: str, price: float, order_type: str = 'market') -> Dict[str, Any]:
        if self._is_alpaca_asset(symbol):
            logger.info(f"Routing order for {symbol} to AlpacaBroker")
            return self.alpaca_broker.submit_order(symbol, qty, side, price, order_type)
        else:
            logger.info(f"Routing order for {symbol} to SimulatorBroker (local simulation)")
            # Make sure simulator has the latest price updated before placing the order
            self.simulator_broker.update_prices({symbol: price})
            return self.simulator_broker.submit_order(symbol, qty, side, price, order_type)

    def get_orders(self) -> List[Dict[str, Any]]:
        try:
            orders = self.alpaca_broker.get_orders()
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca orders: {e}")
            orders = []
        sim_orders = self.simulator_broker.get_orders()
        return orders + sim_orders

    def cancel_order(self, order_id: str) -> bool:
        # Try simulator first if the order_id is in simulator orders
        for order in self.simulator_broker.get_orders():
            if order['order_id'] == order_id:
                return self.simulator_broker.cancel_order(order_id)
                
        # Otherwise, try Alpaca
        try:
            return self.alpaca_broker.cancel_order(order_id)
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id} on Alpaca: {e}")
            return False

    def get_filled_orders(self) -> List[Dict[str, Any]]:
        try:
            alpaca_filled = self.alpaca_broker.get_filled_orders()
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca filled orders: {e}")
            alpaca_filled = []
        return alpaca_filled + self.simulator_broker.get_filled_orders()

    def get_open_orders(self) -> List[Dict[str, Any]]:
        try:
            alpaca_open = self.alpaca_broker.get_open_orders()
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca open orders: {e}")
            alpaca_open = []
        return alpaca_open + self.simulator_broker.get_open_orders()

    def get_tradable_assets(self) -> List[str]:
        # Return ['*'] so scheduler does not filter out any targets.
        # HybridBroker can handle any symbol (supported by Alpaca or Simulator)
        return ['*']
