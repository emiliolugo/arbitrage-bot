"""Unit tests for market matching logic in src.core.market_matcher.

These tests define the expected external behavior for the future
implementation of `find_matches` based on the provided matching spec:

- Markets are binary sports head-to-head (Team A vs Team B).
- Matching is deterministic via a canonical key built from event time
  and canonicalized team names.
- Team aliases are resolved to canonical names (e.g. "LA Lakers" →
  "Los Angeles Lakers").
- Team order differences across platforms do not block a match.
- Different event times must not be matched.
- When the propositions are inverted (home team win vs away team win
  for the same game), matches are still returned but flagged as
  inverted.

The tests assume the following interface for src.core.market_matcher:

    from src.core.market_matcher import find_matches

    matches, unmatched_kalshi = find_matches(kalshi_markets, polymarket_markets)

Where:
- `kalshi_markets` / `polymarket_markets` are lists of Market objects
  (from src.connectors.base.Market).
- `matches` is a list of objects (dicts or lightweight models) with at
  least the keys/attributes:
    - `kalshi`: the Kalshi Market instance
    - `polymarket`: the Polymarket Market instance
    - `inverted`: bool indicating if propositions are inverted
- `unmatched_kalshi` is a list of Kalshi Market instances that could
  not be matched to any Polymarket market.

The implementation in market_matcher.py should be adapted to satisfy
this contract.
"""

from src.connectors.base import Market
from src.core.market_matcher import find_matches


def _make_market(
    *,
    exchange: str,
    ticker: str,
    title: str,
    start_time: str,
    extra_metadata: dict | None = None,
) -> Market:
    """Helper to construct a Market with minimal metadata for matching.

    `start_time` should be an ISO 8601 string (UTC preferred), which
    matching logic can normalize into the event key.
    """
    metadata = {
        "exchange": exchange,
        "start_time": start_time,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    return Market(
        ticker=ticker,
        title=title,
        metadata=metadata,
    )


def _unpack_match(match):
    """Normalize access to match object.

    Allows the implementation to use either a dict-like or an object
    with attributes `kalshi`, `polymarket`, and `inverted`.
    """
    if isinstance(match, dict):
        return match["kalshi"], match["polymarket"], match["inverted"]

    # Fallback to attribute access
    return match.kalshi, match.polymarket, match.inverted


def test_direct_match_same_order_and_time():
    """Markets with identical teams, order, and time should match directly."""
    kalshi_market = _make_market(
        exchange="kalshi",
        ticker="KAL-LAL-BOS-2025-01-01",
        title="Los Angeles Lakers vs Boston Celtics",
        start_time="2025-01-01T20:00:00Z",
    )

    polymarket_market = _make_market(
        exchange="polymarket",
        ticker="POLY-LAL-BOS-2025-01-01",
        title="Los Angeles Lakers vs Boston Celtics",
        start_time="2025-01-01T20:00:00Z",
    )

    matches, unmatched = find_matches([kalshi_market], [polymarket_market])

    assert len(matches) == 1
    assert len(unmatched) == 0

    k, p, inverted = _unpack_match(matches[0])

    assert k is kalshi_market
    assert p is polymarket_market
    assert inverted is False


def test_match_with_reversed_team_order():
    """Titles with reversed team order should still match the same event."""
    kalshi_market = _make_market(
        exchange="kalshi",
        ticker="KAL-LAL-BOS-2025-01-01",
        title="Los Angeles Lakers vs Boston Celtics",
        start_time="2025-01-01T20:00:00Z",
    )

    # Polymarket expresses the same game as an away/home framing.
    polymarket_market = _make_market(
        exchange="polymarket",
        ticker="POLY-LAL-BOS-2025-01-01",
        title="Boston Celtics @ Los Angeles Lakers",
        start_time="2025-01-01T20:00:00Z",
    )

    matches, unmatched = find_matches([kalshi_market], [polymarket_market])

    assert len(matches) == 1
    assert len(unmatched) == 0

    k, p, inverted = _unpack_match(matches[0])

    assert k is kalshi_market
    assert p is polymarket_market
    assert inverted is False


def test_match_uses_team_aliases():
    """Aliases like 'LA Lakers' and 'BOS Celtics' should map to canonical names."""
    kalshi_market = _make_market(
        exchange="kalshi",
        ticker="KAL-LAL-BOS-2025-01-01",
        title="LA Lakers vs BOS Celtics",
        start_time="2025-01-01T20:00:00Z",
    )

    polymarket_market = _make_market(
        exchange="polymarket",
        ticker="POLY-LAL-BOS-2025-01-01",
        title="Los Angeles Lakers vs Boston Celtics",
        start_time="2025-01-01T20:00:00Z",
    )

    matches, unmatched = find_matches([kalshi_market], [polymarket_market])

    assert len(matches) == 1
    assert len(unmatched) == 0

    k, p, inverted = _unpack_match(matches[0])

    assert k is kalshi_market
    assert p is polymarket_market
    assert inverted is False


def test_different_start_times_do_not_match():
    """Same teams on different dates/times must not be matched."""
    kalshi_market = _make_market(
        exchange="kalshi",
        ticker="KAL-LAL-BOS-2025-01-01",
        title="Los Angeles Lakers vs Boston Celtics",
        start_time="2025-01-01T20:00:00Z",
    )

    # Same matchup but different tip-off time
    polymarket_market = _make_market(
        exchange="polymarket",
        ticker="POLY-LAL-BOS-2025-01-02",
        title="Los Angeles Lakers vs Boston Celtics",
        start_time="2025-01-02T20:00:00Z",
    )

    matches, unmatched = find_matches([kalshi_market], [polymarket_market])

    # No match because the normalized event key should include timestamp
    assert len(matches) == 0
    assert unmatched == [kalshi_market]


def test_inverted_proposition_is_flagged():
    """Same game but opposite win propositions should be marked as inverted.

    Example:
    - Kalshi: "Will Los Angeles Lakers beat Boston Celtics?" → YES = Lakers win
    - Polymarket: "Boston Celtics to win vs Los Angeles Lakers" → YES = Celtics win

    Matching logic should still pair these markets but set inverted=True
    so that downstream arbitrage logic can invert prices correctly.
    """
    kalshi_market = _make_market(
        exchange="kalshi",
        ticker="KAL-LAL-BOS-2025-01-01",
        title="Will Los Angeles Lakers beat Boston Celtics?",
        start_time="2025-01-01T20:00:00Z",
    )

    polymarket_market = _make_market(
        exchange="polymarket",
        ticker="POLY-LAL-BOS-2025-01-01",
        title="Boston Celtics to win vs Los Angeles Lakers",
        start_time="2025-01-01T20:00:00Z",
    )

    matches, unmatched = find_matches([kalshi_market], [polymarket_market])

    assert len(matches) == 1
    assert len(unmatched) == 0

    k, p, inverted = _unpack_match(matches[0])

    assert k is kalshi_market
    assert p is polymarket_market
    assert inverted is True
