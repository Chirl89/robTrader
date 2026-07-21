from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseBroker(ABC):
    """
    Abstract base class for all broker execution clients.
    """

    @abstractmethod
    def get_cash(self) -> float:
        """Returns the available cash balance in EUR/USD."""
        pass

    @abstractmethod
    def get_portfolio_value(self) -> float:
        """Returns total portfolio value (cash + assets value)."""
        pass

    @abstractmethod
    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns active positions.
        Example output format:
        {
            'AAPL': {'qty': 10, 'avg_entry_price': 175.50, 'current_price': 180.00}
        }
        """
        pass

    @abstractmethod
    def submit_order(self, symbol: str, qty: float, side: str, price: float, order_type: str = 'market') -> Dict[str, Any]:
        """
        Executes a buy or sell trade.
        Returns a dictionary representing the transaction result:
        - 'status': 'filled' or 'rejected'
        - 'filled_qty': float
        - 'filled_price': float
        - 'commission': float
        - 'order_id': str
        """
        pass

    @abstractmethod
    def get_orders(self) -> List[Dict[str, Any]]:
        """
        Returns recent/active orders submitted to the broker.
        Returns a list of dictionaries:
        - 'order_id': str
        - 'symbol': str
        - 'side': str
        - 'qty': float
        - 'price': float
        - 'status': str
        - 'created_at': str
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancels a pending order in the broker.
        Returns True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def get_filled_orders(self) -> List[Dict[str, Any]]:
        """
        Returns historically completed/filled orders.
        """
        pass

    @abstractmethod
    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Returns currently active/open orders in the broker.
        """
        pass

    @abstractmethod
    def get_tradable_assets(self) -> List[str]:
        """
        Returns a list of tradable asset symbols supported by the broker.
        Use ['*'] to signal that any asset symbol is supported (unfiltered).
        """
        pass
