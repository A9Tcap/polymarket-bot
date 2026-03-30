"""
Trade Executor — places orders on Kalshi using official kalshi-py SDK
"""

import logging
import os
import json
from typing import Dict

log = logging.getLogger('executor')


class TradeExecutor:
    def __init__(self, config: Dict):
        self.dry_run = config.get('dry_run', True)
        self.api_key = os.getenv('KALSHI_API_KEY')
        self.private_key = os.getenv('KALSHI_PRIVATE_KEY', '')
        self.client = None

        if not self.dry_run:
            self._init_client()
            log.warning("LIVE TRADING MODE ENABLED")

    def _init_client(self):
        try:
            from kalshi_py import create_client
            self.client = create_client(
                access_key_id=self.api_key,
                private_key_data=self.private_key,
            )
            log.info("Kalshi client initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize Kalshi client: {e}")
            self.client = None

    async def execute(self, trade: Dict) -> Dict:
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

        if not self.client:
            self._init_client()
            if not self.client:
                return {'status': 'error', 'error': 'Kalshi client not initialized'}

        try:
            ticker = market.get('ticker') or market.get('id')
            side = 'yes' if direction == 'BUY_YES' else 'no'
            price = market['yes_price'] if direction == 'BUY_YES' else market['no_price']

            # Kalshi prices in cents (1-99)
            price_cents = max(1, min(99, round(price * 100)))

            # Number of contracts
            contracts = max(1, round(size / (price_cents / 100)))

            import uuid
            from kalshi_py.api.portfolio import create_order
            from kalshi_py.models import CreateOrderRequest

            order = CreateOrderRequest(
                ticker=ticker,
                client_order_id=str(uuid.uuid4()),
                type='market',
                action='buy',
                side=side,
                count=contracts,
            )

            result = create_order.sync(client=self.client, body=order)
            log.info(f"Order placed: {side.upper()} {contracts} contracts on '{question}'")
            return {'status': 'filled', 'order': str(result)}

        except Exception as e:
            log.error(f"Trade execution failed: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}

    async def close(self):
        pass
