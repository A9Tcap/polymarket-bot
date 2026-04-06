"""
Market Scanner — fetches macro and sports markets concurrently
Uses correct Kalshi API field names from official docs.
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

MACRO_SERIES = [
    'KXBTC', 'KXETH', 'KXDOGE', 'KXSOL', 'KXXRP',
    'KXCPI', 'KXCPIYOY', 'KXCPICORE', 'KXCPICOREYOY',
    'KXEFFR', 'KXFED', 'KXRATECUT', 'KXDOTPLOT',
    'KXGDP', 'KXPAYROLLS', 'KXU3', 'KXJOBLESSCLAIMS',
    'KXINX', 'KXNASDAQ100', 'KXGOLDD', 'KXWTI',
    'KXTRUMP', 'KXTARIFFRATEPRC', 'KXTARIFFRATEEU',
    'KXNEWTARIFFS', 'KXEFFTARIFF', 'KXTRUMPFIRE', 'KXTRUMPRESIGN',
    'KXECONPATH', 'KXHIGHINFLATION', 'KXRECCOUNT',
    'KXMORTGAGERATE', 'KXEGGS', 'KXUSRETAIL', 'KXPCECORE',
    'KXDEBTGROWTH', 'KXDEFAULT', 'KXUSDJPY', 'KXEURUSD',
]

# Expanded sports series covering all major leagues
SPORTS_SERIES = [
    # Basketball
    'KXNBAGAME',
    'KXNCAAMBGAME',
    # Baseball
    'KXMLBGAME',
    # Hockey
    'KXNHLGAME',
    # Soccer
    'KXEPLGAME',
    'KXLALIGAGAME',
    'KXSERIEAGAME',
    'KXUCLGAME',
    'KXUCLWGAME',
    'KXBUNDESLIGAGAME',
    'KXLIGUE1GAME',
    'KXUELGAME',
    'KXMLSGAME',
    # Tennis
    'KXATPMATCH',
    'KXWTAMATCH',
]


def get_auth_headers(method, path):
    api_key = os.getenv('KALSHI_API_KEY')
    private_key_str = os.getenv('KALSHI_PRIVATE_KEY', '')
    timestamp = str(int(time.time() * 1000))
    message = timestamp + method.upper() + path.split('?')[0]
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
        log.error(f"Auth error: {e}")
        return {'Content-Type': 'application/json'}


async def fetch_one_series(session, series_ticker, limit, market_type):
    path = '/trade-api/v2/markets'
    params = {'status': 'open', 'limit': limit, 'series_ticker': series_ticker, 'mve_filter': 'exclude'}
    headers = get_auth_headers('GET', path)
    url = f"https://api.elections.kalshi.com{path}"
    try:
        async with session.get(url, params=params, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 429:
                log.warning(f"Rate limited: {series_ticker}")
                return series_ticker, market_type, []
            if resp.status != 200:
                return series_ticker, market_type, []
            data = json.loads(await resp.text())
            return series_ticker, market_type, data.get('markets', [])
    except Exception as e:
        log.debug(f"Timeout/error fetching {series_ticker}: {e}")
        return series_ticker, market_type, []


class MarketScanner:
    def __init__(self):
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    def _parse_market(self, raw, market_type):
        try:
            yes_bid = float(raw.get('yes_bid_dollars') or 0)
            yes_ask = float(raw.get('yes_ask_dollars') or 0)
            if yes_bid > 0 and yes_ask > 0:
                yes_price = (yes_bid + yes_ask) / 2
            elif yes_bid > 0:
                yes_price = yes_bid
            elif yes_ask > 0:
                yes_price = yes_ask
            else:
                yes_price = 0.5
            yes_price = max(0.01, min(0.99, yes_price))

            return {
                'id': raw.get('ticker'),
                'ticker': raw.get('ticker', ''),
                'question': raw.get('title', ''),
                'yes_price': yes_price,
                'no_price': 1 - yes_price,
                'yes_bid': yes_bid,
                'yes_ask': yes_ask,
                'liquidity': float(raw.get('liquidity_dollars') or 0),
                'volume': float(raw.get('volume_fp') or 0),
                'volume_24h': float(raw.get('volume_24h_fp') or 0),
                'open_interest': float(raw.get('open_interest_fp') or 0),
                'end_date': raw.get('close_time', ''),
                'status': raw.get('status', ''),
                'market_type': market_type,
            }
        except Exception as e:
            log.debug(f"Parse error {raw.get('ticker','?')}: {e}")
            return None

    async def get_active_markets(self, min_liquidity=0):
        session = await self._get_session()

        tasks = []
        for s in MACRO_SERIES:
            tasks.append(fetch_one_series(session, s, 20, 'macro'))
        for s in SPORTS_SERIES:
            tasks.append(fetch_one_series(session, s, 50, 'sports'))

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=30
            )
        except asyncio.TimeoutError:
            log.warning("Global scan timeout — using partial results")
            results = []

        macro_markets = []
        sports_markets = []

        for result in results:
            if isinstance(result, Exception):
                continue
            series_ticker, market_type, raw_markets = result
            count = 0
            for raw in raw_markets:
                parsed = self._parse_market(raw, market_type)
                if parsed:
                    if market_type == 'macro':
                        macro_markets.append(parsed)
                    else:
                        sports_markets.append(parsed)
                    count += 1
            if count:
                log.info(f"{market_type.capitalize()} {series_ticker}: {count} markets")

        if sports_markets:
            s = sports_markets[0]
            log.info(f"Sample sports: {s['ticker']} yes={s['yes_price']:.2f} liq=${s['liquidity']:.2f} vol={s['volume']:.2f}")
        if macro_markets:
            liquid = [m for m in macro_markets if m['liquidity'] > 0]
            if liquid:
                m = liquid[0]
                log.info(f"Sample liquid macro: {m['ticker']} yes={m['yes_price']:.2f} liq=${m['liquidity']:.2f}")

        log.info(f"Total: {len(macro_markets)} macro + {len(sports_markets)} sports markets")
        return macro_markets + sports_markets

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
