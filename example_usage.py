"""Example usage of the Kalshi and Polymarket connectors."""

import asyncio
import logging
from dotenv import load_dotenv

from src.connectors import KalshiConnector, PolymarketConnector

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def example_kalshi():
    """Example of using Kalshi connector."""
    logger.info("=== Kalshi Connector Example ===")

    # Initialize connector (loads credentials from .env)
    kalshi = KalshiConnector(
        private_key_path="backend/kalshi/main.txt"  # or use KALSHI_PRIVATE_KEY env var
    )

    try:
        # Connect to WebSocket
        await kalshi.connect()

        # Get sports markets
        logger.info("Fetching sports markets...")
        markets = await kalshi.get_markets(category="Sports")
        logger.info(f"Found {len(markets)} sports markets")

        # Display first few markets
        for market in markets[:5]:
            logger.info(f"  {market.ticker}: {market.title}")
            logger.info(f"    YES bid: {market.yes_bid}, YES ask: {market.yes_ask}")
            logger.info(f"    NO bid: {market.no_bid}, NO ask: {market.no_ask}")

        # Subscribe to a market for live updates
        if markets:
            ticker = markets[0].ticker

            async def market_callback(market):
                logger.info(f"Update for {market.ticker}: "
                          f"YES {market.yes_bid}/{market.yes_ask}, "
                          f"NO {market.no_bid}/{market.no_ask}")

            logger.info(f"Subscribing to {ticker}...")
            await kalshi.subscribe_market(ticker, market_callback)

            # Keep running for a bit to receive updates
            await asyncio.sleep(10)

    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        # Cleanup
        await kalshi.disconnect()


async def example_polymarket():
    """Example of using Polymarket connector."""
    logger.info("=== Polymarket Connector Example ===")

    # Initialize connector (loads credentials from .env)
    polymarket = PolymarketConnector()

    try:
        # Connect
        await polymarket.connect()

        # Get markets
        logger.info("Fetching markets...")
        markets = await polymarket.get_markets()
        logger.info(f"Found {len(markets)} markets")

        # Display first few markets
        for market in markets[:5]:
            logger.info(f"  {market.ticker}: {market.title}")
            if market.yes_bid or market.yes_ask:
                logger.info(f"    YES bid: {market.yes_bid}, YES ask: {market.yes_ask}")
            if market.no_bid or market.no_ask:
                logger.info(f"    NO bid: {market.no_bid}, NO ask: {market.no_ask}")

        # Get specific market
        if markets:
            ticker = markets[0].ticker
            logger.info(f"Fetching market {ticker}...")
            market = await polymarket.get_market(ticker)
            if market:
                logger.info(f"Got market: {market.title}")

    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        # Cleanup
        await polymarket.disconnect()


async def example_compare_markets():
    """Example of comparing markets across exchanges."""
    logger.info("=== Comparing Markets Across Exchanges ===")

    kalshi = KalshiConnector(private_key_path="backend/kalshi/main.txt")
    polymarket = PolymarketConnector()

    try:
        # Connect both
        await asyncio.gather(
            kalshi.connect(),
            polymarket.connect()
        )

        # Get markets from both
        kalshi_markets, poly_markets = await asyncio.gather(
            kalshi.get_markets(category="Sports"),
            polymarket.get_markets()
        )

        logger.info(f"Kalshi: {len(kalshi_markets)} markets")
        logger.info(f"Polymarket: {len(poly_markets)} markets")

        # Find potential arbitrage opportunities (simple example)
        # In reality, you'd need to match markets by event and normalize prices
        for k_market in kalshi_markets[:10]:
            # Simple check: if YES ask on one exchange < NO ask on another
            if k_market.yes_ask and k_market.no_ask:
                spread = 1.0 - (k_market.yes_ask + k_market.no_ask)
                if abs(spread) > 0.05:  # 5% spread
                    logger.info(f"Potential opportunity on {k_market.ticker}: "
                              f"spread = {spread:.2%}")

    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        # Cleanup
        await asyncio.gather(
            kalshi.disconnect(),
            polymarket.disconnect()
        )


async def main():
    """Main function to run examples."""
    load_dotenv()  # Load environment variables

    # Choose which example to run
    choice = input(
        "Choose example:\n"
        "1. Kalshi only\n"
        "2. Polymarket only\n"
        "3. Compare both\n"
        "Choice (1-3): "
    ).strip()

    if choice == "1":
        await example_kalshi()
    elif choice == "2":
        await example_polymarket()
    elif choice == "3":
        await example_compare_markets()
    else:
        logger.error("Invalid choice")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
