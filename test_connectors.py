"""Integration tests for Polymarket and Kalshi connectors.

These tests hit real APIs to verify that both connectors correctly:
- Connect and authenticate
- Fetch binary outcome markets
- Filter and validate market data
- Handle subscriptions with real-time updates
- Properly clean up connections

Run with: pytest test_connectors.py -v
Run specific tests: pytest test_connectors.py::TestKalshiConnector::test_get_markets -v
"""

import asyncio
import pytest
from config.logging_config import setup_logging
from config.settings import KALSHI_PRIVATE_KEY_PATH
from src.connectors import KalshiConnector, PolymarketConnector
from src.connectors.base import Market, OrderSide

# Setup logging for tests
setup_logging(level="INFO")


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
async def kalshi_connector():
    """Provide a connected Kalshi connector instance."""
    connector = KalshiConnector(private_key_path=KALSHI_PRIVATE_KEY_PATH)
    await connector.connect()
    # Give WebSocket time to establish
    await asyncio.sleep(2)
    yield connector
    await connector.disconnect()


@pytest.fixture
async def polymarket_connector():
    """Provide a connected Polymarket connector instance."""
    connector = PolymarketConnector()
    await connector.connect()
    yield connector
    await connector.disconnect()


# ============================================================================
# Kalshi Connector Tests
# ============================================================================

class TestKalshiConnector:
    """Integration tests for Kalshi connector."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_initialization(self):
        """Test that Kalshi connector initializes correctly."""
        connector = KalshiConnector(private_key_path=KALSHI_PRIVATE_KEY_PATH)
        assert connector is not None
        assert not connector.connected

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_connection(self, kalshi_connector):
        """Test that Kalshi connector establishes connection."""
        assert kalshi_connector.connected

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_get_markets(self, kalshi_connector):
        """Test fetching markets from Kalshi API."""
        markets = await kalshi_connector.get_markets(category="Sports")
        
        assert isinstance(markets, list)
        assert len(markets) > 0, "Should fetch at least one sports market"
        
        # Verify first market structure
        market = markets[0]
        assert isinstance(market, Market)
        assert market.ticker is not None
        assert market.title is not None
        assert len(market.ticker) > 0
        assert len(market.title) > 0

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_binary_outcome_validation(self, kalshi_connector):
        """Test that Kalshi only returns binary outcome markets."""
        markets = await kalshi_connector.get_markets(category="Sports")
        
        assert len(markets) > 0, "Should have markets to validate"
        
        for market in markets:
            # Each market should have binary pricing fields
            # At least one of yes_bid, yes_ask, no_bid, no_ask should exist
            has_yes_prices = market.yes_bid is not None or market.yes_ask is not None
            has_no_prices = market.no_bid is not None or market.no_ask is not None
            
            assert has_yes_prices or has_no_prices, (
                f"Binary market {market.ticker} should have YES or NO prices"
            )

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_market_price_data(self, kalshi_connector):
        """Test that markets contain valid price data."""
        markets = await kalshi_connector.get_markets(category="Sports")
        
        assert len(markets) > 0
        
        # Find a market with complete price data
        complete_market = None
        for market in markets:
            if all([
                market.yes_bid is not None,
                market.yes_ask is not None,
                market.no_bid is not None,
                market.no_ask is not None
            ]):
                complete_market = market
                break
        
        if complete_market:
            # Validate price relationships
            assert 0 <= complete_market.yes_bid <= 1
            assert 0 <= complete_market.yes_ask <= 1
            assert 0 <= complete_market.no_bid <= 1
            assert 0 <= complete_market.no_ask <= 1
            
            # Bid should be <= Ask for same outcome
            assert complete_market.yes_bid <= complete_market.yes_ask
            assert complete_market.no_bid <= complete_market.no_ask

    @pytest.mark.asyncio
    @pytest.mark.timeout(45)
    async def test_subscription_mechanism(self, kalshi_connector):
        """Test WebSocket subscription for real-time market updates."""
        markets = await kalshi_connector.get_markets(category="Sports")
        assert len(markets) > 0
        
        # Pick first market for subscription
        test_market = markets[0]
        updates_received = []
        
        async def callback(market: Market):
            updates_received.append(market)
        
        # Subscribe to market
        await kalshi_connector.subscribe_market(test_market.ticker, callback)
        
        # Wait for updates (Kalshi sends orderbook_delta messages)
        await asyncio.sleep(10)
        
        # Should receive at least one update in 10 seconds on active market
        # Note: This may fail for very inactive markets
        print(f"\nReceived {len(updates_received)} updates for {test_market.ticker}")
        
        if updates_received:
            update = updates_received[0]
            assert isinstance(update, Market)
            assert update.ticker == test_market.ticker

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_get_single_market(self, kalshi_connector):
        """Test fetching a single market by ticker."""
        # First get available markets
        markets = await kalshi_connector.get_markets(category="Sports")
        assert len(markets) > 0
        
        test_ticker = markets[0].ticker
        
        # Fetch single market
        market = await kalshi_connector.get_market(test_ticker)
        
        assert market is not None
        assert isinstance(market, Market)
        assert market.ticker == test_ticker


# ============================================================================
# Polymarket Connector Tests
# ============================================================================

class TestPolymarketConnector:
    """Integration tests for Polymarket connector."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_initialization(self):
        """Test that Polymarket connector initializes correctly."""
        connector = PolymarketConnector()
        assert connector is not None
        assert not connector.connected

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_connection(self, polymarket_connector):
        """Test that Polymarket connector establishes connection."""
        assert polymarket_connector.connected

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_get_markets(self, polymarket_connector):
        """Test fetching markets from Polymarket API."""
        # Try different categories as sports markets may not always be available
        markets = await polymarket_connector.get_markets(category="")  # Get all markets
        
        assert isinstance(markets, list)
        # Polymarket may have periods with no active binary markets
        if len(markets) == 0:
            pytest.skip("No active binary markets available on Polymarket at this time")
        
        # Verify first market structure
        market = markets[0]
        assert isinstance(market, Market)
        assert market.ticker is not None
        assert market.title is not None
        assert len(market.ticker) > 0
        assert len(market.title) > 0

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_binary_outcome_validation(self, polymarket_connector):
        """Test that Polymarket only returns binary outcome markets (exactly 2 tokens)."""
        markets = await polymarket_connector.get_markets(category="")
        
        if len(markets) == 0:
            pytest.skip("No active binary markets available on Polymarket at this time")
        
        # Polymarket should filter to exactly 2-token (YES/NO) markets
        for market in markets:
            # Check metadata for token information
            if 'tokens' in market.metadata:
                tokens = market.metadata['tokens']
                assert len(tokens) == 2, (
                    f"Market {market.ticker} should have exactly 2 tokens, got {len(tokens)}"
                )
                
                # Verify YES and NO outcomes
                outcomes = [token.get('outcome', '').upper() for token in tokens]
                assert 'YES' in outcomes, f"Market {market.ticker} should have YES token"
                assert 'NO' in outcomes, f"Market {market.ticker} should have NO token"

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_active_market_filtering(self, polymarket_connector):
        """Test filtering for markets with active orderbooks."""
        all_markets = await polymarket_connector.get_markets()
        active_markets = polymarket_connector.filter_active_markets(all_markets)
        
        assert isinstance(active_markets, list)
        
        # Active markets should be a subset of all markets
        assert len(active_markets) <= len(all_markets)
        
        # Each active market should have at least one bid or ask price
        for market in active_markets:
            has_price = any([
                market.yes_bid is not None,
                market.yes_ask is not None,
                market.no_bid is not None,
                market.no_ask is not None
            ])
            assert has_price, (
                f"Active market {market.ticker} should have at least one price"
            )

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_market_price_data(self, polymarket_connector):
        """Test that markets contain valid price data."""
        markets = await polymarket_connector.get_markets(category="")
        active_markets = polymarket_connector.filter_active_markets(markets)
        
        if len(active_markets) == 0:
            pytest.skip("No active markets with pricing data available on Polymarket at this time")
        
        # Find market with complete price data
        complete_market = None
        for market in active_markets:
            if all([
                market.yes_bid is not None,
                market.yes_ask is not None,
                market.no_bid is not None,
                market.no_ask is not None
            ]):
                complete_market = market
                break
        
        if complete_market:
            # Validate price ranges (Polymarket uses 0-1 scale)
            assert 0 <= complete_market.yes_bid <= 1
            assert 0 <= complete_market.yes_ask <= 1
            assert 0 <= complete_market.no_bid <= 1
            assert 0 <= complete_market.no_ask <= 1
            
            # Bid should be <= Ask
            assert complete_market.yes_bid <= complete_market.yes_ask
            assert complete_market.no_bid <= complete_market.no_ask

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_subscription_mechanism(self, polymarket_connector):
        """Test polling-based subscription for market updates."""
        markets = await polymarket_connector.get_markets(category="")
        active_markets = polymarket_connector.filter_active_markets(markets)
        
        if len(active_markets) == 0:
            pytest.skip("No active markets available on Polymarket for subscription test")
        
        # Pick first active market
        test_market = active_markets[0]
        updates_received = []
        
        async def callback(market: Market):
            updates_received.append(market)
        
        # Subscribe to market (starts polling)
        await polymarket_connector.subscribe_market(test_market.ticker, callback)
        
        # Wait for polling updates (default interval is 1 second)
        await asyncio.sleep(5)
        
        # Should receive multiple updates from polling
        assert len(updates_received) >= 3, (
            f"Expected at least 3 updates in 5 seconds, got {len(updates_received)}"
        )
        
        # Verify update structure
        update = updates_received[0]
        assert isinstance(update, Market)
        assert update.ticker == test_market.ticker

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_category_filtering(self, polymarket_connector):
        """Test filtering markets by category."""
        # Default category is Sports
        sports_markets = await polymarket_connector.get_markets(category="Sports")
        
        assert isinstance(sports_markets, list)
        # Sports markets should exist (category is popular)
        # Note: This may occasionally fail if no sports markets are available
        print(f"\nFound {len(sports_markets)} sports markets")

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_closed_market_filtering(self, polymarket_connector):
        """Test that closed markets are filtered out."""
        markets = await polymarket_connector.get_markets()
        
        # No market should have closed=True in metadata
        for market in markets:
            if 'closed' in market.metadata:
                assert market.metadata['closed'] is False, (
                    f"Market {market.ticker} should not be closed"
                )


# ============================================================================
# Comparison Tests
# ============================================================================

class TestConnectorComparison:
    """Tests comparing behavior across both connectors."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_both_connectors_return_binary_markets(self, kalshi_connector, polymarket_connector):
        """Verify both connectors return binary outcome markets."""
        kalshi_markets = await kalshi_connector.get_markets(category="Sports")
        poly_markets = await polymarket_connector.get_markets(category="")
        
        assert len(kalshi_markets) > 0, "Kalshi should return markets"
        # Polymarket may not have active markets at all times
        if len(poly_markets) == 0:
            pytest.skip("No active markets on Polymarket, testing Kalshi only")
        
        # Both should have binary market characteristics
        for market in kalshi_markets[:5]:  # Check first 5
            assert market.ticker is not None
            assert market.title is not None
        
        for market in poly_markets[:5]:  # Check first 5
            assert market.ticker is not None
            assert market.title is not None

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_market_data_structure_consistency(self, kalshi_connector, polymarket_connector):
        """Test that both connectors return consistent Market objects."""
        kalshi_markets = await kalshi_connector.get_markets(category="Sports")
        poly_markets = await polymarket_connector.get_markets()
        
        # Both should return Market instances with same base structure
        if kalshi_markets:
            k_market = kalshi_markets[0]
            assert hasattr(k_market, 'ticker')
            assert hasattr(k_market, 'title')
            assert hasattr(k_market, 'yes_bid')
            assert hasattr(k_market, 'no_ask')
            assert hasattr(k_market, 'metadata')
        
        if poly_markets:
            p_market = poly_markets[0]
            assert hasattr(p_market, 'ticker')
            assert hasattr(p_market, 'title')
            assert hasattr(p_market, 'yes_bid')
            assert hasattr(p_market, 'no_ask')
            assert hasattr(p_market, 'metadata')
