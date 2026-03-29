"""
Market Scanner — fetches and filters active Kalshi markets
Public markets endpoint requires no authentication
"""

import logging
import aiohttp
import os
import time
import base64
import json
import asyncio
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from typing import List, Dict

log = logging.getLogger('scanner')

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"


def get_auth_headers(method: str, path: str) -> Dict:
    """Generate RSA-PSS authentication headers for Kalshi API."""
    api_key = os.getenv('KALSHI_API_KEY')
    private_key_str = os.getenv('KALSHI_PRIVATE_KEY', '')

    timestamp = str(int(time.time() * 1000))
    path_to_sign = path.split('?')[0]
    message = timestamp + method.upper() + path_to_sign

    try:
        private_key_bytes = private_key_str.encode()
        if not private_key_bytes.strip().startswith(b'-----'):
            private_key_bytes = (
                b'-----BEGIN RSA PRIVATE KEY-----\n' +
                private_key_str.encode() +
                b'\n-----END RSA PRIVATE KEY-----'
            )

        private_key = serialization.load_pem_private_key(
            private_key_bytes,
            password=None,
            backend=default_backend()
        )

        signature = private_key.sign(
            message.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=hashes.SHA256.digest_size
            ),
            hashes.SHA256()
        )
        sig_b64 = base64.b64encode(signature).decode()

        return {
            'KALSHI-ACCESS-KEY': api_key,
            'KALSHI-ACCESS-SIGNATURE': sig_b64,
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
        }
    except Exception as e:
        log.error(f"Auth header generation failed: {e}")
        return {'Content-Type': 'application/json'}


class MarketScanner:
    def __init__(self):
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers={
                'Content-Type': 'application/json',
                'User-Agent': 'polymarket-bot/1.0',
            })
        return self.session

    async def get_active_markets(self, min_liquidity: float = 100) -> List[Dict]:
        """Fetch all active Kalshi markets — public endpoint, no auth needed."""
        session = await self._get_session()
        markets = []
        cursor = None

        try:
            while True:
                params = {'status': 'open', 'limit': 100}
                if cursor:
                    params['cursor'] = cursor

                url = f"{KALSHI_API}/markets"

                async with session.get(url, params=params) as resp:
                    text = await resp.text()
                    if resp.status == 429:
                        log.warning("Rate limited — waiting 30s before retry")
                        await asyncio.sleep(30)
                        continue
                    if resp.status != 200:
                        log.error(f"API error: {resp.status} {text[:300]}")
                        break
                    data = json.loads(text)

                batch = data.get('markets', [])
                log.info(f"Got batch of {len(batch)} markets")
                if not batch:
                    break

                for market in batch:
                    parsed = self._parse_market(market)
                    if parsed:
                        markets.append(parsed)

                cursor = data.get('cursor')
                if not cursor or len(markets) >= 300:
                    break

        except Exception as e:
            log.error(f"Error fetching markets: {e}", exc_info=True)

        log.info(f"Fetched {len(markets)} total markets")
        return markets

    def _parse_market(self, raw: Dict) -> Dict:
        """Parse raw Kalshi market data into standardized format."""
        try:
            yes_bid = raw.get('yes_bid', 0) or 0
            yes_ask = raw.get('yes_ask', 0) or 0

            yes_price = (yes_bid + yes_ask) / 2 / 100 if (yes_bid + yes_ask) > 0 else 0.5
            no_price = 1 - yes_price

            return {
                'id': raw.get('ticker'),
                'ticker': raw.get('ticker'),
                'question': raw.get('title', ''),
                'description': raw.get('rules_primary', ''),
                'category': raw.get('category', ''),
                'yes_price': yes_price,
                'no_price': no_price,
                'yes_bid': yes_bid / 100,
                'yes_ask': yes_ask / 100,
                'liquidity': float(raw.get('liquidity', 0) or 0),
                'volume': float(raw.get('volume', 0) or 0),
                'end_date': raw.get('close_time'),
                'status': raw.get('status'),
            }
        except Exception as e:
            log.warning(f"Failed to parse market: {e}")
            return None

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
