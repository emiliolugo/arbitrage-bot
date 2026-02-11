"""Minimal Kalshi WS client that only connects and prints available moneylines."""

import asyncio
import os
import time
import json
from dotenv import load_dotenv
from config import load_private_key_from_file, sign_pss_text
import websockets
from typing import Optional
import requests

load_dotenv()

WS_URL = 'wss://api.elections.kalshi.com/trade-api/ws/v2'
PATH_WITHOUT_QUERY = '/trade-api/ws/v2'
METHOD = 'GET'


class KalshiWSClient:
    """Connect-only client that prints available moneyline markets and exits."""

    def __init__(self,
                 api_key_env: str = 'KALSHI_API_KEY_ID',
                 private_key_path: str = 'backend/kalshi/main.txt',
                 ws_url: str = WS_URL):
        self.api_key = os.getenv(api_key_env)
        self.private_key_path = private_key_path
        self.private_key = None
        self.ws_url = ws_url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._closed = False

        if not self.api_key:
            raise RuntimeError('KALSHI_API_KEY_ID environment variable not set')

        # keep auth loading as in original
        self.private_key = load_private_key_from_file(self.private_key_path)

    def _build_auth_headers(self) -> dict:
        """Build signed headers fresh per-connection (timestamp changes)."""
        current_time_milliseconds = int(time.time() * 1000)
        timestamp_str = str(current_time_milliseconds)
        msg_string = timestamp_str + METHOD + PATH_WITHOUT_QUERY
        signature = sign_pss_text(self.private_key, msg_string)

        headers = {
            'KALSHI-ACCESS-KEY': self.api_key,
            'KALSHI-ACCESS-SIGNATURE': signature,
            'KALSHI-ACCESS-TIMESTAMP': timestamp_str,
        }
        return headers

    def _fetch_and_print_moneylines(self):
        """Fetch markets and print those that look like moneylines."""
        try:
            resp = requests.get("https://api.elections.kalshi.com/trade-api/v2/markets",
                                params={"category": "Sports"})
            resp.raise_for_status()
        except Exception as e:
            print(f"Failed to fetch markets: {e}")
            return

        try:
            markets = resp.json().get("markets", [])
            print(markets)
        except Exception:
            print("Unexpected markets response format")
            return

        moneylines = []
        for m in markets:
            title = m.get("title", "") or ""
            if 'moneyline' in title.lower() or m.get("market_type", "").lower() == "moneyline" or m.get("type", "").lower() == "moneyline":
                moneylines.append((m.get("ticker"), title))

        if not moneylines:
            print("No moneyline markets found.")
            return

        print("Available moneylines:")
        for ticker, title in moneylines:
            print(f"- {ticker}: {title}")

    async def _connect_once(self):
        headers = self._build_auth_headers()
        # connect just to satisfy the "connect to ws" requirement; we don't subscribe or consume messages
        async with websockets.connect(self.ws_url, additional_headers=headers) as websocket:
            print("Connected to Kalshi WebSocket")
            self.ws = websocket
            # After connecting, fetch and print moneylines (from REST API)
            # This keeps the connection open briefly while we perform the REST call.
            self._fetch_and_print_moneylines()
            # close after printing
            print("Done — closing connection.")

    async def connect_loop(self, max_retries: int = 0):
        """Keep attempting to connect. max_retries=0 means infinite."""
        attempt = 0
        backoff_seconds = 1
        while not self._closed and (max_retries == 0 or attempt < max_retries):
            try:
                attempt += 1
                await self._connect_once()
            except Exception as e:
                print(f"Connection failed (attempt {attempt}): {e}")
                await asyncio.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 30)
                continue
            else:
                # successful connect and finished job -> exit loop
                break

    def run(self):
        """Blocking run entrypoint."""
        try:
            asyncio.run(self.connect_loop())
        except KeyboardInterrupt:
            print('Interrupted, closing')
            self._closed = True


if __name__ == '__main__':
    try:
        client = KalshiWSClient()
    except Exception as exc:
        print(f"Could not initialize client: {exc}")
    else:
        client.run()
