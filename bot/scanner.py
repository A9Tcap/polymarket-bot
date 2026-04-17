"""
Market Scanner — fetches macro, commodities, political, and sports markets.

Series breakdown:
- MACRO_SERIES: Fed, CPI, GDP, jobs, crypto, S&P, tariffs, Trump
- COMMODITY_SERIES: Oil, gold, silver, natgas, copper + NEW: wheat, corn, coffee, soybeans
- POLITICAL_SERIES: Congress, midterms, Trump approval, executive actions
- SPORTS_SERIES: NBA, MLB, NHL, EPL, La Liga, Serie A, UCL, Bundesliga, Ligue 1, tennis, MLS

The AI economist framework handles quality filtering — we just need to
surface the markets. More variety = more opportunities for edge.
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

# ── Fed & Monetary Policy ──────────────────────────────────────────────────────
MACRO_SERIES = [
    # Fed & rates
    'KXEFFR', 'KXFED', 'KXRATECUT', 'KXDOTPLOT',
    # Inflation
    'KXCPI', 'KXCPIYOY', 'KXCPICORE', 'KXCPICOREYOY',
    'KXPCECORE', 'KXHIGHINFLATION', 'KXEGGS', 'KXUSRETAIL',
    # Growth & labor
    'KXGDP', 'KXPAYROLLS', 'KXU3', 'KXJOBLESSCLAIMS',
    'KXRECCOUNT', 'KXECONPATH',
    # Markets
    'KXINX', 'KXNASDAQ100',
    # Crypto
    'KXBTC', 'KXETH', 'KXDOGE', 'KXSOL', 'KXXRP',
    # Tariffs & trade
    'KXTARIFFRATEPRC', 'KXTARIFFRATEEU', 'KXNEWTARIFFS',
    'KXEFFTARIFF', 'KXTRUMPFIRE', 'KXTRUMPRESIGN',
    'KXMORTGAGERATE', 'KXDEBTGROWTH', 'KXDEFAULT',
    'KXUSDJPY', 'KXEURUSD',
]

# ── Commodities — includes brand new Kalshi markets (launched April 2026) ─────
COMMODITY_SERIES = [
    # Energy
    'KXWTI',        # WTI Crude Oil
    'KXBRENTD',     # Brent Crude daily
    'KXNATGASD',    # Natural Gas daily
    'KXNATGASW',    # Natural Gas weekly
    # Metals
    'KXGOLDD',      # Gold daily
    'KXGOLDMON',    # Gold monthly
    'KXSILVERD',    # Silver daily
    'KXSILVERMON',  # Silver monthly
    'KXCOPPERD',    # Copper daily — key Iran war indicator
    'KXCOPPERMON',  # Copper monthly
    # NEW Agricultural commodities (launched April 15, 2026)
    'KXCORND',      # Corn
    'KXWHEATD',     # Wheat
    'KXSOYBEAND',   # Soybeans
    'KXCOFFEED',    # Coffee
    'KXSUGARD',     # Sugar
    'KXCOTTON',     # Cotton
    # Energy additions
    'KXDIESELD',    # Diesel
    'KXGASOLINED',  # Gasoline
    # Lithium/battery metals
    'KXLITHIUMD',   # Lithium
    'KXNICKELMON',  # Nickel
]

# ── Political markets — building toward midterms ───────────────────────────────
POLITICAL_SERIES = [
    'KXTRUMP',              # Trump actions/approval
    'KXTRUMPACT',           # Trump executive actions
    'KXTRUMPAPPROVALBELOW', # Trump approval rating
    'KXTRUMPPRES',          # Trump presidency outcomes
    'KXTRUMPCHINA',         # Trump China policy
    'KXTRUMPIRAN',          # Trump Iran policy
    'KXTRUMPFIRE',          # Trump firing officials
    'KXBILLSCOUNT',         # Congressional bills
    'KXVETOCOUNT',          # Presidential vetoes
    'KXDCEILEND',           # Debt ceiling
    'KXGOVTSHUTLENGTH',     # Government shutdown
    'KXFEDCHAIRCONFIRM',    # Fed chair confirmation (Warsh)
]

# ── Sports game winner series ──────────────────────────────────────────────────
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
    path_to_sign = path.split('?')[0]
    message = timestamp + method.upper() + path_to_sign
    key_str = private_key_str.strip().replace('\\n', '\n')
    try:
        private_key = serialization.load_pem_private_key(
            key_str.encode(), password=None, backend=default_backend()
        )
        sig = private_key.sign(
            message.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=hashes.SHA256.digest_size),
            hashes.SHA256()
        )
        return {
            'KALSHI-ACCESS-KEY': api_key,
            'KALSHI-ACCESS-SIGNATURE': base64.b64encode(sig).decode(),
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
        }
    except Exception as e:
        log.error(f"Auth header error: {e}")
        return {'Content-Type': 'application/json'}


async def fetch_series(session, series_ticker, limit=20, market_type='macro'):
    """Fetch markets for a single series with error handling."""
    path = '/trade-api/v2/markets'
    params = {
        'status': 'open',
        'limit': limit,
        'series_ticker': series_ticker,
        'mve_filter': 'exclude',  # Exclude combo/multi-leg markets
    }
    headers = get_auth_headers('GET', path)
    url = f"https://api.elections.kalshi.com{path}"
    try:
        async with session.get(
            url, params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=8)
        ) as resp:
            if resp.status == 429:
                log.warning(f"Rate limited: {series_ticker}")
                return series_ticker, market_type, []
            if resp.status != 200:
                return series_ticker, market_type, []
            data = json.loads(await resp.text())
            return series_ticker, market_type, data.get('markets', [])
    except Exception as e:
        log.debug(f"Error fetching {series_ticker}: {e}")
        return series_ticker, market_type, []


class MarketScanner:
    def __init__(self):
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    def _parse_market(self, raw, market_type='macro'):
        """Parse raw Kalshi API response into standardized market dict."""
        try:
            # Use yes_bid_dollars / yes_ask_dollars (correct field names)
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
                'id':           raw.get('ticker'),
                'ticker':       raw.get('ticker', ''),
                'question':     raw.get('title', ''),
                'yes_price':    yes_price,
                'no_price':     1 - yes_price,
                'yes_bid':      yes_bid,
                'yes_ask':      yes_ask,
                'liquidity':    float(raw.get('liquidity_dollars') or 0),
                'volume':       float(raw.get('volume_fp') or 0),
                'volume_24h':   float(raw.get('volume_24h_fp') or 0),
                'open_interest':float(raw.get('open_interest_fp') or 0),
                'end_date':     raw.get('close_time', ''),
                'status':       raw.get('status', ''),
                'market_type':  market_type,
            }
        except Exception as e:
            log.debug(f"Parse error {raw.get('ticker','?')}: {e}")
            return None

    async def get_active_markets(self, min_liquidity=0):
        session = await self._get_session()

        # Build all fetch tasks concurrently
        tasks = []
        for s in MACRO_SERIES:
            tasks.append(fetch_series(session, s, limit=20, market_type='macro'))
        for s in COMMODITY_SERIES:
            tasks.append(fetch_series(session, s, limit=10, market_type='macro'))
        for s in POLITICAL_SERIES:
            tasks.append(fetch_series(session, s, limit=10, market_type='macro'))
        for s in SPORTS_SERIES:
            tasks.append(fetch_series(session, s, limit=50, market_type='sports'))

        # Run all concurrently with global timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=45
            )
        except asyncio.TimeoutError:
            log.warning("Global scan timeout — using partial results")
            results = []

        macro_markets = []
        sports_markets = []
        commodity_count = 0
        political_count = 0

        for result in results:
            if isinstance(result, Exception):
                continue
            series_ticker, market_type, raw_markets = result
            count = 0
            for raw in raw_markets:
                parsed = self._parse_market(raw, market_type)
                if parsed:
                    if market_type == 'sports':
                        sports_markets.append(parsed)
                    else:
                        macro_markets.append(parsed)
                    count += 1

            if count:
                if series_ticker in COMMODITY_SERIES:
                    commodity_count += count
                    log.info(f"Commodity {series_ticker}: {count} markets")
                elif series_ticker in POLITICAL_SERIES:
                    political_count += count
                    log.info(f"Political {series_ticker}: {count} markets")
                else:
                    category = 'Macro' if market_type == 'macro' else 'Sports'
                    log.info(f"{category} {series_ticker}: {count} markets")

        # Summary
        if sports_markets:
            s = sports_markets[0]
            log.info(
                f"Sample sports: {s['ticker']} yes={s['yes_price']:.2f} "
                f"liq=${s['liquidity']:.2f} vol={s['volume']:.2f}"
            )
        liquid_macro = [m for m in macro_markets if m['liquidity'] > 0]
        if liquid_macro:
            m = liquid_macro[0]
            log.info(
                f"Sample liquid macro: {m['ticker']} yes={m['yes_price']:.2f} "
                f"liq=${m['liquidity']:.2f}"
            )

        log.info(
            f"Total: {len(macro_markets)} macro/commodity/political "
            f"({commodity_count} commodity, {political_count} political) "
            f"+ {len(sports_markets)} sports markets"
        )

        return macro_markets + sports_markets

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
