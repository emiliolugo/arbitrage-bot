"""Polymarket exchange connector."""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
import os

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

from .base import BaseConnector, Market, Order, OrderSide


logger = logging.getLogger(__name__)


class PolymarketConnector(BaseConnector):
    """Polymarket exchange connector."""

    def __init__(
        self,
        private_key: Optional[str] = None,
        host: str = "https://clob.polymarket.com",
        chain_id: int = 137,  # Polygon mainnet
        signature_type: int = 0  # EOA
    ):
        """
        Initialize Polymarket connector.

        Args:
            private_key: Ethereum private key (or set POLYMARKET_PRIVATE_KEY env var)
            host: Polymarket CLOB API host
            chain_id: Blockchain chain ID
            signature_type: Signature type (0 for EOA, 1 for Poly Proxy)

        Raises:
            RuntimeError: If private key is not provided
        """
        super().__init__("Polymarket")

        # Load private key
        self.private_key = private_key or os.getenv("POLYMARKET_PRIVATE_KEY")
        if not self.private_key:
            raise RuntimeError("Polymarket private key not provided")

        self.host = host
        self.chain_id = chain_id
        self.signature_type = signature_type

        self.client: Optional[ClobClient] = None
        self._subscriptions: Dict[str, List[Callable]] = {}
        self._price_update_tasks: Dict[str, asyncio.Task] = {}

        logger.info(f"Initialized {self.name} connector")

    async def connect(self) -> None:
        """Initialize Polymarket client connection."""
        if self._connected:
            logger.warning("Already connected to Polymarket")
            return

        try:
            self.client = ClobClient(
                self.host,
                key=self.private_key,
                chain_id=self.chain_id,
                signature_type=self.signature_type,
            )
            self._connected = True
            logger.info("Successfully connected to Polymarket")
        except Exception as e:
            logger.error(f"Failed to connect to Polymarket: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from Polymarket."""
        logger.info("Disconnecting from Polymarket...")

        # Cancel all subscription tasks
        for task in self._price_update_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._price_update_tasks.clear()
        self._subscriptions.clear()
        self.client = None
        self._connected = False

        logger.info("Disconnected from Polymarket")

    async def get_markets(self, category: Optional[str] = None) -> List[Market]:
        """
        Get available markets from Polymarket.

        Args:
            category: Optional category filter (not directly supported by API)

        Returns:
            List of Market objects
        """
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        try:
            # Get all markets
            markets_data = self.client.get_markets()

            markets = []
            for m in markets_data:
                # Polymarket has condition tokens, each market can have multiple outcomes
                # For binary markets, there are usually YES/NO tokens
                tokens = m.get("tokens", [])

                # Get orderbook for each token to get prices
                yes_token = None
                no_token = None

                for token in tokens:
                    outcome = token.get("outcome", "").upper()
                    if outcome == "YES":
                        yes_token = token
                    elif outcome == "NO":
                        no_token = token

                market = Market(
                    ticker=m.get("condition_id", ""),
                    title=m.get("question", ""),
                    volume=m.get("volume"),
                    liquidity=m.get("liquidity"),
                    metadata=m
                )

                # Fetch prices for tokens if available
                if yes_token:
                    token_id = yes_token.get("token_id")
                    if token_id:
                        try:
                            book = self.client.get_order_book(token_id)
                            if book:
                                bids = book.get("bids", [])
                                asks = book.get("asks", [])
                                market.yes_bid = float(bids[0]["price"]) if bids else None
                                market.yes_ask = float(asks[0]["price"]) if asks else None
                        except Exception as e:
                            logger.debug(f"Failed to get orderbook for {token_id}: {e}")

                if no_token:
                    token_id = no_token.get("token_id")
                    if token_id:
                        try:
                            book = self.client.get_order_book(token_id)
                            if book:
                                bids = book.get("bids", [])
                                asks = book.get("asks", [])
                                market.no_bid = float(bids[0]["price"]) if bids else None
                                market.no_ask = float(asks[0]["price"]) if asks else None
                        except Exception as e:
                            logger.debug(f"Failed to get orderbook for {token_id}: {e}")

                markets.append(market)

            # Apply category filter if specified
            if category:
                category_lower = category.lower()
                markets = [
                    m for m in markets
                    if category_lower in m.title.lower() or
                    category_lower in str(m.metadata.get("tags", [])).lower()
                ]

            return markets

        except Exception as e:
            logger.error(f"Failed to get markets: {e}")
            return []

    async def get_market(self, ticker: str) -> Optional[Market]:
        """
        Get specific market by ticker (condition_id).

        Args:
            ticker: Market condition_id

        Returns:
            Market object or None
        """
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        try:
            markets = await self.get_markets()
            for market in markets:
                if market.ticker == ticker:
                    return market
            return None
        except Exception as e:
            logger.error(f"Failed to get market {ticker}: {e}")
            return None

    async def _poll_market_updates(self, ticker: str, token_id: str, interval: float = 1.0) -> None:
        """
        Poll market for price updates.

        Args:
            ticker: Market ticker
            token_id: Token ID to poll
            interval: Polling interval in seconds
        """
        while ticker in self._subscriptions:
            try:
                book = self.client.get_order_book(token_id)
                if book:
                    market = Market(
                        ticker=ticker,
                        title="",  # Would need to fetch full market data
                        metadata=book
                    )

                    bids = book.get("bids", [])
                    asks = book.get("asks", [])

                    # Assuming YES token (adjust based on your needs)
                    market.yes_bid = float(bids[0]["price"]) if bids else None
                    market.yes_ask = float(asks[0]["price"]) if asks else None

                    # Call callbacks
                    for callback in self._subscriptions[ticker]:
                        try:
                            await callback(market)
                        except Exception as e:
                            logger.error(f"Callback error for {ticker}: {e}")

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error polling market {ticker}: {e}")
                await asyncio.sleep(interval)

    async def subscribe_market(self, ticker: str, callback: Callable) -> None:
        """
        Subscribe to market updates (via polling).

        Note: Polymarket doesn't have native WebSocket support in py_clob_client,
        so we poll the API for updates.

        Args:
            ticker: Market ticker (condition_id)
            callback: Async callback function receiving Market updates
        """
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        if ticker not in self._subscriptions:
            self._subscriptions[ticker] = []

            # Get token_id for this market
            market = await self.get_market(ticker)
            if market and market.metadata:
                tokens = market.metadata.get("tokens", [])
                if tokens:
                    token_id = tokens[0].get("token_id")
                    if token_id:
                        # Start polling task
                        task = asyncio.create_task(
                            self._poll_market_updates(ticker, token_id)
                        )
                        self._price_update_tasks[ticker] = task

        self._subscriptions[ticker].append(callback)
        logger.info(f"Subscribed to market {ticker}")

    async def place_order(self, order: Order) -> Dict[str, Any]:
        """
        Place order on Polymarket.

        Args:
            order: Order object

        Returns:
            Order response

        Note: You'll need to map ticker to token_id and handle the order properly
        """
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        try:
            # Get token_id from ticker
            market = await self.get_market(order.ticker)
            if not market or not market.metadata:
                raise ValueError(f"Market {order.ticker} not found")

            tokens = market.metadata.get("tokens", [])
            if not tokens:
                raise ValueError(f"No tokens found for market {order.ticker}")

            # For now, assume first token (you should select based on YES/NO)
            token_id = tokens[0].get("token_id")

            # Map OrderSide to Polymarket side
            side = "BUY" if order.side == OrderSide.BUY else "SELL"

            # Create order
            order_args = OrderArgs(
                token_id=token_id,
                price=order.price,
                size=order.quantity,
                side=side,
                fee_rate_bps=0,  # Adjust as needed
            )

            # Create and post order
            signed_order = self.client.create_order(order_args)
            response = self.client.post_order(signed_order)

            logger.info(f"Order placed: {response}")
            return response

        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel order.

        Args:
            order_id: Order ID

        Returns:
            True if successful
        """
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        try:
            self.client.cancel_order(order_id)
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_balance(self) -> Dict[str, float]:
        """
        Get account balance.

        Returns:
            Balance information
        """
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        try:
            # Get USDC balance (Polymarket uses USDC)
            address = self.client.get_address()
            # Note: py_clob_client may not have direct balance API
            # You may need to query blockchain directly
            logger.warning("Balance API not fully implemented")
            return {"address": address}
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return {}

    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions.

        Returns:
            List of positions
        """
        if not self.client:
            raise RuntimeError("Not connected to Polymarket")

        try:
            # Get open orders as positions
            orders = self.client.get_orders()
            return orders
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
