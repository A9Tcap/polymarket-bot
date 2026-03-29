"""
Trade Executor — places orders on Polymarket via CLOB API
"""

import logging
import os
import time
import json
import hmac
import hashlib
import aiohttp
from typing import Dict
from eth_account import Account
from eth_account.messages import encode_defunct

log = logging.getLogger('executor')

CLOB_API = "https://clob.polymarket.com"


class TradeExecutor:
    def __init__(self, config: Dict):
        self.dry_run = config.get('dry_run', True)
        self.api_key = os.getenv('POLYMARKET_API_KEY')
        self.private_key = os.getenv('POLYMARKET_PRIVATE_KEY')
        self.wallet_address = os.getenv('POLYMARKET_WALLET_ADDRESS')
        self.session = None

        if not self.dry_run:
            if not all([self.api_key, self.private_key, self.wallet_address]):
                raise ValueError("Missing Polymarket credentials for live trading")
            log.warning("LIVE TRADING MODE ENABLED")

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    def _sign_message(self, message: str) -> str:
        """Sign a message with the wallet private key."""
        account = Account.from_key(self.private_key)
        msg = encode_defunct(text=message)
        signed = account.sign_message(msg)
        return signed.signature.hex()

    def _get_auth_headers(self, method: str, path: str, body: str = '') -> Dict:
        """Generate authentication headers for CLOB API."""
        timestamp = str(int(time.time() * 1000))
        message = timestamp + method.upper() + path + body
        signature = self._sign_message(message)

        return {
            'POLY-API-KEY': self.api_key,
            'POLY-SIGNATURE': signature,
            'POLY-TIMESTAMP': timestamp,
            'POLY-ADDRESS': self.wallet_address,
            'Content-Type': 'application/json',
        }

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

        # Live trading
        try:
            if direction == 'BUY_YES':
                return await self._place_order(market, 'YES', size)
            elif direction == 'BUY_NO':
                return await self._place_order(market, 'NO', size)
            elif direction == 'BUY_BOTH':
                # Arbitrage: buy both YES and NO
                r1 = await self._place_order(market, 'YES', size / 2)
                r2 = await self._place_order(market, 'NO', size / 2)
                return {'status': 'both_placed', 'yes': r1, 'no': r2}
            else:
                log.warning(f"Unknown direction: {direction}")
                return {'status': 'skipped', 'reason': f'Unknown direction: {direction}'}

        except Exception as e:
            log.error(f"Trade execution failed: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}

    async def _place_order(self, market: Dict, side: str, size_usdc: float) -> Dict:
        """Place a market order on Polymarket CLOB."""
        session = await self._get_session()

        # Get the token ID for this side
        token_ids = market.get('clob_token_ids', [])
        if not token_ids or len(token_ids) < 2:
            return {'status': 'error', 'reason': 'No CLOB token IDs for market'}

        token_id = token_ids[0] if side == 'YES' else token_ids[1]
        price = market['yes_price'] if side == 'YES' else market['no_price']

        # Calculate shares from USDC size
        shares = round(size_usdc / price, 2)

        order_payload = {
            'tokenID': token_id,
            'price': round(price, 4),
            'side': 'BUY',
            'size': shares,
            'orderType': 'FOK',  # Fill or Kill for market orders
        }

        body = json.dumps(order_payload)
        path = '/order'
        headers = self._get_auth_headers('POST', path, body)

        async with session.post(f"{CLOB_API}{path}", headers=headers, data=body) as resp:
            result = await resp.json()
            if resp.status == 200:
                log.info(f"Order placed: {side} {shares} shares @ {price:.4f} = ${size_usdc:.2f}")
                return {'status': 'filled', 'order': result}
            else:
                log.error(f"Order failed: {resp.status} {result}")
                return {'status': 'error', 'response': result}

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
