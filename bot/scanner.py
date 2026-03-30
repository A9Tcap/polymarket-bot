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

log = logging.getLogger('scanner')

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"


def get_auth_headers(method, path):
    api_key = os.getenv('KALSHI_API_KEY')
    private_key_str = os.getenv('KALSHI_PRIVATE_KEY', '')
    timestamp = str(int(time.time() * 1000))
    path_to_sign = path.split('?')[0]
    message = timestamp + method.upper() + path_to_sign
    key_str = private_key_str.strip().replace('\\n', '\n')
    try:
        private_key = serialization.load_pem_private_key(key_str.encode(), password=None, backend=default_backend())
        sig = private_key.sign(message.encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256.digest_size), hashes.SHA256())
        return {
            'KALSHI-ACCESS-KEY': api_key,
            'KALSHI-ACCESS-SIGNATURE': base64.b64encode(sig).decode(),
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
        }
    except Exception as e:
        log.error(f"Auth header generation failed: {e}")
        return {'Content-Type': 'application/json'}


def is_combo_market(title):
    """Filter out combo/parlay markets that bundle multiple outcomes."""
    if not title:
        return False
    parts = [p.strip() for p in title.split(',')]
    yes_no_parts = [p for p in parts if p.lower().startswith('yes ') or p.lower().startswith('no ')]
    return len(yes_no_parts) > 2


class MarketScanner:
    def __init__(self):
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers={
                'Content-Type': 'application/json',
                'User-Agent': 'kalshi-bot/1.0',
            })
        return self.session

    async def get_active_markets(self, min_liquidity=100):
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
                        log.warning("Rate limited — waiting 30s")
                        await asyncio.sleep(30)
                        continue
                    if resp.status != 200:
                        log.error(f"API error: {resp.status} {text[:300]}")
                        break
                    data = json.loads(text)

                batch = data.get('markets', [])
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

        single_markets = [m for m in markets if not is_combo_market(m['question'])]
        log.info(f"Fetched {len(markets)} total markets, {len(single_markets)} single-outcome markets")
        return single_markets

    def _parse_market(self, raw):
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
