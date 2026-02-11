"""Base connector abstract class for exchange connections."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class OrderSide(Enum):
    """Order side enum."""
    BUY = "buy"
    SELL = "sell"


@dataclass
class Market:
    """Market data structure."""
    ticker: str
    title: str
    yes_price: Optional[float] = None
    no_price: Optional[float] = None
    yes_bid: Optional[float] = None
    yes_ask: Optional[float] = None
    no_bid: Optional[float] = None
    no_ask: Optional[float] = None
    volume: Optional[float] = None
    liquidity: Optional[float] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class Order:
    """Order structure."""
    ticker: str
    side: OrderSide
    quantity: int
    price: float
    order_type: str = "limit"
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseConnector(ABC):
    """Abstract base class for exchange connectors."""

    def __init__(self, name: str):
        """
        Initialize base connector.

        Args:
            name: Name of the exchange (e.g., "Kalshi", "Polymarket")
        """
        self.name = name
        self._connected = False

    @property
    def connected(self) -> bool:
        """Check if connector is connected."""
        return self._connected

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the exchange."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the exchange."""
        pass

    @abstractmethod
    async def get_markets(self, category: Optional[str] = None) -> List[Market]:
        """
        Get available markets.

        Args:
            category: Optional category filter (e.g., "Sports")

        Returns:
            List of Market objects
        """
        pass

    @abstractmethod
    async def get_market(self, ticker: str) -> Optional[Market]:
        """
        Get a specific market by ticker.

        Args:
            ticker: Market ticker symbol

        Returns:
            Market object or None if not found
        """
        pass

    @abstractmethod
    async def subscribe_market(self, ticker: str, callback) -> None:
        """
        Subscribe to market updates.

        Args:
            ticker: Market ticker to subscribe to
            callback: Callback function for updates
        """
        pass

    @abstractmethod
    async def place_order(self, order: Order) -> Dict[str, Any]:
        """
        Place an order.

        Args:
            order: Order object

        Returns:
            Order response dictionary
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_balance(self) -> Dict[str, float]:
        """
        Get account balance.

        Returns:
            Dictionary with balance information
        """
        pass

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions.

        Returns:
            List of position dictionaries
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, connected={self.connected})>"
