import os
from typing import Dict, Any, List
from broker.base_broker import BaseBroker

class AlpacaBroker(BaseBroker):
    """
    Broker implementation connecting to the live/paper Alpaca SDK API.
    """

    def __init__(self, api_key: str = None, secret_key: str = None, is_paper: bool = True):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY_ID")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        
        env = os.getenv("ALPACA_ENV", "paper").lower()
        self.is_paper = env == "paper" if api_key is None else is_paper
        
        self.initialized = bool(self.api_key and self.secret_key)
        self._trading_client = None

    def _init_client(self):
        if not self.initialized:
            raise ValueError("Alpaca API credentials not set. Please check your .env file.")
        
        if self._trading_client is None:
            from alpaca.trading.client import TradingClient
            self._trading_client = TradingClient(self.api_key, self.secret_key, paper=self.is_paper)

    def get_cash(self) -> float:
        self._init_client()
        account = self._trading_client.get_account()
        return float(account.cash)

    def get_portfolio_value(self) -> float:
        self._init_client()
        account = self._trading_client.get_account()
        return float(account.portfolio_value)

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        self._init_client()
        alpaca_positions = self._trading_client.get_all_positions()
        
        positions_dict = {}
        for pos in alpaca_positions:
            symbol = pos.symbol
            positions_dict[symbol] = {
                'qty': float(pos.qty),
                'avg_entry_price': float(pos.avg_entry_price),
                'current_price': float(pos.current_price)
            }
        return positions_dict

    def get_orders(self) -> List[Dict[str, Any]]:
        """
        Retrieves recent orders (all statuses) from the Alpaca API.
        """
        self._init_client()
        
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        
        request_params = GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            limit=20
        )
        
        alpaca_orders = self._trading_client.get_orders(request_params)
        
        orders_list = []
        for order in alpaca_orders:
            # Parse price (fallback if not filled yet)
            price = 0.0
            if order.filled_avg_price:
                price = float(order.filled_avg_price)
            elif order.limit_price:
                price = float(order.limit_price)
                
            orders_list.append({
                'order_id': str(order.id),
                'symbol': order.symbol,
                'side': order.side.value.lower(),
                'qty': float(order.qty) if order.qty else 0.0,
                'price': price,
                'status': order.status.value.lower(),
                'created_at': order.created_at.isoformat() if order.created_at else ''
            })
            
        return orders_list

    def submit_order(self, symbol: str, qty: float, side: str, price: float, order_type: str = 'market') -> Dict[str, Any]:
        """
        Submits an order (market or limit) to Alpaca.
        Side must be 'buy' or 'sell'.
        """
        self._init_client()
        
        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        
        order_side = OrderSide.BUY if side.lower() == 'buy' else OrderSide.SELL
        
        # Normalize crypto symbols (e.g., BTCUSD -> BTC/USD)
        sym = symbol.upper()
        crypto_assets = {'BTC', 'ETH', 'LTC', 'SOL', 'DOGE', 'XRP', 'ADA', 'DOT', 'LINK', 'UNI'}
        if '/' not in sym:
            for asset in crypto_assets:
                if sym == f"{asset}USD":
                    sym = f"{asset}/USD"
                    break
        symbol = sym
        
        # Alpaca requires TimeInForce.GTC for crypto orders, but TimeInForce.DAY for stock orders
        tif = TimeInForce.GTC if '/' in symbol else TimeInForce.DAY
        
        # Alpaca order request based on type
        if order_type.lower() == 'limit':
            order_request = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif,
                limit_price=round(price, 2) if '/' not in symbol else price
            )
        else:
            order_request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif
            )
        
        # Submit order
        try:
            alpaca_order = self._trading_client.submit_order(order_request)
            order_id = str(alpaca_order.id)
            commission = 0.0
            
            # For paper/dry execution, query status
            filled_qty = qty
            filled_price = price
            status = 'submitted'
            
            try:
                order_detail = self._trading_client.get_order_by_id(order_id)
                if order_detail.filled_qty:
                    filled_qty = float(order_detail.filled_qty)
                if order_detail.filled_avg_price:
                    filled_price = float(order_detail.filled_avg_price)
                status = order_detail.status.value.lower()
            except Exception:
                pass
                
            return {
                'status': status,
                'order_id': order_id,
                'symbol': symbol,
                'side': side.lower(),
                'filled_qty': filled_qty,
                'filled_price': filled_price,
                'commission': commission,
                'cash_after': self.get_cash()
            }
        except Exception as e:
            err_msg = str(e)
            try:
                if hasattr(e, 'message') and e.message:
                    err_msg = e.message
            except Exception:
                pass
                
            return {
                'status': 'rejected',
                'reason': err_msg,
                'symbol': symbol,
                'side': side.lower(),
                'filled_qty': 0.0,
                'filled_price': 0.0,
                'commission': 0.0,
                'cash_after': self.get_cash()
            }

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancels a pending order in Alpaca.
        """
        self._init_client()
        import logging
        logger = logging.getLogger("robTrader.AlpacaBroker")
        try:
            self._trading_client.cancel_order_by_id(order_id)
            logger.info(f"Successfully requested cancellation for order {order_id} in Alpaca.")
            return True
        except Exception as e:
            logger.error(f"Alpaca failed to cancel order {order_id}: {e}")
            return False

    def get_filled_orders(self) -> List[Dict[str, Any]]:
        """
        Returns historically completed/filled orders.
        """
        self._init_client()
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        import logging
        logger = logging.getLogger("robTrader.AlpacaBroker")
        
        req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=50)
        try:
            orders = self._trading_client.get_orders(filter=req)
        except Exception as e:
            logger.error(f"Error fetching closed orders: {e}")
            return []
            
        orders_list = []
        for o in orders:
            status_lower = o.status.value.lower()
            filled_qty = float(o.filled_qty) if o.filled_qty else 0.0
            if status_lower == 'filled' or (status_lower in ['canceled', 'cancelled', 'expired'] and filled_qty > 0):
                orders_list.append({
                    'order_id': str(o.id),
                    'symbol': o.symbol,
                    'qty': filled_qty,
                    'side': o.side.value.lower(),
                    'price': float(o.filled_avg_price) if o.filled_avg_price else 0.0,
                    'commission': 0.0,
                    'status': status_lower,
                    'timestamp': o.filled_at.isoformat() if o.filled_at else (o.updated_at.isoformat() if o.updated_at else (o.created_at.isoformat() if o.created_at else None))
                })
        return orders_list

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Retrieves active/open orders (new, partially_filled, etc.) from the Alpaca API.
        """
        self._init_client()
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        import logging
        logger = logging.getLogger("robTrader.AlpacaBroker")
        
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=50)
        try:
            orders = self._trading_client.get_orders(filter=req)
        except Exception as e:
            logger.error(f"Error fetching open orders from Alpaca: {e}")
            return []
            
        orders_list = []
        for o in orders:
            price = 0.0
            if o.filled_avg_price:
                price = float(o.filled_avg_price)
            elif o.limit_price:
                price = float(o.limit_price)
                
            orders_list.append({
                'order_id': str(o.id),
                'symbol': o.symbol,
                'side': o.side.value.lower(),
                'qty': float(o.qty) if o.qty else 0.0,
                'filled_qty': float(o.filled_qty) if o.filled_qty else 0.0,
                'price': price,
                'status': o.status.value.lower(),
                'created_at': o.created_at.isoformat() if o.created_at else ''
            })
        return orders_list

    def get_tradable_assets(self) -> List[str]:
        """
        Returns all active and tradable assets in Alpaca.
        """
        self._init_client()
        from alpaca.trading.requests import GetAssetsRequest
        from alpaca.trading.enums import AssetStatus
        
        req = GetAssetsRequest(status=AssetStatus.ACTIVE)
        assets = self._trading_client.get_all_assets(req)
        return [a.symbol for a in assets if a.tradable]
