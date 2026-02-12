# Arbitrage Bot

A Python-based arbitrage bot for Kalshi and Polymarket prediction markets.

## Project Structure

```
arb/
├── AGENT_GUIDE.md          # Guide and conventions for AI agents
├── src/
│   ├── connectors/          # Exchange connectors
│   │   ├── base.py         # Abstract base connector
│   │   ├── kalshi.py       # Kalshi connector
│   │   └── polymarket.py   # Polymarket connector (Gamma API, polling)
│   ├── core/               # Core arbitrage / matching logic
│   ├── models/             # Domain models (if/when added)
│   └── utils/              # Shared utilities
│       └── crypto.py       # Cryptographic utilities
├── config/                 # Configuration files
│   ├── settings.py        # Application settings
│   └── logging_config.py  # Logging configuration
├── data/                   # Local data storage (created at runtime)
├── keys/                   # Private keys (not in git)
│   └── kalshi_private_key.pem
├── test_connectors.py      # Connector integration tests
├── requirements.txt        # Python dependencies
├── pytest.ini              # Pytest configuration
├── .env                    # Environment variables (not in git)
├── .gitignore             # Git ignore rules
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

# Polymarket credentials (for future CLOB/trading integration)
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
kalshi = KalshiConnector(private_key_path="keys/kalshi_private_key.pem")
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
        private_key_path="keys/kalshi_private_key.pem"
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

#### Polymarket Example (Gamma API, polling)

```python
import asyncio
from src.connectors import PolymarketConnector

async def main():
    # Initialize connector
    polymarket = PolymarketConnector()

    try:
        # Connect
        await polymarket.connect()

        # Get binary sports markets (default category="Sports")
        markets = await polymarket.get_markets()

        # Get specific market
        market = await polymarket.get_market(markets[0].ticker)
        print(f"Market: {market.title}")
        print(f"YES: {market.yes_bid}/{market.yes_ask}")

    finally:
        await polymarket.disconnect()

asyncio.run(main())
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
- ✅ Gamma API integration for Polymarket binary markets
- ✅ Market polling via HTTP (no native WebSocket)
- ✅ Binary YES/NO market filtering (2 outcomes only)
- ⚠️ Trading (orders, balances, positions) **not yet implemented** –
    methods intentionally raise `NotImplementedError` until a CLOB client is wired in.

## Next Steps

1. **Implement arbitrage detection logic** - Compare prices across exchanges
2. **Add risk management** - Position limits, exposure tracking
3. **Add execution engine** - Automated order placement
4. **Add monitoring** - Logging, alerts, performance metrics
5. **Add database** - Store historical data and opportunities

## Development

### Running Tests

```bash
# Run full connector integration test suite
pytest test_connectors.py -v
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
