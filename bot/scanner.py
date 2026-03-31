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

# Sports-related keywords to filter out combo/prop markets
SPORTS_KEYWORDS = [
    ' at ', ' vs ', ' wins by', ' wins over', 'points', 'rebounds', 'assists',
    'touchdowns', 'yards', 'goals', 'saves', 'strikeouts', 'home runs',
    'rushing', 'receiving', 'passing', 'field goals', 'three-pointers',
    'steals', 'blocks', 'aces', 'double-double', 'triple-double'
]

# Keywords that indicate good economics/politics markets
GOOD_KEYWORDS = [
    'fed', 'federal reserve', 'fomc', 'rate', 'cpi', 'inflation', 'gdp',
    'unemployment', 'jobs', 'recession', 'bitcoin', 'crypto', 'trump',
    'congress', 'senate', 'house', 'election', 'tariff', 'iran', 'war',
    'stock', 'nasdaq', 's&p', 'dow', 'oil', 'gold', 'dollar', 'euro',
    'will the', 'will there', 'will us', 'will president', 'will bitcoin',
    'will fed', 'will inflation', 'will congress', 'will trump'
]


def is_good_market(title):
    """Return True if this looks like a clean economics/politics/crypto market."""
    if not title:
        return False
    title_lower = title.lower()
    
    # Filter out sports prop markets
    for kw in SPORTS_KEYWORDS:
        if kw in title_lower:
            return False
    
    # Prefer markets with macro/political keywords
    for kw in GOOD_KEYWORDS:
        if kw in title_lower:
            return True
    
    # Accept markets that don't have sports keywords even without good keywords
    return True


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
        all_markets = []
        cursor = None
        attempts = 0

        try:
            while attempts < 5:
                params = {'status': 'open', 'limit': 200}
                if cursor:
                    params['cursor'] = cursor

                url = f"{KALSHI_API}/markets"

                async with session.get(url, params=params) as resp:
                    if resp.status == 429:
                        log.warning("Rate limited — waiting 60s")
                        await asyncio.sleep(60)
                        attempts += 1
                        continue
                    if resp.status != 200:
                        text = await resp.text()
                        log.error(f"API error: {resp.status} {text[:200]}")
                        break
                    text = await resp.text()
                    data = json.loads(text)

                batch = data.get('markets', [])
                if not batch:
                    break

                for market in batch:
                    parsed = self._parse_market(market)
                    if parsed and parsed['liquidity'] >= min_liquidity:
                        if is_good_market(parsed['question']):
                            all_markets.append(parsed)

                cursor = data.get('cursor')
                if not cursor or len(all_markets) >= 200:
                    break


        except Exception as e:
            log.error(f"Error fetching markets: {e}", exc_info=True)

        log.info(f"Fetched {len(all_markets)} qualifying markets")
        return all_markets

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
