"""
Market Scanner — fetches and filters active Polymarket markets
"""

import logging
import aiohttp
from typing import List, Dict

log = logging.getLogger('scanner')

GAMMA_API = "https://gamma-api.polymarket.com"


class MarketScanner:
    def __init__(self):
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_active_markets(self, min_liquidity: float = 5000) -> List[Dict]:
        """Fetch all active markets above minimum liquidity threshold."""
        session = await self._get_session()
        markets = []
        offset = 0
        limit = 100

        try:
            while True:
                url = f"{GAMMA_API}/markets"
                params = {
                    'active': 'true',
                    'closed': 'false',
                    'limit': limit,
                    'offset': offset,
                    'order': 'volume24hr',
                    'ascending': 'false',
                }
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        log.error(f"API error: {resp.status}")
                        break
                    data = await resp.json()

                if not data:
                    break

                for market in data:
                    liquidity = float(market.get('liquidity', 0) or 0)
                    if liquidity >= min_liquidity:
                        parsed = self._parse_market(market)
                        if parsed:
                            markets.append(parsed)

                if len(data) < limit:
                    break
                offset += limit

                # Cap at 500 markets for performance
                if len(markets) >= 500:
                    break

        except Exception as e:
            log.error(f"Error fetching markets: {e}", exc_info=True)

        log.info(f"Fetched {len(markets)} markets with liquidity >= ${min_liquidity}")
        return markets

    def _parse_market(self, raw: Dict) -> Dict:
        """Parse raw market data into standardized format."""
        try:
            outcomes = raw.get('outcomes', [])
            outcome_prices = raw.get('outcomePrices', [])

            if not outcomes or not outcome_prices:
                return None

            # Parse YES/NO prices
            prices = {}
            for i, outcome in enumerate(outcomes):
                try:
                    prices[outcome] = float(outcome_prices[i])
                except (IndexError, ValueError):
                    pass

            yes_price = prices.get('Yes', prices.get('YES', None))
            no_price = prices.get('No', prices.get('NO', None))

            if yes_price is None:
                return None

            return {
                'id': raw.get('id'),
                'condition_id': raw.get('conditionId'),
                'question': raw.get('question', ''),
                'description': raw.get('description', ''),
                'category': raw.get('category', ''),
                'yes_price': yes_price,
                'no_price': no_price or (1 - yes_price),
                'liquidity': float(raw.get('liquidity', 0) or 0),
                'volume': float(raw.get('volume', 0) or 0),
                'volume_24hr': float(raw.get('volume24hr', 0) or 0),
                'end_date': raw.get('endDate'),
                'tags': raw.get('tags', []),
                'clob_token_ids': raw.get('clobTokenIds', []),
            }
        except Exception as e:
            log.warning(f"Failed to parse market: {e}")
            return None

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
