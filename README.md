# Arbitrage Bot

A Python-based arbitrage bot for Kalshi and Polymarket prediction markets.

## Project Structure

```
arb/
├── src/
│   ├── connectors/          # Exchange connectors
│   │   ├── base.py         # Abstract base connector
│   │   ├── kalshi.py       # Kalshi connector
│   │   └── polymarket.py   # Polymarket connector
│   └── utils/              # Shared utilities
│       └── crypto.py       # Cryptographic utilities
├── backend/                 # Legacy code (to be removed)
├── example_usage.py        # Example usage script
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (not in git)
└── README.md              # This file
```

## Setup

### 1. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Kalshi credentials
KALSHI_API_KEY_ID=your_api_key_here
KALSHI_PRIVATE_KEY=your_private_key_or_path_to_pem_file

# Polymarket credentials
POLYMARKET_PRIVATE_KEY=0x_your_ethereum_private_key_here
```

**Security Note:** Never commit `.env` or private key files to git!

### 3. Kalshi Private Key Setup

For Kalshi, you can either:

**Option A:** Store the private key in `.env`:
```env
KALSHI_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nMIIE...your key here...\n-----END PRIVATE KEY-----"
```

**Option B:** Store in a file and reference it:
```python
kalshi = KalshiConnector(private_key_path="path/to/key.pem")
```

## Usage

### Basic Connector Usage

#### Kalshi Example

```python
import asyncio
from src.connectors import KalshiConnector

async def main():
    # Initialize connector
    kalshi = KalshiConnector(
        private_key_path="backend/kalshi/main.txt"
    )

    try:
        # Connect to WebSocket
        await kalshi.connect()

        # Get markets
        markets = await kalshi.get_markets(category="Sports")

        # Subscribe to updates
        async def callback(market):
            print(f"Update: {market.ticker} - {market.yes_bid}/{market.yes_ask}")

        await kalshi.subscribe_market(markets[0].ticker, callback)
        await asyncio.sleep(10)  # Receive updates for 10 seconds

    finally:
        await kalshi.disconnect()

asyncio.run(main())
```

#### Polymarket Example

```python
import asyncio
from src.connectors import PolymarketConnector

async def main():
    # Initialize connector
    polymarket = PolymarketConnector()

    try:
        # Connect
        await polymarket.connect()

        # Get markets
        markets = await polymarket.get_markets()

        # Get specific market
        market = await polymarket.get_market(markets[0].ticker)
        print(f"Market: {market.title}")
        print(f"YES: {market.yes_bid}/{market.yes_ask}")

    finally:
        await polymarket.disconnect()

asyncio.run(main())
```

### Running Examples

```bash
python example_usage.py
```

## Connector API Reference

### BaseConnector

All connectors inherit from `BaseConnector` and implement these methods:

- `connect()` - Establish connection to exchange
- `disconnect()` - Close connection
- `get_markets(category=None)` - Get available markets
- `get_market(ticker)` - Get specific market
- `subscribe_market(ticker, callback)` - Subscribe to live updates
- `place_order(order)` - Place an order
- `cancel_order(order_id)` - Cancel an order
- `get_balance()` - Get account balance
- `get_positions()` - Get current positions

### Market Object

```python
@dataclass
class Market:
    ticker: str              # Market identifier
    title: str              # Human-readable title
    yes_price: float        # Current YES price
    no_price: float         # Current NO price
    yes_bid: float          # Best YES bid
    yes_ask: float          # Best YES ask
    no_bid: float           # Best NO bid
    no_ask: float           # Best NO ask
    volume: float           # Trading volume
    liquidity: float        # Available liquidity
    metadata: dict          # Exchange-specific data
```

### Order Object

```python
@dataclass
class Order:
    ticker: str             # Market ticker
    side: OrderSide         # BUY or SELL
    quantity: int           # Order quantity
    price: float            # Limit price
    order_type: str         # "limit", "market", etc.
    metadata: dict          # Additional parameters
```

## Features

### Kalshi Connector
- ✅ WebSocket support with auto-reconnect
- ✅ RSA signature authentication
- ✅ Live market updates
- ✅ Order placement and cancellation
- ✅ Balance and position queries

### Polymarket Connector
- ✅ CLOB API integration
- ✅ Ethereum wallet signing
- ✅ Market polling (no native WebSocket)
- ✅ Order placement and cancellation
- ✅ Position queries

## Next Steps

1. **Implement arbitrage detection logic** - Compare prices across exchanges
2. **Add risk management** - Position limits, exposure tracking
3. **Add execution engine** - Automated order placement
4. **Add monitoring** - Logging, alerts, performance metrics
5. **Add database** - Store historical data and opportunities

## Development

### Running Tests

```bash
# TODO: Add pytest tests
pytest tests/
```

### Code Style

```bash
# Format code
black src/

# Lint code
pylint src/
```

## License

Private project - All rights reserved

## Support

For issues or questions, contact the development team.
