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

# Economics, politics, crypto, and macro markets — confirmed from live API
GOOD_SERIES = {
    # Economics & Fed
    'KXCPI', 'KXCPICORE', 'KXCPICOREYOY', 'KXCPIYOY',
    'KXEFFR', 'KXFED', 'KXFEDDECISION', 'KXFEDDISSENT', 'KXFEDCOMBO',
    'KXRATECUT', 'KXRATECUTCOUNT', 'KXLARGECUT', 'KXEMERCUTS',
    'KXDOTPLOT', 'KXFOMCDISSENTCOUNT',
    'KXGDP', 'KXGDPNOM', 'KXGDPYEAR',
    'KXPAYROLLS', 'KXPCECORE', 'KXU3', 'KXU3MAX',
    'KXJOBLESSCLAIMS', 'KXUSNFP', 'KXADP',
    'KXISMPMI', 'KXUSRETAIL', 'KXHOUSINGSTART',
    'KXHIGHINFLATION', 'KXLCPIMAXYOY', 'KXSHELTERCPI',
    'KXAIRFARECPI', 'KXUSEDCARCPI', 'KXUSGASCPI', 'KXEGGS',
    'KXTRADEDEFICIT', 'KXDEBTGROWTH', 'KXDEFGDP',
    'KXRECCOUNT', 'KXRECSSNBER',
    # Financial markets
    'KXINX', 'KXINXMAXY', 'KXINXMINY', 'KXINXPOS', 'KXINXU', 'KXINXY',
    'KXNASDAQ100', 'KXNASDAQ100MAXY', 'KXNASDAQ100MINY',
    'KXNASDAQ100POS', 'KXNASDAQ100U', 'KXNASDAQ100Y',
    'KXGOLDD', 'KXGOLDMON', 'KXGOLDW',
    'KXSILVERD', 'KXSILVERMON', 'KXSILVERW',
    'KXBRENTD', 'KXBRENTW', 'KXWTI', 'KXWTIMAX', 'KXWTIW',
    'KXNATGASD', 'KXNATGASW', 'KXCOPPERD', 'KXCOPPERMON',
    'KXUSDJPY', 'KXEURUSD', 'KXUSTYLD', 'KXUSDTTBILL',
    'KX3MTBILL', 'KX10Y2Y', 'KX10Y3M',
    'KXMORTGAGERATE', 'KXBOND',
    # Crypto
    'KXBTC', 'KXBTC15M', 'KXBTCD', 'KXBTCY',
    'KXBTC2026200', 'KXBTC2026250', 'KXBTCMAX100', 'KXBTCMAX150',
    'KXBTCMAXMON', 'KXBTCMAXY', 'KXBTCMINMON', 'KXBTCMINY',
    'KXBTCRESERVE', 'KXBTCVSGOLD', 'KXBTCHALF',
    'KXETH', 'KXETH15M', 'KXETHD', 'KXETHMAXMON', 'KXETHMAXY', 'KXETHMINY', 'KXETHY',
    'KXDOGE', 'KXDOGE15M', 'KXDOGED',
    'KXBNB', 'KXBNB15M', 'KXBNBD',
    'KXSOL', 'KXSOLD', 'KXSOL26',
    'KXXRP', 'KXXRP15M', 'KXXRPD',
    'KXHYPE', 'KXHYPE15M', 'KXHYPED',
    'KXCRYPTOCAPGAIN', 'KXCRYPTOPAY', 'KXCRYPTORETURNY', 'KXCRYPTOSTRUCTURE',
    # Trump & Politics
    'KXTRUMP', 'KXTRUMPACT', 'KXTRUMPAPPROVALBELOW', 'KXTRUMPAPPROVALYEAR',
    'KXTRUMPCHINA', 'KXTRUMPIRAN', 'KXTRUMPOUT27', 'KXTRUMPPRES',
    'KXTRUMPREMOVE', 'KXTRUMPRESIGN', 'KXTRUMPSAY', 'KXTRUMPSAYMONTH',
    'KXTRUMPFIRE', 'KXTRUMPPARDON', 'KXTRUMPPARDONS',
    'KXTARIFFBILL', 'KXTARIFFRATECAN', 'KXTARIFFRATEEU',
    'KXTARIFFRATEINDIA', 'KXTARIFFRATEPRC', 'KXTARIFFREVENUE',
    'KXNEWTARIFFS', 'KXEFFTARIFF', 'KXDISAPPROVETARIFF',
    'KXECONPATH', 'KXECONSTATCPI', 'KXECONSTATCPICORE',
    'KXECONSTATCPIYOY', 'KXECONSTATU3',
    # Government & Policy  
    'KXDOGE', 'KXAGENCIES', 'KXAGENCYELIM',
    'KXGOVTSHUTLENGTH', 'KXNUMSHUTDOWNS', 'KXDCEILEND',
    'KXBILLSCOUNT', 'KXVETOCOUNT',
    'KXFEDCHAIRCONFIRM', 'KXFEDCHAIRCONFIRMED', 'KXTRYFIREPOWELL',
    'LEAVEPOWELL', 'KXLEAVEPOWELLGOV',
    # Iran / Geopolitical
    'KXIRANEMBASSY', 'KXIRANIMPORTS', 'KXIRANDEMOCRACY',
    'KXHORMUZNORM', 'KXHORMUZTRAFFIC',
    'KXWCIRAN', 'KXUSAIRANAGREEMENT',
    # Housing
    'KXBOSHOMEVAL', 'KXDENHOMEVAL', 'KXHOUHOMEVAL',
    'KXSEAHOMEVAL', 'KXUSHOMEVAL', 'KXHFHOUSING',
    # Other macro
    'KXUSDEBTMON', 'KXDEFAULT', 'KXCREDITRATING',
    'KXOILRIGS', 'KXBARRELS', 'KXQATARLNGPROD',
    'FEDHIKE', 'KXFEDHIKE',
}


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


def is_good_ticker(ticker):
    if not ticker:
        return False
    # Check exact series match
    series = ticker.split('-')[0].upper()
    return series in GOOD_SERIES


class MarketScanner:
    def __init__(self):
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_active_markets(self, min_liquidity=100):
        session = await self._get_session()
        all_markets = []
        cursor = None

        try:
            while True:
                path = '/trade-api/v2/markets'
                params = {'status': 'open', 'limit': 200}
                if cursor:
                    params['cursor'] = cursor

                headers = get_auth_headers('GET', path)
                url = f"https://api.elections.kalshi.com{path}"

                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status == 429:
                        log.warning("Rate limited — waiting 120s")
                        await asyncio.sleep(120)
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
                        if is_good_ticker(parsed['ticker']):
                            all_markets.append(parsed)

                cursor = data.get('cursor')
                if not cursor or len(all_markets) >= 200:
                    break

        except Exception as e:
            log.error(f"Error fetching markets: {e}", exc_info=True)

        log.info(f"Fetched {len(all_markets)} macro/politics/crypto markets")
        for m in all_markets[:10]:
            log.info(f"  [{m['ticker']}] {m['question'][:70]}")

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
