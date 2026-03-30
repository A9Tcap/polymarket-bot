"""
Trade Executor — places orders on Kalshi API with RSA-PSS signing
"""

import logging
import os
import json
import time
import base64
import uuid
import aiohttp
from typing import Dict
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

log = logging.getLogger('executor')

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"


def sign_request(method: str, path: str, private_key_str: str) -> Dict:
    timestamp = str(int(time.time() * 1000))
    path_to_sign = path.split('?')[0]
    message = timestamp + method.upper() + path_to_sign

    try:
        private_key_bytes = private_key_str.strip().encode()
        if not private_key_bytes.startswith(b'-----'):
            private_key_bytes = (
                b'-----BEGIN RSA PRIVATE KEY-----\n' +
                private_key_bytes +
                b'\n-----END RSA PRIVATE KEY-----'
            )

        private_key = serialization.load_pem_private_key(
            private_key_bytes, password=None, backend=default_backend()
        )

        signature = private_key.sign(
            message.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=hashes.SHA256.digest_size
            ),
            hashes.SHA256()
        )
        sig_b64 = base64.b64encode(signature).decode()

        return {
            'KALSHI-ACCESS-KEY': os.getenv('KALSHI_API_KEY'),
            'KALSHI-ACCESS-SIGNATURE': sig_b64,
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
        }
    except Exception as e:
        log.error(f"Signing failed: {e}")
        return {'Content-Type': 'application/json'}


class TradeExecutor:
    def __init__(self, config: Dict):
        self.dry_run = config.get('dry_run', True)
        self.private_key = os.getenv('KALSHI_PRIVATE_KEY', '')
        self.session = None

        if not self.dry_run:
            log.warning("LIVE TRADING MODE ENABLED")

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def execute(self, trade: Dict) -> Dict:
        market = trade['market']
        direction = trade['direction']
        size = trade['position_size_usdc']
        question = market['question'][:60]

        if self.dry_run:
            log.info(f"[DRY RUN] Would execute: {direction} ${size:.2f} on '{question}'")
            return {
                'status': 'dry_run',
                'direction': direction,
                'size': size,
                'market_id': market['id'],
                'question': question,
            }

        try:
            ticker = market.get('ticker') or market.get('id')
            side = 'yes' if direction == 'BUY_YES' else 'no'
            price = market['yes_price'] if direction == 'BUY_YES' else market['no_price']
            price_cents = max(1, min(99, round(price * 100)))
            contracts = max(1, round(size / (price_cents / 100)))

            order_payload = {
                'ticker': ticker,
                'client_order_id': str(uuid.uuid4()),
                'type': 'market',
                'action': 'buy',
                'side': side,
                'count': contracts,
            }

            path = '/trade-api/v2/portfolio/orders'
            body = json.dumps(order_payload)
            headers = sign_request('POST', path, self.private_key)

            session = await self._get_session()
            async with session.post(
                f"https://api.elections.kalshi.com{path}",
                headers=headers,
                data=body
            ) as resp:
                result = await resp.json()
                if resp.status in (200, 201):
                    log.info(f"Order placed: {side.upper()} {contracts} contracts on '{question}'")
                    return {'status': 'filled', 'order': result}
                else:
                    log.error(f"Order failed: {resp.status} {result}")
                    return {'status': 'error', 'response': result}

        except Exception as e:
            log.error(f"Trade execution failed: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
             `
