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

# Macro/economics/crypto series — main strategy
MACRO_SERIES = [
    'KXBTC', 'KXETH',
    'KXCPI', 'KXCPIYOY', 'KXCPICORE', 'KXCPICOREYOY',
    'KXEFFR', 'KXFED', 'KXRATECUT', 'KXDOTPLOT',
    'KXGDP', 'KXPAYROLLS', 'KXU3', 'KXJOBLESSCLAIMS',
    'KXINX', 'KXNASDAQ100', 'KXGOLDD', 'KXWTI',
    'KXTRUMP', 'KXTARIFFRATEPRC', 'KXTARIFFRATEEU',
    'KXNEWTARIFFS', 'KXEFFTARIFF', 'KXTRUMPFIRE', 'KXTRUMPRESIGN',
    'KXECONPATH', 'KXHIGHINFLATION', 'KXRECCOUNT',
    'KXMORTGAGERATE', 'KXEGGS', 'KXUSRETAIL',
    'KXDOGE', 'KXSOL', 'KXXRP',
]

# Sports game winner series only — no props, no spreads, no combos
SPORTS_SERIES = [
    'KXNBAGAME',    # NBA game winners
    'KXMLBGAME',    # MLB game winners
    'KXNHLGAME',    # NHL game winners
    'KXNFLGAME',    # NFL game winners
    'KXEPLGAME',    # EPL soccer
    'KXLALIGAGAME', # La Liga soccer
    'KXSERIEAGAME', # Serie A soccer
    'KXUCLGAME',    # Champions League
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


async def fetch_series(session, series_ticker, limit=20):
    """Fetch markets for a single series."""
    path = '/trade-api/v2/markets'
    params = {'status': 'open', 'limit': limit, 'series_ticker': series_ticker}
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

    async def get_active_markets(self, min_liquidity=0):
        session = await self._get_session()
        macro_markets = []
        sports_markets = []

        # Fetch macro series
        for series_ticker in MACRO_SERIES:
            batch = await fetch_series(session, series_ticker, limit=20)
            count = 0
            for market in batch:
                parsed = self._parse_market(market)
                if parsed:
                    parsed['market_type'] = 'macro'
                    macro_markets.append(parsed)
                    count += 1
            if count:
                log.info(f"Macro {series_ticker}: {count} markets")
            await asyncio.sleep(0.5)

        # Fetch sports game winner series
        for series_ticker in SPORTS_SERIES:
            batch = await fetch_series(session, series_ticker, limit=50)
            count = 0
            for market in batch:
                parsed = self._parse_market(market)
                if parsed:
                    parsed['market_type'] = 'sports'
                    sports_markets.append(parsed)
                    count += 1
            if count:
                log.info(f"Sports {series_ticker}: {count} markets")
            await asyncio.sleep(0.5)

        all_markets = macro_markets + sports_markets
        log.info(f"Total: {len(macro_markets)} macro + {len(sports_markets)} sports markets")
        return all_markets

    def _parse_market(self, raw):
        try:
            yes_bid = raw.get('yes_bid', 0) or 0
            yes_ask = raw.get('yes_ask', 0) or 0
            yes_price = (yes_bid + yes_ask) / 2 / 100 if (yes_bid + yes_ask) > 0 else 0.5
            no_price = 1 - yes_price

            if yes_price <= 0 or yes_price >= 1:
                return None

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
                'market_type': 'macro',
            }
        except Exception as e:
            log.warning(f"Failed to parse market: {e}")
            return None

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
