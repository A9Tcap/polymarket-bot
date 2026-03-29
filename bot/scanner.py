"""
Market Scanner — fetches and filters active Kalshi markets
Uses RSA-PSS signing as required by Kalshi API
"""

import logging
import aiohttp
import os
import time
import base64
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

    # Strip query parameters from path before signing
    path_to_sign = path.split('?')[0]
    message = timestamp + method.upper() + path_to_sign

    try:
        private_key_bytes = private_key_str.encode()

        # Handle PEM format
        if not private_key_bytes.strip().startswith(b'-----'):
            # Wrap bare base64 key in PEM headers
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

        # RSA-PSS signing
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
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_active_markets(self, min_liquidity: float = 100) -> List[Dict]:
        """Fetch all active Kalshi markets above minimum liquidity threshold."""
        session = await self._get_session()
        markets = []
        cursor = None

        try:
            while True:
                path = '/trade-api/v2/markets'
                params = {'status': 'open', 'limit': 200}
                if cursor:
                    params['cursor'] = cursor

                # Sign path without query params
                headers = get_auth_headers('GET', path)

                # Build full URL with params
                url = f"https://api.elections.kalshi.com{path}"

                async with session.get(url, params=params, headers=headers) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        log.error(f"API error: {resp.status} {text[:200]}")
                        break
                    import json
                    data = json.loads(text)

                batch = data.get('markets', [])
                if not batch:
                    break

                for market in batch:
                    parsed = self._parse_market(market)
                    if parsed and parsed['liquidity'] >= min_liquidity:
                        markets.append(parsed)

                cursor = data.get('cursor')
                if not cursor or len(markets) >= 500:
                    break

        except Exception as e:
            log.error(f"Error fetching markets: {e}", exc_info=True)

        log.info(f"Fetched {len(markets)} markets with liquidity >= ${min_liquidity}")
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
