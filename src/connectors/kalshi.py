"""Kalshi exchange connector with REST and WebSocket support."""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Callable
import os
from dotenv import load_dotenv

import websockets
import requests
from requests.exceptions import RequestException

from .base import BaseConnector, Market, Order, OrderSide
from ..utils.crypto import load_private_key_from_file, load_private_key_from_string, sign_pss_text

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class KalshiConnector(BaseConnector):
    """Kalshi exchange connector."""

    REST_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
    WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    WS_PATH = "/trade-api/ws/v2"

    def __init__(
        self,
        api_key: Optional[str] = None,
        private_key_path: Optional[str] = None,
        private_key_string: Optional[str] = None
    ):
        """
        Initialize Kalshi connector.

        Args:
            api_key: Kalshi API key (or set KALSHI_API_KEY_ID env var)
            private_key_path: Path to private key file
            private_key_string: Private key as string (alternative to file)

        Raises:
            RuntimeError: If API key or private key is not provided
        """
        super().__init__("Kalshi")

        # Load API and private keys
        self.api_key = api_key or os.getenv("KALSHI_API_KEY_ID")
        if not self.api_key:
            raise RuntimeError("Kalshi API key not provided")

        # Load private key - priority: string > file path > env var
        if private_key_string:
            self.private_key = load_private_key_from_string(private_key_string)
        elif private_key_path:
            self.private_key = load_private_key_from_file(private_key_path)
        else:
            key_str = os.getenv("KALSHI_PRIVATE_KEY")
            if not key_str:
                raise RuntimeError("Kalshi private key not provided")
            self.private_key = load_private_key_from_string(key_str)

        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._subscriptions: Dict[str, List[Callable]] = {}
        self._ws_task: Optional[asyncio.Task] = None
        self._reconnect_delay = 1
        self._max_reconnect_delay = 60

        logger.info(f"Initialized {self.name} connector")

    def _build_auth_headers(self, method: str, path: str) -> Dict[str, str]:
        """
        Build authentication headers for API requests.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path without query params

        Returns:
            Dictionary of auth headers
        """
        timestamp = str(int(time.time() * 1000))
        message = timestamp + method + path
        signature = sign_pss_text(self.private_key, message)

        return {
            "KALSHI-ACCESS-KEY": self.api_key,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json"
        }

    async def _api_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make authenticated API request.

        Args:
            method: HTTP method
            endpoint: API endpoint (without base URL)
            params: Query parameters
            data: Request body data

        Returns:
            Response JSON

        Raises:
            RequestException: If request fails
        """
        url = f"{self.REST_BASE_URL}{endpoint}"
        path = endpoint.split("?")[0]  # Remove query params for signing
        headers = self._build_auth_headers(method, path)

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=data,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            logger.error(f"API request failed: {e}")
            raise

    async def connect(self) -> None:
        """Establish WebSocket connection to Kalshi."""
        if self._connected:
            logger.warning("Already connected to Kalshi")
            return

        logger.info("Connecting to Kalshi WebSocket...")
        self._ws_task = asyncio.create_task(self._ws_loop())

        # Wait a bit for connection to establish
        for _ in range(10):
            await asyncio.sleep(0.1)
            if self._connected:
                logger.info("Successfully connected to Kalshi WebSocket")
                return

        logger.warning("WebSocket connection may not be established yet")

    async def _ws_loop(self) -> None:
        """WebSocket connection loop with auto-reconnect."""
        while True:
            try:
                await self._connect_ws()
            except asyncio.CancelledError:
                logger.info("WebSocket loop cancelled")
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self._connected = False
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    async def _connect_ws(self) -> None:
        """Connect to WebSocket and handle messages."""
        headers = self._build_auth_headers("GET", self.WS_PATH)

        async with websockets.connect(self.WS_URL, additional_headers=headers) as websocket:
            self.ws = websocket
            self._connected = True
            self._reconnect_delay = 1  # Reset backoff on successful connection
            logger.info("WebSocket connected")

            # Resubscribe to markets
            for ticker in self._subscriptions.keys():
                await self._send_subscribe(ticker)

            # Handle incoming messages
            async for message in websocket:
                await self._handle_ws_message(message)

    async def _send_subscribe(self, ticker: str) -> None:
        """Send subscription message for a ticker."""
        if not self.ws:
            return

        subscribe_msg = {
            "type": "subscribe",
            "channel": "orderbook_delta",
            "ticker": ticker
        }
        await self.ws.send(json.dumps(subscribe_msg))
        logger.debug(f"Subscribed to {ticker}")

    async def _handle_ws_message(self, message: str) -> None:
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)

            # Handle different message types
            if data.get("type") == "orderbook_delta":
                ticker = data.get("ticker")
                if ticker in self._subscriptions:
                    market = self._parse_orderbook_update(data)
                    for callback in self._subscriptions[ticker]:
                        try:
                            await callback(market)
                        except Exception as e:
                            logger.error(f"Callback error for {ticker}: {e}")
        except json.JSONDecodeError:
            logger.error(f"Failed to parse WebSocket message: {message}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")

    def _parse_orderbook_update(self, data: Dict) -> Market:
        """Parse orderbook update into Market object."""
        ticker = data.get("ticker", "")

        # Extract best bid/ask from orderbook and normalize from cents to decimal
        yes_bids = data.get("yes_bids", [])
        yes_asks = data.get("yes_asks", [])
        no_bids = data.get("no_bids", [])
        no_asks = data.get("no_asks", [])

        return Market(
            ticker=ticker,
            title=data.get("title", ""),
            yes_bid=yes_bids[0]["price"] / 100.0 if yes_bids else None,
            yes_ask=yes_asks[0]["price"] / 100.0 if yes_asks else None,
            no_bid=no_bids[0]["price"] / 100.0 if no_bids else None,
            no_ask=no_asks[0]["price"] / 100.0 if no_asks else None,
            metadata=data
        )

    async def disconnect(self) -> None:
        """Disconnect from Kalshi."""
        logger.info("Disconnecting from Kalshi...")

        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            await self.ws.close()
            self.ws = None

        self._connected = False
        self._subscriptions.clear()
        logger.info("Disconnected from Kalshi")

    async def get_markets(self, category: Optional[str] = None) -> List[Market]:
        """
        Get available binary sports markets from Kalshi.

        Args:
            category: Optional category filter. Currently only "Sports" is
                handled explicitly and is applied client-side because the
                Kalshi markets endpoint does not support a "Sports" category
                filter.

        Returns:
            List of binary Market objects
        """
        # Base query params – do not send category to Kalshi; we filter
        # on the client side instead.
        params = {
            "mve_filter": "exclude"  # Exclude multi-variate event markets
        }

        # Normalize requested category. Default behavior remains "Sports" to
        # match the public connector interface used in tests.
       
        try:
            response = await self._api_request("GET", "/markets", params=params)
            markets = response.get("markets", [])

            binary_markets = []
            for m in markets:
                # Filter for binary markets (API already excludes multi-variate events)
                market_type = m.get("market_type", "").lower()
                num_outcomes = m.get("num_outcomes")

                # Skip if market has more than 2 outcomes
                if num_outcomes and num_outcomes > 2:
                    continue

                # Accept market if it's explicitly binary OR has exactly 2 outcomes
                is_binary = market_type == "binary" or num_outcomes == 2
                if not is_binary:
                    continue

                # Apply client-side category filtering. Right now we only
                # treat "Sports" specially; other categories fall back to
                # returning all binary markets.
                ticker = m.get("ticker","").lower()
                if not "game" in ticker:
                    continue

                # Normalize prices from cents (0-100) to decimal (0-1)
                yes_bid = m.get("yes_bid") / 100.0 if m.get("yes_bid") is not None else None
                yes_ask = m.get("yes_ask") / 100.0 if m.get("yes_ask") is not None else None
                no_bid = m.get("no_bid") / 100.0 if m.get("no_bid") is not None else None
                no_ask = m.get("no_ask") / 100.0 if m.get("no_ask") is not None else None

                binary_markets.append(
                    Market(
                        ticker=m.get("ticker", ""),
                        title=m.get("title", ""),
                        yes_bid=yes_bid,
                        yes_ask=yes_ask,
                        no_bid=no_bid,
                        no_ask=no_ask,
                        volume=m.get("volume"),
                        liquidity=m.get("liquidity"),
                        metadata=m
                    )
                )
            logger.info(f"Fetched {len(binary_markets)} binary sports markets from Kalshi")
            return binary_markets

        except Exception as e:
            logger.error(f"Failed to get markets: {e}")
            return []

    async def get_market(self, ticker: str) -> Optional[Market]:
        """
        Get specific market by ticker.

        Args:
            ticker: Market ticker

        Returns:
            Market object or None
        """
        try:
            response = await self._api_request("GET", f"/markets/{ticker}")
            m = response.get("market", {})

            return Market(
                ticker=m.get("ticker", ""),
                title=m.get("title", ""),
                yes_bid=m.get("yes_bid"),
                yes_ask=m.get("yes_ask"),
                no_bid=m.get("no_bid"),
                no_ask=m.get("no_ask"),
                volume=m.get("volume"),
                liquidity=m.get("liquidity"),
                metadata=m
            )
        except Exception as e:
            logger.error(f"Failed to get market {ticker}: {e}")
            return None

    async def subscribe_market(self, ticker: str, callback: Callable) -> None:
        """
        Subscribe to market updates.

        Args:
            ticker: Market ticker
            callback: Async callback function receiving Market updates
        """
        if ticker not in self._subscriptions:
            self._subscriptions[ticker] = []

        self._subscriptions[ticker].append(callback)

        # Send subscription if connected
        if self._connected and self.ws:
            await self._send_subscribe(ticker)

        logger.info(f"Subscribed to market {ticker}")

    async def place_order(self, order: Order) -> Dict[str, Any]:
        """
        Place order on Kalshi.

        Args:
            order: Order object

        Returns:
            Order response
        """
        order_data = {
            "ticker": order.ticker,
            "side": order.side.value,
            "quantity": order.quantity,
            "price": order.price,
            "type": order.order_type
        }

        try:
            response = await self._api_request("POST", "/orders", data=order_data)
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
        try:
            await self._api_request("DELETE", f"/orders/{order_id}")
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
        try:
            response = await self._api_request("GET", "/balance")
            return response
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return {}

    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions.

        Returns:
            List of positions
        """
        try:
            response = await self._api_request("GET", "/positions")
            return response.get("positions", [])
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
