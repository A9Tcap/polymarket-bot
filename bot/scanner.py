"""
Market Scanner — fetches macro and sports game winner markets from Kalshi
Uses correct API field names from official Kalshi docs:
- yes_bid_dollars, yes_ask_dollars (prices in dollars 0-1)
- volume_fp (volume as floating point)
- liquidity_dollars (liquidity in dollars)
- close_time (resolution time)
- mve_filter=exclude (official param to exclude combo/parlay markets)
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

log = logging.getLogger('scanner')

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"

# Macro/economics/crypto series
MACRO_SERIES = [
    'KXBTC', 'KXETH', 'KXDOGE', 'KXSOL', 'KXXRP',
    'KXCPI', 'KXCPIYOY', 'KXCPICORE', 'KXCPICOREYOY',
    'KXEFFR', 'KXFED', 'KXRATECUT', 'KXDOTPLOT',
    'KXGDP', 'KXPAYROLLS', 'KXU3', 'KXJOBLESSCLAIMS',
    'KXINX', 'KXNASDAQ100', 'KXGOLDD', 'KXWTI',
    'KXTRUMP', 'KXTARIFFRATEPRC', 'KXTARIFFRATEEU',
    'KXNEWTARIFFS', 'KXEFFTARIFF', 'KXTRUMPFIRE', 'KXTRUMPRESIGN',
    'KXECONPATH', 'KXHIGHINFLATION', 'KXRECCOUNT',
    'KXMORTGAGERATE', 'KXEGGS', 'KXUSRETAIL',
]

# Sports game winner series only
SPORTS_SERIES = [
    'KXNBAGAME',
    'KXMLBGAME',
    'KXNHLGAME',
    'KXNFLGAME',
    'KXEPLGAME',
    'KXLALIGAGAME',
    'KXSERIEAGAME',
    'KXUCLGAME',
]


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


async def fetch_series(session, series_ticker, limit=20, mve_exclude=False):
    path = '/trade-api/v2/markets'
    params = {'status': 'open', 'limit': limit, 'series_ticker': series_ticker}
    if mve_exclude:
        params['mve_filter'] = 'exclude'
    headers = get_auth_headers('GET', path)
    url = f"https://api.elections.kalshi.com{path}"
    try:
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status == 429:
                log.warning(f"Rate limited on {series_ticker} — waiting 60s")
                await asyncio.sleep(60)
                return []
            if resp.status != 200:
                return []
            data = json.loads(await resp.text())
            return data.get('markets', [])
    except Exception as e:
        log.debug(f"Error fetching {series_ticker}: {e}")
        return []


class MarketScanner:
    def __init__(self):
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    def _parse_market(self, raw, market_type='macro'):
        """Parse market using correct Kalshi API field names."""
        try:
            # Prices: yes_bid_dollars and yes_ask_dollars are strings like "0.5600"
            yes_bid = float(raw.get('yes_bid_dollars') or 0)
            yes_ask = float(raw.get('yes_ask_dollars') or 0)

            # Midpoint price
            if yes_bid > 0 and yes_ask > 0:
                yes_price = (yes_bid + yes_ask) / 2
            elif yes_bid > 0:
                yes_price = yes_bid
            elif yes_ask > 0:
                yes_price = yes_ask
            else:
                yes_price = 0.5

            # Clamp to valid range
            yes_price = max(0.01, min(0.99, yes_price))
            no_price = 1 - yes_price

            # Volume and liquidity use correct field names
            volume = float(raw.get('volume_fp') or 0)
            liquidity = float(raw.get('liquidity_dollars') or 0)

            # Resolution time is close_time
            close_time = raw.get('close_time', '')

            return {
                'id': raw.get('ticker'),
                'ticker': raw.get('ticker', ''),
                'question': raw.get('title', ''),
                'description': raw.get('rules_primary', ''),
                'category': raw.get('category', ''),
                'yes_price': yes_price,
                'no_price': no_price,
                'yes_bid': yes_bid,
                'yes_ask': yes_ask,
                'liquidity': liquidity,
                'volume': volume,
                'volume_24h': float(raw.get('volume_24h_fp') or 0),
                'open_interest': float(raw.get('open_interest_fp') or 0),
                'end_date': close_time,
                'status': raw.get('status', ''),
                'market_type': market_type,
            }
        except Exception as e:
            log.warning(f"Failed to parse market {raw.get('ticker','?')}: {e}")
            return None

    async def get_active_markets(self, min_liquidity=0):
        session = await self._get_session()
        macro_markets = []
        sports_markets = []

        # Fetch macro series (exclude combos)
        for series_ticker in MACRO_SERIES:
            batch = await fetch_series(session, series_ticker, limit=20, mve_exclude=True)
            count = 0
            for market in batch:
                parsed = self._parse_market(market, 'macro')
                if parsed:
                    macro_markets.append(parsed)
                    count += 1
            if count:
                log.info(f"Macro {series_ticker}: {count} markets")
            await asyncio.sleep(0.5)

        # Fetch sports game winner series (exclude combos)
        for series_ticker in SPORTS_SERIES:
            batch = await fetch_series(session, series_ticker, limit=50, mve_exclude=True)
            count = 0
            for market in batch:
                parsed = self._parse_market(market, 'sports')
                if parsed:
                    sports_markets.append(parsed)
                    count += 1
            if count:
                log.info(f"Sports {series_ticker}: {count} markets")
            await asyncio.sleep(0.5)

        # Log sample to verify correct parsing
        if sports_markets:
            s = sports_markets[0]
            log.info(f"Sample sports: {s['ticker']} yes={s['yes_price']:.2f} liq=${s['liquidity']:.2f} vol={s['volume']:.2f} close={s['end_date'][:16]}")
        if macro_markets:
            # Find one with non-zero liquidity
            liquid = [m for m in macro_markets if m['liquidity'] > 0]
            if liquid:
                m = liquid[0]
                log.info(f"Sample liquid macro: {m['ticker']} yes={m['yes_price']:.2f} liq=${m['liquidity']:.2f}")

        all_markets = macro_markets + sports_markets
        log.info(f"Total: {len(macro_markets)} macro + {len(sports_markets)} sports markets")
        return all_markets

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
