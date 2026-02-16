"""Market matcher for finding equivalent markets across exchanges."""

import re
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ============================================================================
# Team Alias Mapping - 3-letter common abbreviations for professional teams
# ============================================================================

TEAM_ALIASES = {
    # NBA
    "lal": "los angeles lakers",
    "lakers": "los angeles lakers",
    "la lakers": "los angeles lakers",
    "los angeles lakers": "los angeles lakers",

    "lac": "los angeles clippers",
    "clippers": "los angeles clippers",
    "la clippers": "los angeles clippers",
    "los angeles clippers": "los angeles clippers",

    "gsw": "golden state warriors",
    "warriors": "golden state warriors",
    "golden state warriors": "golden state warriors",

    "bos": "boston celtics",
    "celtics": "boston celtics",
    "boston celtics": "boston celtics",

    "mia": "miami heat",
    "heat": "miami heat",
    "miami heat": "miami heat",

    "dal": "dallas mavericks",
    "mavericks": "dallas mavericks",
    "dallas mavericks": "dallas mavericks",

    "phx": "phoenix suns",
    "suns": "phoenix suns",
    "phoenix suns": "phoenix suns",

    "den": "denver nuggets",
    "nuggets": "denver nuggets",
    "denver nuggets": "denver nuggets",

    "mil": "milwaukee bucks",
    "bucks": "milwaukee bucks",
    "milwaukee bucks": "milwaukee bucks",

    "phi": "philadelphia 76ers",
    "76ers": "philadelphia 76ers",
    "philadelphia 76ers": "philadelphia 76ers",
    "sixers": "philadelphia 76ers",

    # NFL
    "buf": "buffalo bills",
    "bills": "buffalo bills",
    "buffalo bills": "buffalo bills",

    "mia": "miami dolphins",
    "dolphins": "miami dolphins",
    "miami dolphins": "miami dolphins",

    "ne": "new england patriots",
    "nep": "new england patriots",
    "patriots": "new england patriots",
    "new england patriots": "new england patriots",

    "nyj": "new york jets",
    "jets": "new york jets",
    "new york jets": "new york jets",

    "bal": "baltimore ravens",
    "ravens": "baltimore ravens",
    "baltimore ravens": "baltimore ravens",

    "cin": "cincinnati bengals",
    "bengals": "cincinnati bengals",
    "cincinnati bengals": "cincinnati bengals",

    "cle": "cleveland browns",
    "browns": "cleveland browns",
    "cleveland browns": "cleveland browns",

    "pit": "pittsburgh steelers",
    "steelers": "pittsburgh steelers",
    "pittsburgh steelers": "pittsburgh steelers",

    "kc": "kansas city chiefs",
    "chiefs": "kansas city chiefs",
    "kansas city chiefs": "kansas city chiefs",

    "sf": "san francisco 49ers",
    "sfo": "san francisco 49ers",
    "49ers": "san francisco 49ers",
    "san francisco 49ers": "san francisco 49ers",

    # MLB
    "nyy": "new york yankees",
    "yankees": "new york yankees",
    "new york yankees": "new york yankees",

    "bos": "boston red sox",
    "red sox": "boston red sox",
    "boston red sox": "boston red sox",

    "lad": "los angeles dodgers",
    "dodgers": "los angeles dodgers",
    "los angeles dodgers": "los angeles dodgers",

    "chc": "chicago cubs",
    "cubs": "chicago cubs",
    "chicago cubs": "chicago cubs",

    # NHL
    "tor": "toronto maple leafs",
    "maple leafs": "toronto maple leafs",
    "toronto maple leafs": "toronto maple leafs",

    "mtl": "montreal canadiens",
    "canadiens": "montreal canadiens",
    "montreal canadiens": "montreal canadiens",

    "bos": "boston bruins",
    "bruins": "boston bruins",
    "boston bruins": "boston bruins",

    # College Basketball (examples)
    "duke": "duke blue devils",
    "duke blue devils": "duke blue devils",

    "unc": "north carolina tar heels",
    "north carolina": "north carolina tar heels",
    "tar heels": "north carolina tar heels",
    "north carolina tar heels": "north carolina tar heels",

    "uk": "kentucky wildcats",
    "kentucky": "kentucky wildcats",
    "wildcats": "kentucky wildcats",
    "kentucky wildcats": "kentucky wildcats",
}


# ============================================================================
# Date Normalization
# ============================================================================

def normalize_event_date(market) -> Optional[str]:
    """
    Extract and normalize event date from market metadata.

    Args:
        market: Market object with metadata

    Returns:
        ISO date string (YYYY-MM-DD) or None if date cannot be extracted
    """
    metadata = market.metadata or {}

    # Kalshi: use 'expected_expiration_time'
    if 'expected_expiration_time' in metadata:
        try:
            # Parse ISO timestamp and extract date
            timestamp = metadata['expected_expiration_time']
            # Handle both full ISO format and date-only format
            if 'T' in timestamp:
                date_str = timestamp.split('T')[0]
            else:
                date_str = timestamp
            # Validate format YYYY-MM-DD
            datetime.strptime(date_str, '%Y-%m-%d')
            return date_str
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse Kalshi date from {timestamp}: {e}")

    # Polymarket: extract from slug (e.g., 'cwbb-colst-stmry-2025-11-08')
    if 'slug' in metadata:
        slug = metadata['slug']
        # Extract date from last dash pattern: YYYY-MM-DD at the end
        match = re.search(r'(\d{4}-\d{2}-\d{2})$', slug)
        if match:
            date_str = match.group(1)
            try:
                # Validate format
                datetime.strptime(date_str, '%Y-%m-%d')
                return date_str
            except ValueError as e:
                logger.warning(f"Invalid date extracted from slug {slug}: {e}")

    logger.warning(f"Could not extract date from market: {market.title}")
    return None


# ============================================================================
# Title Parsing
# ============================================================================

def parse_binary_sports_title(title: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse a binary sports market title to extract team names.

    Handles patterns like:
    - "Lakers vs Celtics"
    - "Celtics @ Lakers"
    - "Will the Lakers beat the Celtics?"
    - "Los Angeles Lakers vs. Boston Celtics"
    - "LA Lakers v BOS Celtics"
    - "Lakers vs Celtics – Jan 5"
    - "NBA: Lakers vs Celtics"

    Args:
        title: Market title string

    Returns:
        Tuple of (team1, team2) or (None, None) if parsing fails
    """
    if not title:
        return None, None

    # Normalize: lowercase and clean up
    normalized = title.lower()

    # Remove common prefix patterns
    normalized = re.sub(r'^(will\s+the\s+|will\s+|does\s+|can\s+)', '', normalized)
    normalized = re.sub(r'^(nba|nfl|mlb|nhl|ncaa|ncaab|ncaaf):\s*', '', normalized)
    normalized = re.sub(r'\s+(game|match)\s+', ' ', normalized)

    # Remove trailing date patterns (e.g., "– Jan 5", "- January 5th")
    normalized = re.sub(r'\s*[–-]\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(st|nd|rd|th)?.*$', '', normalized)

    # Remove question words and punctuation
    normalized = re.sub(r'\s+(beat|defeat|win\s+against|vs\.?|versus|v\.?)\s+', '|', normalized)
    normalized = re.sub(r'\s+@\s+', '|', normalized)
    normalized = re.sub(r'[?!.]', '', normalized)

    # Split on the separator
    if '|' not in normalized:
        # Try to find vs/v/@/versus without normalization working
        # Fallback patterns
        vs_patterns = [
            r'\s+vs\.?\s+',
            r'\s+versus\s+',
            r'\s+v\.?\s+',
            r'\s+@\s+',
        ]
        for pattern in vs_patterns:
            if re.search(pattern, normalized):
                normalized = re.sub(pattern, '|', normalized)
                break

    if '|' not in normalized:
        logger.warning(f"Could not find team separator in title: {title}")
        return None, None

    # Split and clean
    parts = normalized.split('|', 1)
    if len(parts) != 2:
        logger.warning(f"Expected 2 teams but got {len(parts)} from title: {title}")
        return None, None

    team1_raw = parts[0].strip()
    team2_raw = parts[1].strip()

    # Remove trailing noise from team2 (dates, extra text)
    team2_raw = re.split(r'\s*[–-]\s*', team2_raw)[0].strip()

    # Normalize team names through alias map
    team1 = normalize_team_name(team1_raw)
    team2 = normalize_team_name(team2_raw)

    if not team1 or not team2:
        logger.warning(f"Failed to normalize teams from title: {title}")
        return None, None

    return team1, team2


def normalize_team_name(team_name: str) -> Optional[str]:
    """
    Normalize a team name using the alias map.

    Args:
        team_name: Raw team name string

    Returns:
        Canonical team name or None if not found
    """
    if not team_name:
        return None

    # Clean up the team name
    cleaned = team_name.lower().strip()

    # Remove articles
    cleaned = re.sub(r'^(the|a|an)\s+', '', cleaned)

    # Direct lookup
    if cleaned in TEAM_ALIASES:
        return TEAM_ALIASES[cleaned]

    # Try fuzzy matching: check if any alias is contained or contains
    for alias, canonical in TEAM_ALIASES.items():
        if alias in cleaned or cleaned in alias:
            return canonical

    # If not in map, return the cleaned version as-is
    # This allows matching of teams not yet in the alias map
    logger.debug(f"Team '{team_name}' not in alias map, using cleaned version: '{cleaned}'")
    return cleaned


# ============================================================================
# Market Key Generation
# ============================================================================

def build_market_key(market, alias_map: Optional[Dict[str, str]] = None) -> Optional[str]:
    """
    Build a deterministic market key for matching.

    Key format: {date}:{team_a}:{team_b}
    where teams are sorted alphabetically for platform-independence.

    Args:
        market: Market object
        alias_map: Optional custom alias map (uses TEAM_ALIASES if None)

    Returns:
        Market key string or None if key cannot be built
    """
    # Extract date
    date = normalize_event_date(market)
    if not date:
        return None

    # Parse teams from title
    team1, team2 = parse_binary_sports_title(market.title)
    if not team1 or not team2:
        return None

    # Sort teams alphabetically for consistency
    teams_sorted = sorted([team1, team2])

    # Build key
    key = f"{date}:{teams_sorted[0]}:{teams_sorted[1]}"
    return key


# ============================================================================
# Match Detection
# ============================================================================

@dataclass
class MarketMatch:
    """Represents a matched pair of markets."""
    kalshi_market: Any
    polymarket_market: Any
    match_key: str
    inverted: bool = False


def check_if_inverted(kalshi_market, polymarket_market) -> bool:
    """
    Check if two markets represent inverted propositions.

    For example:
    - Kalshi: "Will Lakers win?"
    - Polymarket: "Will Celtics win?"

    Args:
        kalshi_market: Market from Kalshi
        polymarket_market: Market from Polymarket

    Returns:
        True if propositions are inverted, False otherwise
    """
    # TODO: Implement inversion detection logic
    # For now, assume all matches are direct (not inverted)
    return False


def construct_match_object(
    kalshi: Any,
    polymarket: Any,
    match_key: str,
    inverted: bool = False
) -> MarketMatch:
    """
    Construct a match object from two markets.

    Args:
        kalshi: Kalshi Market object
        polymarket: Polymarket Market object
        match_key: The key used for matching
        inverted: Whether the propositions are inverted

    Returns:
        MarketMatch object
    """
    return MarketMatch(
        kalshi_market=kalshi,
        polymarket_market=polymarket,
        match_key=match_key,
        inverted=inverted
    )


# ============================================================================
# Main Matching Algorithm
# ============================================================================

def get_matches(kalshi_markets: List, polymarket_markets: List) -> Tuple[List[MarketMatch], List]:
    """
    Find matching markets between Kalshi and Polymarket.

    Uses O(n+m) algorithm:
    1. Index all Polymarket markets by their canonical key
    2. For each Kalshi market, check if its key exists in the index
    3. If match found, construct match object

    Args:
        kalshi_markets: List of Market objects from Kalshi
        polymarket_markets: List of Market objects from Polymarket

    Returns:
        Tuple of (matches, unmatched_kalshi):
        - matches: List of MarketMatch objects
        - unmatched_kalshi: List of Kalshi markets without matches
    """
    logger.info(f"Matching {len(kalshi_markets)} Kalshi markets against {len(polymarket_markets)} Polymarket markets")

    # Build Polymarket index
    polymarket_index: Dict[str, Any] = {}
    polymarket_skipped = 0

    for p_market in polymarket_markets:
        key = build_market_key(p_market)
        if key:
            if key in polymarket_index:
                logger.warning(f"Duplicate Polymarket key: {key}")
            polymarket_index[key] = p_market
        else:
            polymarket_skipped += 1

    logger.info(f"Indexed {len(polymarket_index)} Polymarket markets ({polymarket_skipped} skipped)")

    # Match Kalshi markets
    matches: List[MarketMatch] = []
    unmatched_kalshi: List = []
    kalshi_skipped = 0

    for k_market in kalshi_markets:
        key = build_market_key(k_market)
        if not key:
            kalshi_skipped += 1
            unmatched_kalshi.append(k_market)
            continue

        if key in polymarket_index:
            p_market = polymarket_index[key]

            # Check if propositions are inverted
            inverted = check_if_inverted(k_market, p_market)

            # Construct match object
            match = construct_match_object(
                kalshi=k_market,
                polymarket=p_market,
                match_key=key,
                inverted=inverted
            )
            matches.append(match)

            logger.debug(f"Match found: {key} (inverted={inverted})")
        else:
            unmatched_kalshi.append(k_market)

    logger.info(
        f"Matching complete: {len(matches)} matches, "
        f"{len(unmatched_kalshi)} unmatched Kalshi markets "
        f"({kalshi_skipped} skipped due to parsing errors)"
    )

    return matches, unmatched_kalshi


# ============================================================================
# Legacy Interface (for compatibility)
# ============================================================================

def find_matches(kalshi_markets: List, polymarket_markets: List) -> Tuple[List[MarketMatch], List]:
    """
    Legacy interface for finding matches.

    This is an alias for get_matches() to maintain compatibility
    with existing code that may call find_matches().
    """
    return get_matches(kalshi_markets, polymarket_markets)
