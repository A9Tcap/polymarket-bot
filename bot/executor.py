"""
Trade Executor — places orders on Kalshi API
"""

import logging
import os
import json
import aiohttp
from typing import Dict
from bot.scanner import get_auth_headers

log = logging.getLogger('executor')

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"


class TradeExecutor:
    def __init__(self, config: Dict):
        self.dry_run = config.get('dry_run', True)
        self.api_key = os.getenv('KALSHI_API_KEY')
        self.private_key = os.getenv('KALSHI_PRIVATE_KEY')
        self.session = None

        if not self.dry_run:
            if not all([self.api_key, self.private_key]):
                raise ValueError("Missing Kalshi credentials for live trading")
            log.warning("LIVE TRADING MODE ENABLED")

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def execute(self, trade: Dict) -> Dict:
        """Execute a trade (or simulate in dry run mode)."""
        market = trade['market']
        direction = trade['direction']
        size = trade['position_size_usdc']
        question = market['question'][:60]

        if self.dry_run:
            log.info(f"[DRY RUN] Would execute: {direction} ${size:.2f} on '{question}...'")
            return {
                'status': 'dry_run',
                'direction': direction,
                'size': size,
                'market_id': market['id'],
                'question': question,
                'message': 'Dry run — no real trade placed',
            }

        try:
            if direction == 'BUY_YES':
                return await self._place_order(market, 'yes', size)
            elif direction == 'BUY_NO':
                return await self._place_order(market, 'no', size)
            elif direction == 'BUY_BOTH':
                r1 = await self._place_order(market, 'yes', size / 2)
                r2 = await self._place_order(market, 'no', size / 2)
                return {'status': 'both_placed', 'yes': r1, 'no': r2}
            else:
                return {'status': 'skipped', 'reason': f'Unknown direction: {direction}'}

        except Exception as e:
            log.error(f"Trade execution failed: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}

    async def _place_order(self, market: Dict, side: str, size_usdc: float) -> Dict:
        """Place an order on Kalshi."""
        session = await self._get_session()

        ticker = market.get('ticker') or market.get('id')
        price = market['yes_price'] if side == 'yes' else market['no_price']

        # Kalshi uses cents (1-99)
        price_cents = max(1, min(99, round(price * 100)))

        # Calculate contracts from USDC (each contract costs price_cents / 100)
        contracts = max(1, round(size_usdc / (price_cents / 100)))

        order_payload = {
            'ticker': ticker,
            'client_order_id': f"bot_{ticker}_{int(os.urandom(4).hex(), 16)}",
            'type': 'market',
            'action': 'buy',
            'side': side,
            'count': contracts,
        }

        path = '/portfolio/orders'
        body = json.dumps(order_payload)
        headers = get_auth_headers('POST', path)

        async with session.post(
            f"{KALSHI_API}{path}",
            headers=headers,
            data=body
        ) as resp:
            result = await resp.json()
            if resp.status in (200, 201):
                log.info(f"Order placed: {side.upper()} {contracts} contracts @ {price_cents}¢ = ~${size_usdc:.2f}")
                return {'status': 'filled', 'order': result}
            else:
                log.error(f"Order failed: {resp.status} {result}")
                return {'status': 'error', 'response': result}

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
