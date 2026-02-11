"""Simple test script to verify connectors are working."""

import asyncio
from config.logging_config import setup_logging
from config.settings import KALSHI_PRIVATE_KEY_PATH
from src.connectors import KalshiConnector, PolymarketConnector

# Setup logging
setup_logging(level="INFO")


async def test_kalshi():
    """Test Kalshi connector."""
    print("\n" + "="*60)
    print("Testing Kalshi Connector")
    print("="*60)

    try:
        kalshi = KalshiConnector(private_key_path=KALSHI_PRIVATE_KEY_PATH)
        print("✓ Kalshi connector initialized")

        await kalshi.connect()
        print("✓ Connected to Kalshi")

        markets = await kalshi.get_markets(category="Sports")
        print(f"✓ Fetched {len(markets)} sports markets")

        if markets:
            print(f"\nFirst 3 markets:")
            for market in markets[:3]:
                print(f"  - {market.ticker}: {market.title}")
                print(f"    YES: {market.yes_bid}/{market.yes_ask}")

        await kalshi.disconnect()
        print("✓ Disconnected from Kalshi")

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


async def test_polymarket():
    """Test Polymarket connector."""
    print("\n" + "="*60)
    print("Testing Polymarket Connector")
    print("="*60)

    try:
        poly = PolymarketConnector()
        print("✓ Polymarket connector initialized")

        await poly.connect()
        print("✓ Connected to Polymarket")

        markets = await poly.get_markets()
        print(f"✓ Fetched {len(markets)} markets")

        if markets:
            print(f"\nFirst 3 markets:")
            for market in markets[:3]:
                print(f"  - {market.ticker}: {market.title[:60]}...")

        await poly.disconnect()
        print("✓ Disconnected from Polymarket")

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


async def main():
    """Run connector tests."""
    print("\n" + "="*60)
    print("Connector Test Suite")
    print("="*60)

    results = []

    # Test Kalshi
    kalshi_ok = await test_kalshi()
    results.append(("Kalshi", kalshi_ok))

    # Test Polymarket
    poly_ok = await test_polymarket()
    results.append(("Polymarket", poly_ok))

    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    for name, ok in results:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"{name}: {status}")

    all_pass = all(ok for _, ok in results)
    print("\n" + ("All tests passed!" if all_pass else "Some tests failed!"))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
