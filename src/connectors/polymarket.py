"""Polymarket exchange connector using the Gamma API for market data."""

import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Any, Callable

import requests
from requests.exceptions import RequestException
from dotenv import load_dotenv

from .base import BaseConnector, Market, Order, OrderSide

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class PolymarketConnector(BaseConnector):
    """Polymarket exchange connector using the Gamma API for binary sports market data."""

    GAMMA_API_URL = "https://gamma-api.polymarket.com"
    CLOB_API_URL = "https://clob.polymarket.com"

    def __init__(self, private_key: Optional[str] = None):
        """
        Initialize Polymarket connector.

        Args:
            private_key: Polymarket wallet private key (or set POLYMARKET_PRIVATE_KEY env var)
        """
        super().__init__("Polymarket")

        self.private_key = private_key or os.getenv("POLYMARKET_PRIVATE_KEY")
        self._subscriptions: Dict[str, List[Callable]] = {}
        self._poll_tasks: List[asyncio.Task] = []
        self._poll_interval = 1.0  # seconds between polls

        logger.info(f"Initialized {self.name} connector")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _gamma_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
    ) -> Any:
        """
        Make a GET request to the Gamma API.

        Args:
            endpoint: API endpoint path (e.g. "/events")
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            RequestException: If the request fails
        """
        url = f"{self.GAMMA_API_URL}{endpoint}"
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            logger.error(f"Gamma API request failed: {e}")
            raise

    def _parse_market(self, m: Dict, event_category: str = "") -> Optional[Market]:
        """
        Parse a raw Gamma API market dict into a Market object.

        Args:
            m: Raw market dictionary from Gamma API
            event_category: Category string from the parent event

        Returns:
            Market object, or None if the market is not a valid binary market
        """
        # Parse outcomes (JSON string → list)
        outcomes_raw = m.get("outcomes", "[]")
        try:
            outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else (outcomes_raw or [])
        except (json.JSONDecodeError, TypeError):
            return None

        # Binary markets only (exactly 2 outcomes: Yes / No)
        if len(outcomes) != 2:
            return None

        # Skip closed markets
        if m.get("closed"):
            return None

        # Parse outcome prices (JSON string → list of floats)
        prices_raw = m.get("outcomePrices", "[]")
        try:
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else (prices_raw or [])
        except (json.JSONDecodeError, TypeError):
            prices = []

        # Parse CLOB token IDs (JSON string → list of strings)
        token_ids_raw = m.get("clobTokenIds", "[]")
        try:
            token_ids = json.loads(token_ids_raw) if isinstance(token_ids_raw, str) else (token_ids_raw or [])
        except (json.JSONDecodeError, TypeError):
            token_ids = []

        # Build tokens list for metadata (test suite expects this structure)
        tokens = []
        for i, outcome in enumerate(outcomes):
            token = {
                "outcome": outcome,
                "token_id": token_ids[i] if i < len(token_ids) else None,
                "price": float(prices[i]) if i < len(prices) and prices[i] is not None else None,
            }
            tokens.append(token)

        # YES / NO outcome prices (Polymarket uses 0-1 scale)
        yes_price = float(prices[0]) if len(prices) > 0 and prices[0] is not None else None
        no_price = float(prices[1]) if len(prices) > 1 and prices[1] is not None else None

        # Best bid / ask from Gamma API (reported for the YES outcome)
        best_bid = m.get("bestBid")
        best_ask = m.get("bestAsk")

        yes_bid = float(best_bid) if best_bid is not None else None
        yes_ask = float(best_ask) if best_ask is not None else None

        # Derive NO bid / ask from the complement of YES prices
        # Buying NO at X is equivalent to selling YES at (1 - X)
        no_bid = round(1.0 - yes_ask, 6) if yes_ask is not None else None
        no_ask = round(1.0 - yes_bid, 6) if yes_bid is not None else None

        condition_id = m.get("conditionId", m.get("id", ""))

        return Market(
            ticker=condition_id,
            title=m.get("question", ""),
            yes_price=yes_price,
            no_price=no_price,
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            no_bid=no_bid,
            no_ask=no_ask,
            volume=m.get("volumeNum"),
            liquidity=m.get("liquidityNum"),
            metadata={
                "tokens": tokens,
                "closed": m.get("closed", False),
                "condition_id": condition_id,
                "market_id": m.get("id"),
                "slug": m.get("slug"),
                "event_category": event_category,
                "enable_order_book": m.get("enableOrderBook", False),
                "accepting_orders": m.get("acceptingOrders", False),
                "clob_token_ids": token_ids,
            },
        )

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish connection to Polymarket Gamma API."""
        if self._connected:
            logger.warning("Already connected to Polymarket")
            return

        logger.info("Connecting to Polymarket Gamma API...")
        try:
            self._gamma_request("/markets", params={"limit": 1})
            self._connected = True
            logger.info("Successfully connected to Polymarket Gamma API")
        except Exception as e:
            logger.error(f"Failed to connect to Polymarket: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from Polymarket and cancel all polling tasks."""
        logger.info("Disconnecting from Polymarket...")

        for task in self._poll_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._poll_tasks.clear()
        self._subscriptions.clear()
        self._connected = False
        logger.info("Disconnected from Polymarket")

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_markets(self, category: Optional[str] = None) -> List[Market]:
        """
        Get available binary sports markets from Polymarket via the Gamma API.

        Uses the /events endpoint to naturally group markets by category.

        Args:
            category: Category filter (defaults to "Sports", pass "" for all)

        Returns:
            List of binary Market objects
        """
        # Default to sports category
        if category is None:
            category = "Sports"

        params = {
            "closed": "false",
            "limit": 100,
        }

        try:
            events = self._gamma_request("/events", params=params)

            binary_markets = []
            for event in events:
                event_category = event.get("category", "") or ""

                # Filter by category (empty string = no filter)
                if category and category.lower() not in event_category.lower():
                    continue

                for m in event.get("markets", []):
                    market = self._parse_market(m, event_category=event_category)
                    if market is not None:
                        binary_markets.append(market)

            logger.info(
                f"Fetched {len(binary_markets)} binary markets from Polymarket "
                f"(category={category!r})"
            )
            return binary_markets

        except Exception as e:
            logger.error(f"Failed to get markets: {e}")
            return []

    async def get_market(self, ticker: str) -> Optional[Market]:
        """
        Get a specific market by ticker (conditionId).

        Args:
            ticker: Market conditionId

        Returns:
            Market object or None if not found
        """
        try:
            markets = self._gamma_request(
                "/markets",
                params={"condition_ids": ticker, "limit": 1},
            )

            if not markets:
                return None

            m = markets[0]

            # Try to extract event category from nested events
            event_category = ""
            events = m.get("events", [])
            if events:
                event_category = events[0].get("category", "") or ""

            return self._parse_market(m, event_category=event_category)

        except Exception as e:
            logger.error(f"Failed to get market {ticker}: {e}")
            return None

    def filter_active_markets(self, markets: List[Market]) -> List[Market]:
        """
        Filter for markets that have active pricing data.

        Args:
            markets: List of Market objects

        Returns:
            Subset of markets that have at least one bid or ask price
        """
        return [
            m for m in markets
            if any([
                m.yes_bid is not None,
                m.yes_ask is not None,
                m.no_bid is not None,
                m.no_ask is not None,
            ])
        ]

    # ------------------------------------------------------------------
    # Subscriptions (polling-based)
    # ------------------------------------------------------------------

    async def subscribe_market(self, ticker: str, callback: Callable) -> None:
        """
        Subscribe to market updates via polling.

        Args:
            ticker: Market conditionId
            callback: Async callback receiving Market updates
        """
        if ticker not in self._subscriptions:
            self._subscriptions[ticker] = []

        self._subscriptions[ticker].append(callback)

        # Spin up a polling task for this ticker
        task = asyncio.create_task(self._poll_market(ticker))
        self._poll_tasks.append(task)

        logger.info(f"Subscribed to market {ticker} (polling every {self._poll_interval}s)")

    async def _poll_market(self, ticker: str) -> None:
        """Poll the Gamma API for market updates and invoke callbacks."""
        while True:
            try:
                market = await self.get_market(ticker)
                if market and ticker in self._subscriptions:
                    for callback in self._subscriptions[ticker]:
                        try:
                            await callback(market)
                        except Exception as e:
                            logger.error(f"Callback error for {ticker}: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Polling error for {ticker}: {e}")

            await asyncio.sleep(self._poll_interval)

    # ------------------------------------------------------------------
    # Trading stubs (require CLOB client integration)
    # ------------------------------------------------------------------

    async def place_order(self, order: Order) -> Dict[str, Any]:
        """Place order on Polymarket (requires CLOB client – not yet implemented)."""
        raise NotImplementedError(
            "Polymarket order placement requires CLOB client integration"
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order on Polymarket (requires CLOB client – not yet implemented)."""
        raise NotImplementedError(
            "Polymarket order cancellation requires CLOB client integration"
        )

    async def get_balance(self) -> Dict[str, float]:
        """Get account balance (requires CLOB client – not yet implemented)."""
        raise NotImplementedError(
            "Polymarket balance retrieval requires CLOB client integration"
        )

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions (requires CLOB client – not yet implemented)."""
        raise NotImplementedError(
            "Polymarket position retrieval requires CLOB client integration"
        )
